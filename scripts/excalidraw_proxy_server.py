"""
Lightweight local HTTP server for Excalidraw vector rendering.
Serves local docs/ directory and proxies esm.sh bundle sub-modules.
"""

import http.server
import socketserver
import urllib.request
from pathlib import Path

PORT = 8085
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"

class ExcalidrawHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS_DIR), **kwargs)

    def do_GET(self):
        clean_path = self.path.split("?")[0].lstrip("/")
        local_file = DOCS_DIR / clean_path
        if clean_path and local_file.exists() and local_file.is_file():
            return super().do_GET()
        
        # Proxy ESM sub-dependencies (/@braintree, /node, /nanoid, etc.) to esm.sh
        remote_url = f"https://esm.sh{self.path}"
        try:
            req = urllib.request.Request(remote_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                self.send_response(resp.status)
                for header, val in resp.getheaders():
                    if header.lower() not in ["content-length", "transfer-encoding", "content-encoding"]:
                        self.send_header(header, val)
                content = resp.read()
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
        except Exception as e:
            self.send_error(404, f"Proxy Error: {e}")

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), ExcalidrawHandler) as httpd:
        print(f"Excalidraw Vector Renderer Server listening on http://localhost:{PORT}")
        httpd.serve_forever()

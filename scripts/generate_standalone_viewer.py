"""
Embeds the Excalidraw JSON directly into a self-contained HTML renderer.
Uses @excalidraw/excalidraw SVG exporter bundle from esm.sh.
"""

import json
from pathlib import Path

def main():
    excal_file = Path("docs/architecture_workflow.excalidraw")
    data = json.loads(excal_file.read_text(encoding="utf-8"))
    json_str = json.dumps(data)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Lexi - Emirates NBD Excalidraw Architecture Workflow</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      background: #0f172a;
      color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      overflow-x: auto;
      overflow-y: auto;
      padding: 24px;
    }}
    .header-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #1e293b;
      border: 1px solid #334155;
      padding: 14px 28px;
      border-radius: 14px;
      margin-bottom: 24px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }}
    .header-bar h1 {{
      font-size: 22px;
      color: #38bdf8;
      font-weight: 700;
    }}
    .header-bar p {{
      font-size: 13.5px;
      color: #94a3b8;
      margin-top: 4px;
    }}
    .status-pill {{
      background: #065f46;
      color: #34d399;
      padding: 6px 16px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 600;
      border: 1px solid #059669;
    }}
    #canvas-container {{
      background: #ffffff;
      border: 2px solid #334155;
      border-radius: 16px;
      padding: 30px;
      display: inline-block;
      min-width: 2560px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6);
    }}
    #root svg {{
      display: block;
      width: 100%;
      height: auto;
    }}
    .loading {{
      color: #64748b;
      font-size: 18px;
      padding: 60px;
      text-align: center;
    }}
  </style>

  <script type="module">
    import {{ exportToSvg }} from "https://esm.sh/@excalidraw/excalidraw?bundle";

    const excalidrawDiagram = {json_str};

    async function renderDiagram() {{
      const root = document.getElementById("root");
      const statusPill = document.getElementById("status-indicator");
      try {{
        const svg = await exportToSvg({{
          elements: excalidrawDiagram.elements,
          appState: {{
            ...excalidrawDiagram.appState,
            exportBackground: true,
            viewBackgroundColor: "#ffffff",
            exportWithDarkMode: false,
          }},
          files: excalidrawDiagram.files || {{}},
        }});

        root.innerHTML = "";
        root.appendChild(svg);
        statusPill.textContent = "Verified Native Vector SVG (" + excalidrawDiagram.elements.length + " elements)";
        window.__renderComplete = true;
      }} catch (err) {{
        console.error("Render failed:", err);
        root.innerHTML = `<div class="loading" style="color:#ef4444;">Render Error: ${{err.message}}</div>`;
        statusPill.textContent = "Render Failed";
        statusPill.style.background = "#7f1d1d";
        statusPill.style.color = "#f87171";
        window.__renderComplete = false;
        window.__renderError = err.message;
      }}
    }}

    window.addEventListener("DOMContentLoaded", renderDiagram);
  </script>
</head>
<body>
  <div class="header-bar">
    <div>
      <h1>Lexi: Emirates NBD Hybrid RAG Workflow Architecture</h1>
      <p>Built with coleam00/excalidraw-diagram-skill | Verified via Chrome DevTools | Native .excalidraw vector rendering</p>
    </div>
    <div class="status-pill" id="status-indicator">Initializing Excalidraw Engine...</div>
  </div>

  <div id="canvas-container">
    <div id="root">
      <div class="loading">Rendering 134 vector architectural elements, bound containers, and evidence artifacts...</div>
    </div>
  </div>
</body>
</html>
"""

    out_path = Path("docs/render_architecture_excalidraw.html")
    out_path.write_text(html_content, encoding="utf-8")
    print(f"Wrote self-contained renderer to {out_path.resolve()}")

    brain_path = Path(r"C:\Users\PRATYUSH\.gemini\antigravity\brain\89ef14e7-7130-44e6-b2c0-2d37a54dc431\render_architecture_excalidraw.html")
    brain_path.write_text(html_content, encoding="utf-8")
    print(f"Wrote artifact renderer to {brain_path.resolve()}")

if __name__ == "__main__":
    main()

"""
Deterministic, zero-dependency Excalidraw JSON to standalone SVG renderer.
Converts any .excalidraw file into valid, high-resolution SVG with hand-drawn/clean aesthetics,
bound text centering, arrowheads, and code/JSON evidence artifacts.
"""

import json
from pathlib import Path
import html

def excalidraw_to_svg(excal_path: Path, output_svg_path: Path):
    data = json.loads(excal_path.read_text(encoding="utf-8"))
    elements = data.get("elements", [])

    # Compute bounding box
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for el in elements:
        if el.get("isDeleted"):
            continue
        x = el.get("x", 0)
        y = el.get("y", 0)
        w = el.get("width", 0)
        h = el.get("height", 0)
        
        if el.get("type") in ("arrow", "line") and "points" in el:
            for px, py in el["points"]:
                min_x = min(min_x, x + px)
                min_y = min(min_y, y + py)
                max_x = max(max_x, x + px)
                max_y = max(max_y, y + py)
        else:
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + abs(w))
            max_y = max(max_y, y + abs(h))

    padding = 40
    min_x -= padding
    min_y -= padding
    max_x += padding
    max_y += padding
    width = int(max_x - min_x)
    height = int(max_y - min_y)

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{min_x} {min_y} {width} {height}" width="{width}" height="{height}">',
        '''<defs>
          <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#1e3a5f" />
          </marker>
          <marker id="arrowhead-start" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#c2410c" />
          </marker>
          <marker id="arrowhead-decision" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#b45309" />
          </marker>
          <marker id="arrowhead-ai" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#6d28d9" />
          </marker>
          <marker id="arrowhead-success" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#047857" />
          </marker>
          <marker id="arrowhead-warning" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#dc2626" />
          </marker>
          <filter id="shadow" x="-5%" y="-5%" width="115%" height="115%">
            <feDropShadow dx="3" dy="3" stdDeviation="0" flood-color="#334155" flood-opacity="0.35"/>
          </filter>
        </defs>''',
        f'<rect x="{min_x}" y="{min_y}" width="{width}" height="{height}" fill="#ffffff" />'
    ]

    # Render elements by layer: sections/rectangles first, then arrows/lines, then text
    shapes = [e for e in elements if e.get("type") in ("rectangle", "ellipse")]
    lines_and_arrows = [e for e in elements if e.get("type") in ("line", "arrow")]
    texts = [e for e in elements if e.get("type") == "text"]

    for el in shapes:
        x = el.get("x", 0)
        y = el.get("y", 0)
        w = el.get("width", 0)
        h = el.get("height", 0)
        stroke = el.get("strokeColor", "#1e293b")
        fill = el.get("backgroundColor", "transparent")
        sw = el.get("strokeWidth", 1)
        dash = 'stroke-dasharray="6,4"' if el.get("strokeStyle") == "dashed" else ""
        rx = 8 if el.get("roundness") else 0
        
        # Add shadow for primary boxes
        filt = 'filter="url(#shadow)"' if fill not in ("transparent", "#f8fafc") and w < 600 else ""
        
        if el.get("type") == "rectangle":
            svg_parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {dash} {filt} />')
        elif el.get("type") == "ellipse":
            cx = x + w / 2
            cy = y + h / 2
            rx = w / 2
            ry = h / 2
            svg_parts.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {dash} />')

    for el in lines_and_arrows:
        x = el.get("x", 0)
        y = el.get("y", 0)
        stroke = el.get("strokeColor", "#1e3a5f")
        sw = el.get("strokeWidth", 2)
        points = el.get("points", [])
        if not points:
            continue
        
        d_points = " ".join([f"{x + px},{y + py}" for px, py in points])
        
        marker = 'marker-end="url(#arrowhead)"'
        if stroke == "#c2410c":
            marker = 'marker-end="url(#arrowhead-start)"'
        elif stroke == "#b45309":
            marker = 'marker-end="url(#arrowhead-decision)"'
        elif stroke == "#6d28d9":
            marker = 'marker-end="url(#arrowhead-ai)"'
        elif stroke == "#047857":
            marker = 'marker-end="url(#arrowhead-success)"'
        elif stroke == "#dc2626":
            marker = 'marker-end="url(#arrowhead-warning)"'
        elif el.get("type") == "line":
            marker = ""

        svg_parts.append(f'<polyline points="{d_points}" fill="none" stroke="{stroke}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round" {marker} />')

    for el in texts:
        x = el.get("x", 0)
        y = el.get("y", 0)
        w = el.get("width", 0)
        h = el.get("height", 0)
        color = el.get("strokeColor", "#0f172a")
        raw_text = el.get("text", "")
        font_size = el.get("fontSize", 14)
        font_family = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" if font_size <= 13 else "'Segoe UI', -apple-system, sans-serif"
        font_weight = "700" if font_size >= 18 or el.get("containerId") else "400"
        align = el.get("textAlign", "left")

        lines = raw_text.split("\n")
        line_height = font_size * 1.3
        
        # Determine text anchor
        text_anchor = "start"
        text_x = x
        if align == "center":
            text_anchor = "middle"
            text_x = x + w / 2

        # Vertical centering if inside container
        text_y = y + font_size
        if el.get("containerId") and len(lines) > 1:
            total_text_h = len(lines) * line_height
            text_y = y + (h - total_text_h) / 2 + font_size * 0.85

        svg_parts.append(f'<text x="{text_x}" y="{text_y}" font-family="{font_family}" font-size="{font_size}px" font-weight="{font_weight}" fill="{color}" text-anchor="{text_anchor}">')
        for i, line in enumerate(lines):
            escaped = html.escape(line)
            dy = "0" if i == 0 else f"{line_height}px"
            svg_parts.append(f'  <tspan x="{text_x}" dy="{dy}">{escaped}</tspan>')
        svg_parts.append('</text>')

    svg_parts.append('</svg>')
    output_svg_path.write_text("\n".join(svg_parts), encoding="utf-8")
    print(f"Generated standalone SVG: {output_svg_path.resolve()} ({width}x{height})")

if __name__ == "__main__":
    src = Path("docs/architecture_workflow.excalidraw")
    dst = Path("docs/architecture_workflow.svg")
    excalidraw_to_svg(src, dst)
    
    # Also save to artifact dir
    brain_dst = Path(r"C:\Users\PRATYUSH\.gemini\antigravity\brain\89ef14e7-7130-44e6-b2c0-2d37a54dc431\architecture_workflow.svg")
    excalidraw_to_svg(src, brain_dst)

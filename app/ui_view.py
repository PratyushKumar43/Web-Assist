"""Presentation adapter: turns a grounded `ChatResponse` into the chat UI's view model.

The browser is deliberately dumb. It never parses markdown, never resolves a product, and never
invents content: this module does the one job of converting the already-verified answer (markdown)
plus the product catalog into the small, typed payload the UI draws - intro text, a spec grid,
product cards, bullets, sources and quick-reply chips.

Every value here comes from either the grounded answer or `app/catalog.json`, so the UI cannot
display a figure the RAG pipeline did not verify.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.graph.nodes import load_catalog_data
from app.models import ChatResponse, UICard, UIChatResponse, UISpec

_TABLE_LINE = re.compile(r"^\|")
_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")
_BULLET_PREFIXES = ("- ", "* ", "\u2022 ")

# Quick replies stay inside the golden eval set, so every chip is known to route correctly.
_CHIPS_BY_INTENT: Dict[str, List[str]] = {
    "FACT": [
        "What credit cards and commercial cards are available?",
        "Compare Millionaire Account versus standard savings accounts",
        "What cards do you have for business payments?",
    ],
    "DISCOVERY": [
        "What savings and account options can I open?",
        "Compare Millionaire Account versus standard savings accounts",
        "What is the annual fee of U By Emaar Signature Credit Card?",
    ],
    "COMPARISON": [
        "What credit cards and commercial cards are available?",
        "What is the annual fee of U By Emaar Signature Credit Card?",
        "What savings and account options can I open?",
    ],
    "ABOUT": [
        "What credit cards and commercial cards are available?",
        "What savings and account options can I open?",
        "What cards do you have for business payments?",
    ],
    "OUT_OF_SCOPE": [
        "What credit cards and commercial cards are available?",
        "What savings and account options can I open?",
        "Compare Millionaire Account versus standard savings accounts",
    ],
}


def _plain(text: str) -> str:
    """Drop inline markdown from a single cell or line."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return text.strip()


def _parse_blocks(answer: str) -> Tuple[List[str], List[List[str]], List[str]]:
    """Split a markdown answer into (prose lines, first table rows, bullet lines)."""
    prose: List[str] = []
    bullets: List[str] = []
    rows: List[List[str]] = []

    for raw in answer.splitlines():
        line = raw.strip()
        if not line:
            continue

        if _TABLE_LINE.match(line):
            cells = [_plain(cell) for cell in line.strip("|").split("|")]
            if all(_SEPARATOR_CELL.match(cell.replace(" ", "")) for cell in cells if cell):
                continue
            if any(cells):
                rows.append(cells)
            continue

        if line.startswith(_BULLET_PREFIXES):
            bullets.append(_plain(line[2:]))
        elif line.startswith("*") and line.endswith("*") and len(line) > 2:
            # Italic closing question; the quick-reply chips replace it.
            continue
        else:
            prose.append(_plain(line))

    return prose, rows, bullets


def _catalog_by_name() -> Dict[str, Dict[str, Any]]:
    """Index the bundled catalog by lowercase product name."""
    return {p["name"].lower(): p for p in load_catalog_data() if p.get("name")}


def _header_index(header: Sequence[str], *needles: str) -> Optional[int]:
    """Find the first column whose header contains one of `needles`."""
    for idx, cell in enumerate(header):
        if any(needle in cell.lower() for needle in needles):
            return idx
    return None


def _cell(row: Sequence[str], idx: Optional[int], default: str = "") -> str:
    """Read a table cell defensively (short rows are common in scraped tables)."""
    if idx is None or idx >= len(row):
        return default
    return row[idx].strip() or default


def _discovery_cards(
    header: Sequence[str],
    body: Sequence[Sequence[str]],
    catalog: Dict[str, Dict[str, Any]],
) -> List[UICard]:
    """Build product cards from a `Product Name | Category | ...` discovery table."""
    name_idx = _header_index(header, "product name", "name")
    cat_idx = _header_index(header, "category")
    highlight_idx = _header_index(header, "highlight", "reward")
    fee_idx = _header_index(header, "annual fee", "fee")
    req_idx = _header_index(header, "requirement", "salary")

    cards: List[UICard] = []
    for row in body:
        name = _cell(row, name_idx if name_idx is not None else 0)
        if not name:
            continue
        entry = catalog.get(name.lower(), {})
        cards.append(
            UICard(
                name=name,
                category=_cell(row, cat_idx, entry.get("category", "Product")),
                fee=_cell(row, fee_idx, "N/A"),
                requirement=_cell(row, req_idx, "N/A"),
                highlight=_cell(row, highlight_idx, entry.get("summary", "")),
                url=entry.get("url", ""),
            )
        )
    return cards


def _comparison_cards(
    header: Sequence[str],
    body: Sequence[Sequence[str]],
    catalog: Dict[str, Dict[str, Any]],
) -> List[UICard]:
    """Build one card per compared product from a `Feature | A | B` table."""
    def value_for(label: str, column: int) -> str:
        for row in body:
            if row and label in row[0].lower():
                return _cell(row, column)
        return ""

    cards: List[UICard] = []
    for column in (1, 2):
        if column >= len(header) or not header[column]:
            continue
        name = header[column]
        entry = catalog.get(name.lower(), {})
        cards.append(
            UICard(
                name=name,
                category=entry.get("category", "Product"),
                fee=value_for("annual fee", column) or entry.get("annual_fee", "N/A"),
                requirement=value_for("eligibility", column)
                or entry.get("min_requirement", "N/A"),
                highlight=value_for("primary benefit", column) or entry.get("summary", ""),
                url=entry.get("url", ""),
            )
        )
    return cards


def _table_blocks(
    rows: Sequence[Sequence[str]],
    catalog: Dict[str, Dict[str, Any]],
) -> Tuple[List[UISpec], List[UICard], List[str]]:
    """Classify the answer's table and project it onto specs, cards, or bullets."""
    if not rows:
        return [], [], []

    header = list(rows[0])
    body = list(rows[1:])

    if header[0].lower().startswith("detail"):
        specs = [
            UISpec(label=row[0], value=_cell(row, 1, "N/A"))
            for row in body
            if row and row[0]
        ]
        return specs, [], []

    if header[0].lower().startswith("product name"):
        return [], _discovery_cards(header, body, catalog), []

    if header[0].lower().startswith("feature"):
        return [], _comparison_cards(header, body, catalog), []

    return [], [], [" \u2014 ".join(cell for cell in row if cell) for row in body]


def build_ui_payload(response: ChatResponse) -> UIChatResponse:
    """Project a grounded `ChatResponse` onto the UI view model.

    Args:
        response: The verified answer, its citations, and the routed intent.

    Returns:
        A `UIChatResponse` the browser can render without parsing markdown.
    """
    intent = (response.intent or "FACT").upper()
    prose, rows, bullets = _parse_blocks(response.answer)
    catalog = _catalog_by_name()

    specs, cards, table_bullets = _table_blocks(rows, catalog)
    bullets.extend(table_bullets)

    if rows:
        intro = prose[0] if prose else ""
    else:
        intro = " ".join(prose)

    if not intro:
        intro = "Here are the verified options available with Emirates NBD:"

    chips_key = intent if response.answerable else "OUT_OF_SCOPE"

    return UIChatResponse(
        interaction_id=uuid.uuid4().hex[:12],
        intent=intent,
        answerable=response.answerable,
        intro=intro,
        specs=specs,
        cards=cards,
        bullets=bullets,
        sources=response.sources,
        next_chips=_CHIPS_BY_INTENT.get(chips_key, _CHIPS_BY_INTENT["FACT"]),
    )

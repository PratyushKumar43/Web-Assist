"""Synthetic catalog anchor chunks for broad discovery queries.

Pages like "about your products" or "types of credit card" are poor matches for
per-product detail chunks, because those chunks never say "here is the full
catalog". These generated overview chunks give the retriever an anchor document
that enumerates every category and product.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CATALOG_FILE = Path(__file__).resolve().parent / "catalog.json"
if not CATALOG_FILE.exists():
    CATALOG_FILE = Path(__file__).resolve().parent.parent / "data" / "products_catalog.json"

CATALOG_URL = "https://www.emiratesnbd.com/en"
CATALOG_CATEGORY = "general_catalog"


def load_catalog() -> List[Dict[str, Any]]:
    """Load the bundled product catalog from disk."""
    if CATALOG_FILE.exists():
        try:
            return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Error loading catalog from %s: %s", CATALOG_FILE, exc)
    return []


def _slugify(value: str) -> str:
    slug = value.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", slug).strip("-")


def _anchor_chunk(
    chunk_id: str,
    product_name: str,
    title: str,
    text: str,
    section_path: str,
) -> Dict[str, Any]:
    """Build a chunk dict with every field the Qdrant upsert path expects."""
    return {
        "chunk_id": chunk_id,
        "chunk_index": 0,
        "product_id": chunk_id,
        "product_name": product_name,
        "entity_id": chunk_id,
        "parent_id": "banking-services",
        "governing_kfs": "",
        "relations": {},
        "category": CATALOG_CATEGORY,
        "doc_type": "catalog_overview",
        "status": "active",
        "section_path": section_path,
        "url": CATALOG_URL,
        "source_url": CATALOG_URL,
        "title": title,
        "crawled_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        "text": text,
    }


def generate_catalog_overview_chunks(catalog: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Build synthetic catalog anchor chunks: one master overview plus one per category."""
    catalog = catalog if catalog is not None else load_catalog()
    if not catalog:
        return []

    categories: Dict[str, List[Dict[str, Any]]] = {}
    for product in catalog:
        categories.setdefault(product.get("category", "General"), []).append(product)

    # 1. Master overview across every category
    category_names = ", ".join(sorted(categories))
    overview_lines = [
        "Emirates NBD Products & Services — Complete Catalog",
        "",
        "What products and services does Emirates NBD offer? "
        f"Emirates NBD offers {len(catalog)} banking products and services across "
        f"{len(categories)} categories: {category_names}.",
        "",
        "Here is the complete list of all Emirates NBD products, cards, accounts, "
        "services and loans by category:",
    ]
    for category, products in sorted(categories.items()):
        overview_lines.append(f"- {category}: {len(products)}")
        for product in products:
            overview_lines.append(f"  - {product['name']}")
    overview_text = "\n".join(overview_lines)

    chunks: List[Dict[str, Any]] = [
        _anchor_chunk(
            chunk_id="catalog-master-overview",
            product_name="Emirates NBD Product Catalog",
            title="Emirates NBD Product Catalog Overview",
            text=overview_text,
            section_path="Catalog Overview",
        )
    ]

    # 2. One directory chunk per category
    for category, products in sorted(categories.items()):
        lines = [
            f"Emirates NBD {category} — Complete Directory",
            "",
            f"What {category.lower()} does Emirates NBD offer? Emirates NBD offers {len(products)} "
            f"{category} products. Here is the full list of all available {category} with "
            "annual fees, joining fees and eligibility requirements:",
        ]
        for product in products:
            fee = product.get("annual_fee") or "N/A"
            requirement = product.get("min_requirement") or "N/A"
            lines.append(f"- {product['name']}: Annual Fee {fee}, Requirement: {requirement}")
            if product.get("summary"):
                lines.append(f"  {product['summary']}")
        text = "\n".join(lines)

        chunks.append(
            _anchor_chunk(
                chunk_id=f"catalog-directory-{_slugify(category)}",
                product_name=f"Emirates NBD {category} Directory",
                title=f"All {category} | Emirates NBD",
                text=text,
                section_path=f"{category} Directory",
            )
        )

    logger.info("Generated %d catalog anchor chunks.", len(chunks))
    return chunks

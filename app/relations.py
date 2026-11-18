"""Hierarchical Relational Knowledge Graph Engine for Web-Assist.

Provides entity resolution, multi-hop relationship traversal, and regulatory
policy inheritance across products, packages, categories, and Key Facts Statements.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_ONTOLOGY_CACHE: Optional[Dict[str, Any]] = None


def load_ontology() -> Dict[str, Any]:
    """Load the banking entity-relationship ontology from disk with caching."""
    global _ONTOLOGY_CACHE
    if _ONTOLOGY_CACHE is not None:
        return _ONTOLOGY_CACHE

    ontology_path = Path(__file__).resolve().parent / "graph_ontology.json"
    if ontology_path.exists():
        try:
            _ONTOLOGY_CACHE = json.loads(ontology_path.read_text(encoding="utf-8"))
            return _ONTOLOGY_CACHE
        except Exception as exc:
            logger.error("Failed to parse graph_ontology.json: %s", exc)

    return {"entities": {"packages": [], "policies": [], "categories": [], "products": []}}


def get_all_products() -> List[Dict[str, Any]]:
    """Return all defined product entities."""
    return load_ontology().get("entities", {}).get("products", [])


def get_product_by_id(product_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve product metadata by unique identifier."""
    for prod in get_all_products():
        if prod.get("id") == product_id:
            return prod
    return None


def resolve_entity_by_text(text: str) -> Optional[Dict[str, Any]]:
    """Match query text or product name to a known ontology product entity."""
    t_lower = text.lower()
    products = get_all_products()

    # 1. Exact or substring product name match
    for prod in products:
        name = prod.get("name", "").lower()
        pid = prod.get("id", "").lower()
        if name in t_lower or pid in t_lower:
            return prod

    # 2. Token overlap heuristic
    tokens = set(re.findall(r"\w+", t_lower))
    best_match = None
    best_score = 0
    for prod in products:
        prod_tokens = set(re.findall(r"\w+", prod.get("name", "").lower()))
        overlap = len(tokens & prod_tokens)
        if overlap > best_score and overlap >= 2:
            best_score = overlap
            best_match = prod

    return best_match


def get_entity_relations(entity_id: str) -> Dict[str, Any]:
    """Return the relational neighborhood for an entity (category, package, KFS)."""
    ontology = load_ontology()
    entities = ontology.get("entities", {})

    product = get_product_by_id(entity_id)
    if not product:
        return {}

    category_id = product.get("category_id")
    package_id = product.get("package_id")
    kfs_id = product.get("governing_kfs")

    category = next((c for c in entities.get("categories", []) if c.get("id") == category_id), None)
    package = next((p for p in entities.get("packages", []) if p.get("id") == package_id), None)
    kfs = next((k for k in entities.get("policies", []) if k.get("id") == kfs_id), None)

    return {
        "product": product,
        "category": category,
        "package": package,
        "governing_kfs": kfs,
    }


def get_inherited_terms(entity_id: str) -> Dict[str, Any]:
    """Resolve inherited account rules (minimum balance, fall-below fee, exemptions)."""
    relations = get_entity_relations(entity_id)
    product = relations.get("product") or {}
    package = relations.get("package") or {}
    kfs = relations.get("governing_kfs") or {}

    # Check direct product-level inherited terms first
    if product.get("inherited_terms"):
        return product["inherited_terms"]

    # Fall back to governing package
    if package:
        return {
            "min_monthly_balance": package.get("min_average_balance", "AED 3,000"),
            "fall_below_fee": package.get("fall_below_fee", "AED 26.25 per month (inclusive of VAT)"),
            "salary_waiver": "AED 5,000 monthly salary transfer waives the fall-below fee",
            "exemptions": package.get("exemptions", []),
            "governing_package": package.get("name"),
            "governing_document": kfs.get("title") if kfs else "Key Facts Statement (KFS)",
            "document_url": kfs.get("url") if kfs else "https://www.emiratesnbd.com/en/KFS/cash",
        }

    return {}


def format_relational_context_chunk(entity_id: str) -> Optional[Dict[str, Any]]:
    """Format a synthetic relational context chunk containing regulatory & package terms."""
    relations = get_entity_relations(entity_id)
    product = relations.get("product")
    if not product:
        return None

    package = relations.get("package")
    kfs = relations.get("governing_kfs")
    terms = get_inherited_terms(entity_id)

    lines = [
        f"Official Regulatory & Policy Context for: {product.get('name')}",
        f"Product Category: {product.get('category_id')}",
    ]
    if package:
        lines.append(f"Governing Banking Package: {package.get('name')} - {package.get('description', '')}")
    if kfs:
        lines.append(f"Governing Key Facts Statement (KFS): {kfs.get('title')} ({kfs.get('url')})")
        if kfs.get("terms_summary"):
            lines.append(f"Regulatory Terms Summary: {kfs['terms_summary']}")

    if terms:
        lines.append("Baseline Account Requirements & Fee Structure:")
        for k, v in terms.items():
            if k == "exemptions" and isinstance(v, list):
                lines.append("  - Fee Exemptions: " + "; ".join(v))
            elif isinstance(v, str):
                lines.append(f"  - {k.replace('_', ' ').title()}: {v}")

    text_body = "\n".join(lines)
    url = kfs.get("url") if kfs else product.get("url", "https://www.emiratesnbd.com/en")

    return {
        "chunk_id": f"rel_{entity_id}_kfs_policy",
        "text": text_body,
        "product_name": f"{product.get('name')} (Governing Policy)",
        "url": url,
        "score": 0.96,
        "is_relational": True,
        "entity_id": entity_id,
    }

"""Unit tests for the Hierarchical Relational Knowledge Graph Engine."""

import pytest
from app.relations import (
    format_relational_context_chunk,
    get_all_products,
    get_entity_relations,
    get_inherited_terms,
    load_ontology,
    resolve_entity_by_text,
)


def test_load_ontology():
    """Verify ontology loads properly with required entity collections."""
    ontology = load_ontology()
    assert "entities" in ontology
    entities = ontology["entities"]
    assert len(entities.get("packages", [])) >= 1
    assert len(entities.get("policies", [])) >= 1
    assert len(entities.get("categories", [])) >= 1
    assert len(entities.get("products", [])) >= 4


def test_resolve_entity_by_text():
    """Test matching entity from natural language queries."""
    res1 = resolve_entity_by_text("What is the minimum balance for Millionaire Account?")
    assert res1 is not None
    assert res1["id"] == "millionaire-account"

    res2 = resolve_entity_by_text("Tell me about Standard Current Account fees")
    assert res2 is not None
    assert res2["id"] == "standard-current-account"

    res3 = resolve_entity_by_text("U By Emaar Signature Card")
    assert res3 is not None
    assert res3["id"] == "u-by-emaar-signature-credit-card"


def test_get_entity_relations():
    """Test relational neighborhood retrieval for product."""
    relations = get_entity_relations("millionaire-account")
    assert relations["product"] is not None
    assert relations["category"] is not None
    assert relations["category"]["id"] == "savings-accounts"
    assert relations["package"] is not None
    assert relations["package"]["id"] == "package-classic"
    assert relations["governing_kfs"] is not None
    assert relations["governing_kfs"]["id"] == "kfs-cash-accounts"


def test_get_inherited_terms():
    """Test inheritance of regulatory terms (min balance, fall-below fee)."""
    terms = get_inherited_terms("millionaire-account")
    assert "min_monthly_balance" in terms
    assert "AED 3,000" in terms["min_monthly_balance"]
    assert "fall_below_fee" in terms
    assert "AED 26.25" in terms["fall_below_fee"]
    assert "salary_waiver" in terms


def test_format_relational_context_chunk():
    """Test construction of synthetic relational context chunks."""
    chunk = format_relational_context_chunk("millionaire-account")
    assert chunk is not None
    assert chunk["chunk_id"] == "rel_millionaire-account_kfs_policy"
    assert "Key Facts Statement (KFS)" in chunk["text"]
    assert "AED 3,000" in chunk["text"]
    assert "AED 26.25" in chunk["text"]
    assert chunk["is_relational"] is True
    assert chunk["url"] == "https://www.emiratesnbd.com/en/KFS/cash"

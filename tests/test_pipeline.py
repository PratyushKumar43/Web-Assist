"""Tests for Phase 2 & 3: Clean, Catalog, and Chunking Pipeline."""

import pytest
from app.clean import clean_page_content, clean_markdown, normalize_currency
from app.catalog import extract_product_from_page, classify_category, compile_and_save_catalog
from app.chunk import chunk_document, split_into_heading_sections


def test_clean_markdown_currency_normalization():
    """Verify UAE Dirham private unicode \uEAEF is normalized to AED."""
    raw = "The annual fee is \uEAEF 1,575 and joining fee is \uEAEF 525."
    cleaned = normalize_currency(raw)
    assert "AED 1,575" in cleaned
    assert "AED 525" in cleaned
    assert "\uEAEF" not in cleaned


def test_clean_markdown_boilerplate_removal():
    """Verify cookie banners, accessibility widget noise, and spinner links are removed."""
    raw = """
Skip to main content
Enable accessibility for low vision
Open the accessibility menu
# Premium Credit Card
Enjoy unlimited airport lounge access.
Copyright 2026 Bank
    """
    cleaned = clean_markdown(raw)
    assert "# Premium Credit Card" in cleaned
    assert "Enjoy unlimited airport lounge access." in cleaned
    assert "Skip to main content" not in cleaned
    assert "Enable accessibility for low vision" not in cleaned


def test_clean_markdown_preserves_tables():
    """Verify markdown comparison tables remain intact through cleaning."""
    raw = """
# Fee Schedule
| Card Type | Annual Fee | Minimum Salary |
|---|---|---|
| Platinum | AED 500 | AED 10,000 |
| Signature | AED 1,500 | AED 25,000 |
    """
    cleaned = clean_markdown(raw)
    assert "| Card Type | Annual Fee | Minimum Salary |" in cleaned
    assert "| Platinum | AED 500 | AED 10,000 |" in cleaned


def test_classify_category():
    """Verify URL path classification into banking categories."""
    assert classify_category("https://example.com/en/cards/credit-cards/signature", "Signature") == "Credit Cards"
    assert classify_category("https://example.com/en/cards/commercial-cards/mobile", "Mobile") == "Commercial Cards"
    assert classify_category("https://example.com/en/accounts/savings-account", "Savings") == "Savings Accounts"
    assert classify_category("https://example.com/en/loans/home-loan", "Home") == "Home Loans"
    assert classify_category("https://example.com/en/wealth/islamic", "Islamic") == "Islamic Banking"
    assert classify_category("https://example.com/en/other", "Other") == "Banking Services"


def test_extract_product_from_page():
    """Verify regex-based extraction of salary requirements and fees."""
    md = """
# Skywards Infinite Card
Enjoy elite travel privileges across Emirates network.
Minimum salary: AED 30,000
Joining fee: AED 1,050
Annual fee: AED 1,575
    """
    meta = extract_product_from_page("https://example.com/en/cards/skywards", "Skywards Infinite", md)
    assert meta is not None
    assert meta["annual_fee"] == "AED 1,575"
    assert meta["joining_fee"] == "AED 1,050"
    assert "30,000" in meta["min_requirement"]
    assert meta["category"] == "Credit Cards"


def test_compile_and_save_catalog(tmp_path):
    """Verify catalog compilation and JSON persistence."""
    pages = [
        {
            "url": "https://example.com/en/cards/credit-cards/gold-card",
            "title": "Gold Credit Card | Bank",
            "markdown": "# Gold Credit Card\nMinimum salary: AED 10,000\nAnnual fee: AED 300\nGreat card.",
        }
    ]
    catalog_path = str(tmp_path / "catalog.json")
    catalog = compile_and_save_catalog(pages, output_path=catalog_path)
    assert len(catalog) == 1
    assert catalog[0]["product_id"] == "gold-credit-card"
    assert catalog[0]["name"] == "Gold Credit Card"
    assert catalog[0]["category"] == "Credit Cards"
    assert catalog[0]["annual_fee"] == "AED 300"


def test_chunk_document_heading_breadcrumbs():
    """Verify chunker attaches contextual breadcrumbs and keeps chunk bounds."""
    text = """
# Visa Signature Card
Introduction to the premier card.

## Lounge Access
Complimentary access to over 1,000 airport lounges worldwide via LoungeKey.

## Fees & Charges
Annual fee is AED 1,500. Supplementary cards are free.
    """
    page = {
        "url": "https://example.com/en/cards/signature",
        "title": "Visa Signature Card | Bank",
        "markdown": text,
        "crawled_at": "2026-11-18",
    }
    product_meta = {
        "product_id": "visa-signature-card",
        "name": "Visa Signature Card",
        "category": "Credit Cards",
    }
    chunks = chunk_document(page, product_meta=product_meta)

    assert len(chunks) >= 2
    lounge_chunk = next((c for c in chunks if "Lounge Access" in c["section_path"]), None)
    assert lounge_chunk is not None
    assert "Product: Visa Signature Card > Lounge Access" in lounge_chunk["text"]
    assert lounge_chunk["url"] == "https://example.com/en/cards/signature"
    assert lounge_chunk["product_id"] == "visa-signature-card"

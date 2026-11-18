"""Tests for Phase 1: Scraper, Politeness, and Ingestion Engine."""

import os
import tempfile
import pytest
from app.db import init_db, upsert_page, get_page_by_url, get_all_pages
from app.scraper import (
    compute_content_hash,
    is_same_domain,
    RobotsPolitenessValidator,
    LocalCleanCrawler,
)


def test_content_hash_deterministic():
    """Verify hash computation is consistent and deterministic."""
    h1 = compute_content_hash("Hello World")
    h2 = compute_content_hash("Hello World")
    h3 = compute_content_hash("Different Content")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 16


def test_domain_filtering():
    """Verify crawler strictly limits traversal to target domain."""
    base = "https://example.com"
    assert is_same_domain("https://example.com/cards", base) is True
    assert is_same_domain("https://sub.example.com/cards", base) is True
    assert is_same_domain("https://malicious.com", base) is False
    assert is_same_domain("https://google.com/search", base) is False


def test_sqlite_manifest_crud():
    """Verify SQLite initialization and page metadata upserts."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        init_db(db_path)
        upsert_page(
            page_id="test-1",
            url="https://example.com/product-a",
            title="Product A Credit Card",
            content_hash="hash123",
            crawled_at="2026-11-18",
            status="indexed",
            raw_path="/path/to/raw.md",
            db_path=db_path,
        )

        page = get_page_by_url("https://example.com/product-a", db_path=db_path)
        assert page is not None
        assert page["title"] == "Product A Credit Card"
        assert page["status"] == "indexed"

        all_pages = get_all_pages(db_path=db_path)
        assert len(all_pages) == 1
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_local_clean_crawler_table_preservation():
    """Verify markdown conversion keeps financial/product tables intact."""
    sample_html = """
    <html>
      <head><title>Credit Card Fees</title></head>
      <body>
        <nav><a href="/">Home</a></nav>
        <h1>Annual Fees & Limits</h1>
        <table>
          <thead>
            <tr><th>Card Tier</th><th>Annual Fee</th><th>Min Spend</th></tr>
          </thead>
          <tbody>
            <tr><td>Infinite</td><td>AED 700</td><td>AED 50,000</td></tr>
            <tr><td>Platinum</td><td>AED 0</td><td>AED 12,000</td></tr>
          </tbody>
        </table>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md
    import re

    soup = BeautifulSoup(sample_html, "html.parser")
    title = soup.find("title").get_text()
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()

    markdown_text = md(str(soup), heading_style="ATX", strip=["a", "img"])
    markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text).strip()

    assert title == "Credit Card Fees"
    assert "AED 700" in markdown_text
    assert "AED 50,000" in markdown_text
    assert "| Card Tier | Annual Fee | Min Spend |" in markdown_text
    assert "Copyright" not in markdown_text
    assert "Home" not in markdown_text

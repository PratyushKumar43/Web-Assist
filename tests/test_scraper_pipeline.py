"""Unit tests for the Stateful 4-Stage Scraper Pipeline."""

import tempfile
from pathlib import Path

import pytest

from app.scraper_pipeline.audit import generate_audit_report, validate_page_for_rag
from app.scraper_pipeline.discovery import clean_and_normalize_url
from app.scraper_pipeline.extractor import is_content_thin_or_blocked
from app.scraper_pipeline.registry import (
    get_pending_urls,
    get_registry_summary,
    init_registry,
    register_urls,
    update_url_status,
)


@pytest.fixture
def temp_registry_db():
    """Create an isolated temporary SQLite database for registry testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    init_registry(db_path)
    yield db_path
    Path(db_path).unlink(missing_ok=True)


def test_clean_and_normalize_url():
    """Verify URL normalization strips tracking params, fragments, and trailing slashes."""
    base = "https://www.emiratesnbd.com/en"

    # 1. Strips tracking params & trailing slash
    raw = "https://www.emiratesnbd.com/en/accounts/savings/?utm_source=google&utm_medium=cpc&fbclid=123"
    assert clean_and_normalize_url(raw, base) == "https://www.emiratesnbd.com/en/accounts/savings"

    # 2. Strips URL fragments
    raw_frag = "https://www.emiratesnbd.com/en/cards/credit-cards#apply-now"
    assert clean_and_normalize_url(raw_frag, base) == "https://www.emiratesnbd.com/en/cards/credit-cards"

    # 3. Preserves root slash
    assert clean_and_normalize_url("https://www.emiratesnbd.com/", base) == "https://www.emiratesnbd.com/"

    # 4. Filters out external domains
    assert clean_and_normalize_url("https://google.com/search?q=bank", base) is None

    # 5. Filters out binary assets
    assert clean_and_normalize_url("https://www.emiratesnbd.com/brochure.pdf", base) is None
    assert clean_and_normalize_url("https://www.emiratesnbd.com/images/hero.jpg", base) is None


def test_registry_crud_and_resumption(temp_registry_db):
    """Verify atomic state transitions and restart resumption in registry.db."""
    urls = [
        "https://www.emiratesnbd.com/en/accounts",
        "https://www.emiratesnbd.com/en/cards",
        "https://www.emiratesnbd.com/en/loans",
    ]

    # 1. Initial Registration
    added = register_urls(urls, source_tag="test_discovery", db_path=temp_registry_db)
    assert added == 3

    # Duplicate registration should be ignored
    added_dup = register_urls(urls, source_tag="test_discovery", db_path=temp_registry_db)
    assert added_dup == 0

    # 2. Retrieve Pending
    pending = get_pending_urls(limit=2, db_path=temp_registry_db)
    assert len(pending) == 2
    assert pending[0] == urls[0]

    # 3. Mark first URL as SCRAPED
    update_url_status(
        urls[0],
        status="SCRAPED",
        extractor="firecrawl",
        content_hash="abc123hash",
        raw_path="./data/raw/abc123hash.md",
        db_path=temp_registry_db,
    )

    # 4. Mark second URL as FAILED
    update_url_status(
        urls[1],
        status="FAILED",
        extractor="firecrawl",
        error="Connection timeout",
        db_path=temp_registry_db,
    )

    # 5. Verify pending resumption
    # urls[0] is SCRAPED (should not appear)
    # urls[1] is FAILED with retry_count=1 (< max_retries 3, should appear for retry)
    # urls[2] is PENDING (should appear)
    resumed_pending = get_pending_urls(limit=10, max_retries=3, db_path=temp_registry_db)
    assert urls[0] not in resumed_pending
    assert urls[1] in resumed_pending
    assert urls[2] in resumed_pending

    # 6. Verify Summary
    summary = get_registry_summary(temp_registry_db)
    assert summary["total_urls"] == 3
    assert summary["status_counts"]["SCRAPED"] == 1
    assert summary["status_counts"]["FAILED"] == 1
    assert summary["status_counts"]["PENDING"] == 1


def test_is_content_thin_or_blocked():
    """Verify detection of thin text and anti-bot challenge triggers."""
    assert is_content_thin_or_blocked("") is True
    assert is_content_thin_or_blocked("Short snippet under 200 chars") is True
    assert is_content_thin_or_blocked("A" * 300 + " Please enable JavaScript to run this app. " + "B" * 50) is True
    assert is_content_thin_or_blocked("A" * 300 + " Access Denied: 403 Forbidden. " + "B" * 50) is True

    # Valid substantive content
    valid_text = "# Personal Accounts\n\nEmirates NBD provides comprehensive current and savings accounts for individuals and businesses across the UAE with instant online opening and multi-currency support." * 3
    assert is_content_thin_or_blocked(valid_text) is False


def test_quality_gate():
    """Verify Quality Gate validator filters out invalid pages."""
    valid_page = {
        "status": "SCRAPED",
        "markdown": "# Standard Account\n\n" + "Detailed terms, fees, and requirements for the account. " * 15,
        "content_hash": "hash_12345",
    }
    assert validate_page_for_rag(valid_page) is True

    # Failed status rejected
    assert validate_page_for_rag({**valid_page, "status": "FAILED"}) is False

    # Short content rejected
    assert validate_page_for_rag({**valid_page, "markdown": "Too short"}) is False

    # Missing hash rejected
    assert validate_page_for_rag({**valid_page, "content_hash": None}) is False


def test_audit_report_generation(temp_registry_db, tmp_path):
    """Verify audit report generation outputs valid markdown file."""
    urls = ["https://www.emiratesnbd.com/en/test1", "https://www.emiratesnbd.com/en/test2"]
    register_urls(urls, db_path=temp_registry_db)
    update_url_status(urls[0], status="SCRAPED", extractor="firecrawl", db_path=temp_registry_db)

    out_file = tmp_path / "test_audit.md"
    report = generate_audit_report(
        discovery_summary={"base_url": "https://www.emiratesnbd.com/en", "firecrawl_map_count": 5, "sitemap_count": 2, "navigation_crawl_count": 3},
        extraction_summary={"new_links": 2},
        db_path=temp_registry_db,
        output_path=str(out_file),
    )

    assert out_file.exists()
    assert "# Stateful Scraper Pipeline Audit Report" in report
    assert "Total Discovered URLs" in report
    assert "SCRAPED" in report

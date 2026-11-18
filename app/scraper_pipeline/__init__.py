"""Stateful 4-Stage Scraper & Ingestion Pipeline package."""

from app.scraper_pipeline.audit import (
    generate_audit_report,
    index_validated_pages_to_qdrant,
    validate_page_for_rag,
)
from app.scraper_pipeline.discovery import (
    clean_and_normalize_url,
    run_multi_source_discovery,
)
from app.scraper_pipeline.extractor import StatefulExtractor
from app.scraper_pipeline.registry import (
    get_pending_urls,
    get_registry_summary,
    get_scraped_pages,
    init_registry,
    register_urls,
    update_url_status,
)

__all__ = [
    "clean_and_normalize_url",
    "run_multi_source_discovery",
    "init_registry",
    "register_urls",
    "get_pending_urls",
    "update_url_status",
    "get_registry_summary",
    "get_scraped_pages",
    "StatefulExtractor",
    "validate_page_for_rag",
    "index_validated_pages_to_qdrant",
    "generate_audit_report",
]

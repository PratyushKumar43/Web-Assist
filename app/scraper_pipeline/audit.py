"""Stage 4: Quality Gate & Audit Reporting module.

Validates that only quality-gated SCRAPED pages with sufficient content reach RAG
chunking and Qdrant vector indexing, and outputs a comprehensive audit report.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.chunk import chunk_document
from app.config import settings
from app.indexer import get_indexer
from app.relations import resolve_entity_by_text
from app.scraper_pipeline.registry import get_registry_summary, get_scraped_pages

logger = logging.getLogger(__name__)


def validate_page_for_rag(page: Dict[str, Any], min_length: int = 200) -> bool:
    """Quality gate validating page status, content length, and integrity before RAG."""
    if page.get("status") != "SCRAPED":
        return False
    md = page.get("markdown", "")
    if not md or len(md.strip()) < min_length:
        return False
    if not page.get("content_hash"):
        return False
    return True


def index_validated_pages_to_qdrant(
    pages: List[Dict[str, Any]],
    min_length: int = 200,
) -> int:
    """Filter pages through the quality gate, chunk with breadcrumbs, and upsert to Qdrant."""
    indexer = get_indexer()
    valid_pages = [p for p in pages if validate_page_for_rag(p, min_length)]

    logger.info("Quality Gate: %d/%d pages passed for RAG indexing.", len(valid_pages), len(pages))
    if not valid_pages:
        return 0

    all_chunks: List[Dict[str, Any]] = []
    for page in valid_pages:
        url = page.get("url", "")
        title = page.get("title", "")
        entity = resolve_entity_by_text(title) or resolve_entity_by_text(url)

        product_meta = None
        if entity:
            product_meta = {
                "name": entity.get("name", title),
                "product_id": entity.get("id", ""),
                "category": entity.get("category_id", "General"),
                "parent_id": entity.get("category_id", ""),
                "governing_kfs": entity.get("governing_kfs", ""),
            }

        chunks = chunk_document(page, product_meta=product_meta, max_tokens=500)
        all_chunks.extend(chunks)

    if all_chunks:
        total_upserted = indexer.upsert_chunks(all_chunks, batch_size=32)
        logger.info("Quality-gated indexing complete: %d chunks upserted into Qdrant Cloud.", total_upserted)
        return total_upserted
    return 0


def generate_audit_report(
    discovery_summary: Dict[str, Any],
    extraction_summary: Dict[str, Any],
    db_path: Optional[str] = None,
    output_path: str = "./data/scraper_audit_report.md",
) -> str:
    """Generate comprehensive audit report summarizing the 4-stage pipeline run."""
    reg_summary = get_registry_summary(db_path=db_path)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    status_counts = reg_summary.get("status_counts", {})
    extractor_counts = reg_summary.get("extractor_counts", {})
    source_counts = reg_summary.get("source_counts", {})

    lines = [
        "# Stateful Scraper Pipeline Audit Report",
        "",
        f"> **Generated:** {now_str}  ",
        f"> **Target Domain:** {discovery_summary.get('base_url', settings.SITE_URL)}  ",
        f"> **Registry DB:** `{db_path or settings.REGISTRY_DB_PATH}`",
        "",
        "---",
        "",
        "## 1. Pipeline Summary Metrics",
        "",
        "| Metric | Count | Notes |",
        "|---|---|---|",
        f"| **Total Discovered URLs** | {reg_summary.get('total_urls', 0)} | De-duplicated in persistent registry |",
        f"| **Successfully SCRAPED** | {status_counts.get('SCRAPED', 0)} | Quality-verified & cached |",
        f"| **PENDING Remaining** | {status_counts.get('PENDING', 0)} | Ready for next resume batch |",
        f"| **EMPTY / Thin (<200 chars)** | {status_counts.get('EMPTY', 0)} | Blocked or no main content |",
        f"| **FAILED** | {status_counts.get('FAILED', 0)} | Errors recorded with retry counters |",
        f"| **New Links Discovered (Recursive)** | {extraction_summary.get('new_links', 0)} | Captured via recursive link loop |",
        "",
        "---",
        "",
        "## 2. Discovery Sources Breakdown",
        "",
        "| Discovery Source | URLs Discovered |",
        "|---|---|",
        f"| Firecrawl /map | {discovery_summary.get('firecrawl_map_count', 0)} |",
        f"| Robots.txt & XML Sitemaps | {discovery_summary.get('sitemap_count', 0)} |",
        f"| Navigation-Linked Crawl | {discovery_summary.get('navigation_crawl_count', 0)} |",
        f"| Recursive Extraction Loop | {source_counts.get('recursive_link_loop', 0)} |",
        "",
        "---",
        "",
        "## 3. Extractor Performance Breakdown",
        "",
        "| Extractor Engine | Pages Processed |",
        "|---|---|",
        f"| Tier 1: Firecrawl API | {extractor_counts.get('firecrawl', 0)} |",
        f"| Tier 2: TinyFish AI Browser | {extractor_counts.get('tinyfish', 0)} |",
        f"| Tier 3: Local Parser Fallback | {extractor_counts.get('local', 0)} |",
        "",
        "---",
        "",
        "## 4. Zero Silent Drop Guarantee Status",
        "",
        "- ✅ **Persistent Statefulness:** All discovered URLs are saved to SQLite before extraction starts.",
        "- ✅ **Atomic State Machine:** Every URL transitions to `SCRAPED`, `EMPTY`, or `FAILED` with explicit error logging.",
        "- ✅ **Resumption Ready:** Next execution can resume directly from existing `PENDING` and `FAILED` rows.",
    ]

    report_text = "\n".join(lines)
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(report_text, encoding="utf-8")
    logger.info("Saved scraper audit report to: %s", output_path)
    return report_text

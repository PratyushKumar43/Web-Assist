"""Master CLI script to build and index the complete knowledge base into Qdrant."""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.catalog import compile_and_save_catalog
from app.chunk import chunk_document
from app.clean import clean_page_content
from app.config import settings
from app.db import init_db
from app.indexer import QdrantHybridIndexer
from app.scraper import ResilientIngestionEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("build_kb")


def generate_coverage_report(
    catalog: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    output_path: str = "./data/coverage_report.md",
) -> str:
    """Generate markdown audit report verifying 100% product coverage."""
    chunk_counts: Dict[str, int] = {}
    for c in chunks:
        pid = c.get("product_id") or "unclassified"
        chunk_counts[pid] = chunk_counts.get(pid, 0) + 1

    report_lines = [
        "# Knowledge Base Coverage Audit Report",
        "",
        f"> Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "## 1. Summary Metrics",
        "",
        f"- **Total Products Cataloged**: {len(catalog)}",
        f"- **Total Chunks Generated & Indexed**: {len(chunks)}",
        f"- **Storage Backend**: Qdrant Cloud Cluster (`{settings.QDRANT_COLLECTION}`)",
        "",
        "## 2. Product Coverage Breakdown",
        "",
        "| Product Name | Category | Chunks | Annual Fee | Min Requirement | Status |",
        "|---|---|---|---|---|---|",
    ]

    for p in catalog:
        pid = p["product_id"]
        count = chunk_counts.get(pid, 0)
        status = "✅ 100% Covered" if count > 0 else "❌ Missing Chunks"
        af = p.get("annual_fee") or "N/A"
        mr = p.get("min_requirement") or "N/A"
        report_lines.append(
            f"| [{p['name']}]({p['url']}) | {p['category']} | {count} | {af} | {mr} | {status} |"
        )

    report_text = "\n".join(report_lines)
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(report_text, encoding="utf-8")
    return report_text


async def main() -> None:
    parser = argparse.ArgumentParser(description="One-command knowledge base builder.")
    parser.add_argument(
        "--url",
        type=str,
        default=settings.SITE_URL,
        help="Target company website URL",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=12,
        help="Maximum pages to crawl and index",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force re-creation of Qdrant collection",
    )
    args = parser.parse_args()

    print("\n" + "=" * 65)
    print(" WEBSITE RAG KNOWLEDGE BASE BUILDER")
    print(f" Target Site: {args.url}")
    print(f" Destination: Qdrant Cloud ({settings.QDRANT_COLLECTION})")
    print("=" * 65 + "\n")

    # Step 1: Initialize DB
    logger.info("Initializing local SQLite manifest...")
    init_db()

    # Step 2: Ingest Pages
    logger.info("Starting resilient crawl (max %d pages)...", args.max_pages)
    engine = ResilientIngestionEngine(base_url=args.url)
    crawl_report = await engine.crawl_site(max_pages=args.max_pages)
    pages = crawl_report["indexed_pages"]
    logger.info("Successfully fetched %d pages.", len(pages))

    # Step 3: Extract Product Catalog
    logger.info("Compiling product catalog...")
    catalog = compile_and_save_catalog(pages)
    cat_by_url = {p["url"]: p for p in catalog}
    logger.info("Extracted %d distinct products.", len(catalog))

    # Step 4: Heading-Aware Chunking
    logger.info("Chunking pages with contextual breadcrumbs...")
    all_chunks: List[Dict[str, Any]] = []
    for page in pages:
        prod_meta = cat_by_url.get(page["url"])
        page_chunks = chunk_document(page, product_meta=prod_meta)
        all_chunks.extend(page_chunks)
    logger.info("Generated %d total chunks across %d pages.", len(all_chunks), len(pages))

    # Step 5: Upsert into Qdrant Cloud
    logger.info("Connecting to Qdrant and upserting hybrid vectors...")
    indexer = QdrantHybridIndexer()
    indexer.ensure_collection(recreate=args.refresh)
    total_upserted = indexer.upsert_chunks(all_chunks)
    logger.info("Successfully indexed %d chunks in Qdrant Cloud!", total_upserted)

    # Step 6: Generate Coverage Audit Report
    logger.info("Writing coverage audit report...")
    generate_coverage_report(catalog, all_chunks)
    logger.info("Saved coverage report to data/coverage_report.md")

    # Step 7: Verification Probes
    print("\n" + "=" * 65)
    print(" RUNNING VERIFICATION RETRIEVAL PROBES ON QDRANT CLOUD")
    print("=" * 65)

    sample_probes = [
        "What is the annual fee of Skywards Infinite Credit Card?",
        "What is the minimum balance for Millionaire Savings Account?",
        "Corporate Virtual Mobile Card features",
    ]

    for probe in sample_probes:
        print(f"\n🔍 Query: '{probe}'")
        results = indexer.hybrid_search(probe, top_k=2)
        if results:
            top = results[0]
            print(f"   Score: {top.get('score', 0):.4f}")
            print(f"   Source: {top.get('title')} ({top.get('url')})")
            print(f"   Snippet:\n   {top.get('text', '')[:200]}...")
        else:
            print("   No results returned.")

    print("\n" + "=" * 65)
    print(f" ✅ KNOWLEDGE BASE BUILD COMPLETE: {total_upserted} chunks in Qdrant Cloud")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

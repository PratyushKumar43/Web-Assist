"""Master CLI Runner for the Stateful 4-Stage Scraper & Ingestion Pipeline."""

import argparse
import asyncio
import logging
import sys
from typing import Any, Dict

from app.config import settings
from app.scraper_pipeline.audit import (
    generate_audit_report,
    index_validated_pages_to_qdrant,
)
from app.scraper_pipeline.discovery import run_multi_source_discovery
from app.scraper_pipeline.extractor import StatefulExtractor
from app.scraper_pipeline.registry import get_registry_summary, init_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_pipeline")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Stateful 4-Stage Scraper Pipeline CLI.")
    parser.add_argument(
        "--url",
        type=str,
        default=settings.SITE_URL,
        help="Target base domain URL (defaults to SITE_URL in .env)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=10,
        help="Maximum pages to extract in this run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run Stage 1 discovery only and display persistent URL registry counts",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume scraping existing PENDING/FAILED rows without re-running full discovery",
    )
    parser.add_argument(
        "--index",
        action="store_true",
        help="Index quality-gated SCRAPED pages directly into Qdrant Cloud",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=settings.REGISTRY_DB_PATH,
        help="Custom path for registry.db SQLite database",
    )
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print(" 🚀 STATEFUL 4-STAGE SCRAPER & INGESTION PIPELINE")
    print(f" Target Site:    {args.url}")
    print(f" Registry DB:    {args.db_path}")
    print(f" Execution Mode: {'DRY-RUN (Discovery Only)' if args.dry_run else 'FULL EXTRACTION'}")
    print(f" Batch Limit:    {args.max_pages}")
    print("=" * 70 + "\n")

    # Step 0: Ensure registry schema is ready
    init_registry(args.db_path)

    discovery_summary: Dict[str, Any] = {}
    if not args.resume:
        # Stage 1: Multi-Source URL Discovery
        logger.info("Executing Stage 1: Multi-Source URL Discovery...")
        discovery_summary = await run_multi_source_discovery(
            base_url=args.url,
            map_limit=150,
            db_path=args.db_path,
        )
    else:
        logger.info("Resume mode active: skipping Stage 1 initial discovery.")

    # Show registry counts
    reg_summary = get_registry_summary(db_path=args.db_path)
    print("\n" + "-" * 50)
    print(" 📊 URL REGISTRY SUMMARY COUNTS")
    print("-" * 50)
    print(f" Total Registered URLs: {reg_summary['total_urls']}")
    print(" Status Breakdown:")
    for status, count in sorted(reg_summary["status_counts"].items()):
        print(f"   • {status:<10}: {count}")
    if reg_summary["extractor_counts"]:
        print(" Extractor Breakdown:")
        for ext, count in sorted(reg_summary["extractor_counts"].items()):
            print(f"   • {ext:<10}: {count}")
    if reg_summary["source_counts"]:
        print(" Discovery Source Breakdown:")
        for src, count in sorted(reg_summary["source_counts"].items()):
            print(f"   • {src:<20}: {count}")
    print("-" * 50 + "\n")

    if args.dry_run:
        print("✅ Dry-run complete. Discovered URLs are saved in registry.db as PENDING.")
        print("Run without --dry-run to start stateful tiered extraction.")
        return

    # Stage 3: Tiered Extraction & Recursive Link Loop
    logger.info("Executing Stage 3: Tiered Extraction for up to %d pages...", args.max_pages)
    extractor = StatefulExtractor(
        base_url=args.url,
        raw_storage_dir="./data/raw",
        db_path=args.db_path,
    )
    extraction_summary = await extractor.run_batch_extraction(
        batch_limit=args.max_pages,
        rate_limit=settings.CRAWL_RATE_LIMIT,
    )

    # Stage 4: Quality Gate & Optional Qdrant Cloud Indexing
    if args.index and extraction_summary["pages"]:
        logger.info("Executing Stage 4: Quality Gate & Qdrant Cloud Indexing...")
        chunks_indexed = index_validated_pages_to_qdrant(extraction_summary["pages"])
        print(f"✅ Upserted {chunks_indexed} quality-gated chunks to Qdrant Cloud.")

    # Audit Report Generation
    report_md = generate_audit_report(
        discovery_summary=discovery_summary,
        extraction_summary=extraction_summary,
        db_path=args.db_path,
        output_path="./data/scraper_audit_report.md",
    )

    print("\n" + report_md)


if __name__ == "__main__":
    asyncio.run(main())

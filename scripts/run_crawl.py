"""CLI tool to test and execute Phase 1 resilient crawling."""

import argparse
import asyncio
import logging
import sys
from app.config import settings
from app.db import init_db
from app.scraper import ResilientIngestionEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_crawl")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test and execute web crawling for target site.")
    parser.add_argument(
        "--url",
        type=str,
        default=settings.SITE_URL,
        help="Target site URL to crawl (defaults to SITE_URL in .env)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Maximum pages to crawl and index in this run",
    )
    args = parser.parse_args()

    logger.info("Initializing knowledge base SQLite manifest...")
    init_db()

    logger.info("Starting Resilient Ingestion Engine for: %s", args.url)
    engine = ResilientIngestionEngine(base_url=args.url)

    report = await engine.crawl_site(max_pages=args.max_pages)

    print("\n" + "=" * 60)
    print(" CRAWL SUMMARY REPORT")
    print("=" * 60)
    print(f"Target Site:    {report['base_url']}")
    print(f"Total Visited:  {report['total_visited']}")
    print(f"Indexed Pages:  {report['indexed_count']}")
    print(f"Skipped URLs:   {report['skipped_count']}")
    print("-" * 60)
    print("INDEXED PAGES:")
    for page in report["indexed_pages"]:
        print(f"  • [{page['source_engine']}] {page['title'][:40]} -> {page['url']} ({len(page['markdown'])} chars)")
    if report["skipped_urls"]:
        print("-" * 60)
        print("SKIPPED / DISALLOWED URLS:")
        for surl in report["skipped_urls"]:
            print(f"  ✗ {surl}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

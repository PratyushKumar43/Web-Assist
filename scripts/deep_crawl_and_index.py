"""Deep multi-hub crawler and relational knowledge base indexer."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.catalog import compile_and_save_catalog
from app.chunk import chunk_document
from app.clean import clean_page_content
from app.config import settings
from app.indexer import get_indexer
from app.relations import get_entity_relations, resolve_entity_by_text
from app.scraper import FirecrawlCrawler, LocalCleanCrawler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("deep_crawl_and_index")

# Canonical hub targets for deep crawling
TARGET_HUBS = [
    {
        "url": "https://www.emiratesnbd.com/en/KFS/cash",
        "entity_id": "kfs-cash-accounts",
        "name": "Key Facts Statement (KFS) - Current and Savings Accounts",
        "category": "Regulatory Disclosures",
        "parent_id": "banking-services",
        "governing_kfs": "kfs-cash-accounts",
    },
    {
        "url": "https://www.emiratesnbd.com/en/accounts/savings-accounts/savings-account",
        "entity_id": "standard-savings-account",
        "name": "Standard Savings Account",
        "category": "Savings Accounts",
        "parent_id": "savings-accounts",
        "governing_kfs": "kfs-cash-accounts",
    },
    {
        "url": "https://www.emiratesnbd.com/en/accounts/current-accounts/standard-current-account",
        "entity_id": "standard-current-account",
        "name": "Standard Current Account",
        "category": "Current Accounts",
        "parent_id": "current-accounts",
        "governing_kfs": "kfs-cash-accounts",
    },
    {
        "url": "https://www.emiratesnbd.com/en/accounts/current-accounts",
        "entity_id": "current-accounts",
        "name": "Current Accounts Overview",
        "category": "Current Accounts",
        "parent_id": "banking-services",
        "governing_kfs": "kfs-cash-accounts",
    },
    {
        "url": "https://www.emiratesnbd.com/en/accounts/savings-accounts",
        "entity_id": "savings-accounts",
        "name": "Savings Accounts Overview",
        "category": "Savings Accounts",
        "parent_id": "banking-services",
        "governing_kfs": "kfs-cash-accounts",
    },
    {
        "url": "https://www.emiratesnbd.com/en/knowledge-hub/open-a-current-account-online",
        "entity_id": "open-current-account-online-guide",
        "name": "Open Current Account Online UAE – Quick Guide",
        "category": "Knowledge Hub",
        "parent_id": "current-accounts",
        "governing_kfs": "kfs-cash-accounts",
    },
    {
        "url": "https://www.emiratesnbd.com/en/campaigns/millionaire-accounts",
        "entity_id": "millionaire-account",
        "name": "Millionaire Account",
        "category": "Savings Accounts",
        "parent_id": "savings-accounts",
        "governing_kfs": "kfs-cash-accounts",
    },
]


async def run_deep_crawl_and_index():
    """Fetch all canonical hubs, chunk with relational metadata, and upsert to Qdrant."""
    crawler = FirecrawlCrawler()
    local_parser = LocalCleanCrawler()
    indexer = get_indexer()

    all_chunks: List[Dict[str, Any]] = []
    scraped_pages: List[Dict[str, Any]] = []

    for hub in TARGET_HUBS:
        url = hub["url"]
        logger.info("Fetching canonical hub: %s (%s)...", hub["name"], url)

        data = None
        try:
            data = await crawler.extract_markdown(url)
        except Exception as exc:
            logger.warning("Firecrawl failed for %s (%s). Using local parser...", url, exc)

        if not data or not data.get("markdown"):
            data = await local_parser.extract_markdown(url)

        if not data or not data.get("markdown"):
            logger.error("Failed to extract content for %s", url)
            continue

        raw_md = data["markdown"]
        clean_md = clean_page_content(raw_md)
        title = data.get("title") or hub["name"]
        crawled_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        page_record = {
            "url": url,
            "title": title,
            "markdown": clean_md,
            "crawled_at": crawled_at,
        }
        scraped_pages.append(page_record)

        # Build relational product metadata
        product_meta = {
            "name": hub["name"],
            "product_id": hub["entity_id"],
            "entity_id": hub["entity_id"],
            "parent_id": hub["parent_id"],
            "governing_kfs": hub["governing_kfs"],
            "category": hub["category"],
            "relations": {
                "parent": hub["parent_id"],
                "kfs": hub["governing_kfs"],
            },
        }

        chunks = chunk_document(page_record, product_meta=product_meta, max_tokens=500)
        logger.info("Generated %d chunks for '%s'.", len(chunks), hub["name"])
        all_chunks.extend(chunks)

    # Upsert all chunks into Qdrant Cloud
    logger.info("Upserting %d relational chunks into Qdrant Cloud '%s'...", len(all_chunks), settings.QDRANT_COLLECTION)
    total_upserted = indexer.upsert_chunks(all_chunks, batch_size=32)
    logger.info("Successfully upserted %d points to Qdrant Cloud.", total_upserted)

    # Update catalog
    logger.info("Compiling and saving catalog...")
    compile_and_save_catalog(scraped_pages, output_path="./data/products_catalog.json")
    logger.info("Deep crawl and relational indexing completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_deep_crawl_and_index())

"""Stage 3: Tiered Extraction & Recursive Link Loop module.

Extracts content using a two-tier escalation pipeline (Firecrawl -> TinyFish -> Local),
discovers internal domain links recursively, and registers new URLs back into the
persistent URL registry with zero drops.
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.clean import clean_page_content
from app.config import settings
from app.scraper import FirecrawlCrawler, LocalCleanCrawler, TinyFishCrawler
from app.scraper_pipeline.discovery import clean_and_normalize_url
from app.scraper_pipeline.registry import (
    get_pending_urls,
    register_urls,
    update_url_status,
)

logger = logging.getLogger(__name__)

BLOCKED_PATTERNS = [
    "enable javascript to run this app",
    "please enable javascript",
    "access denied",
    "checking your browser",
    "cloudflare turnstile",
    "verify you are human",
    "please enable cookies",
    "security verification",
]


def is_content_thin_or_blocked(markdown: str) -> bool:
    """Detect whether extracted markdown is empty, thin, or an anti-bot challenge."""
    if not markdown or len(markdown.strip()) < 200:
        return True
    md_lower = markdown.lower()
    return any(p in md_lower for p in BLOCKED_PATTERNS)


class StatefulExtractor:
    """Manages two-tier extraction with automatic escalation and recursive link harvesting."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        raw_storage_dir: str = "./data/raw",
        db_path: Optional[str] = None,
    ) -> None:
        self.base_url = base_url or settings.SITE_URL
        self.raw_dir = Path(raw_storage_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path or settings.REGISTRY_DB_PATH
        self.firecrawl = FirecrawlCrawler()
        self.tinyfish = TinyFishCrawler()
        self.local = LocalCleanCrawler()

    async def extract_url(self, url: str) -> Dict[str, Any]:
        """Extract a single URL through Tier 1 (Firecrawl) -> Tier 2 (TinyFish) -> Tier 3 (Local)."""
        logger.info("Extracting URL: %s", url)
        result: Optional[Dict[str, Any]] = None
        extractor_used = "firecrawl"
        error_msg: Optional[str] = None

        # ---------------------------------------------------------------------
        # Tier 1: Firecrawl (Markdown + Links)
        # ---------------------------------------------------------------------
        if self.firecrawl.api_key and not self.firecrawl.api_key.startswith("<"):
            try:
                result = await self.firecrawl.extract_markdown(url)
            except Exception as exc:
                error_msg = f"Firecrawl error: {exc}"
                logger.warning("Tier 1 (Firecrawl) failed for %s (%s). Escalating to Tier 2...", url, exc)

        # Check if Tier 1 returned thin or blocked content
        if not result or is_content_thin_or_blocked(result.get("markdown", "")):
            # -----------------------------------------------------------------
            # Tier 2: TinyFish AI Browser Automation Fallback
            # -----------------------------------------------------------------
            if self.tinyfish.api_key and not self.tinyfish.api_key.startswith("<"):
                logger.info("Escalating to Tier 2 (TinyFish AI) for: %s", url)
                extractor_used = "tinyfish"
                try:
                    result = await self.tinyfish.extract_markdown(url)
                except Exception as exc:
                    error_msg = f"TinyFish error: {exc}"
                    logger.warning("Tier 2 (TinyFish) failed for %s (%s). Falling back to Local...", url, exc)

        # ---------------------------------------------------------------------
        # Tier 3: Local Clean Parser Fallback
        # ---------------------------------------------------------------------
        if not result or is_content_thin_or_blocked(result.get("markdown", "")):
            logger.info("Falling back to Tier 3 (LocalCleanCrawler) for: %s", url)
            extractor_used = "local"
            try:
                result = await self.local.extract_markdown(url)
            except Exception as exc:
                error_msg = f"Local parser error: {exc}"

        # ---------------------------------------------------------------------
        # Recursive Link Loop: Register Newly Discovered In-Page Links
        # ---------------------------------------------------------------------
        discovered_links = result.get("links", []) if result else []
        newly_registered = 0
        if discovered_links:
            normalized_links: Set[str] = set()
            for link in discovered_links:
                norm = clean_and_normalize_url(link, self.base_url)
                if norm and norm != url:
                    normalized_links.add(norm)
            if normalized_links:
                newly_registered = register_urls(
                    sorted(list(normalized_links)),
                    source_tag="recursive_link_loop",
                    db_path=self.db_path,
                )

        # ---------------------------------------------------------------------
        # Status Resolution & State Persistence
        # ---------------------------------------------------------------------
        raw_markdown = result.get("markdown", "") if result else ""
        clean_md = clean_page_content(raw_markdown)

        if not clean_md or is_content_thin_or_blocked(clean_md):
            if result and len(clean_md) < 200:
                logger.warning("URL %s marked EMPTY (content length %d chars < 200).", url, len(clean_md))
                update_url_status(
                    url,
                    status="EMPTY",
                    extractor=extractor_used,
                    error="Content length < 200 chars or blocked",
                    db_path=self.db_path,
                )
                return {"url": url, "status": "EMPTY", "extractor": extractor_used, "new_links": newly_registered}
            else:
                logger.error("URL %s marked FAILED (all extractors failed or error: %s).", url, error_msg)
                update_url_status(
                    url,
                    status="FAILED",
                    extractor=extractor_used,
                    error=error_msg or "Extraction returned no content",
                    db_path=self.db_path,
                )
                return {"url": url, "status": "FAILED", "extractor": extractor_used, "error": error_msg, "new_links": newly_registered}

        # Content is healthy: Save raw cache and update registry to SCRAPED
        content_hash = hashlib.sha256(clean_md.encode("utf-8")).hexdigest()[:16]
        raw_file_path = self.raw_dir / f"{content_hash}.md"
        raw_file_path.write_text(clean_md, encoding="utf-8")

        update_url_status(
            url,
            status="SCRAPED",
            extractor=extractor_used,
            content_hash=content_hash,
            raw_path=str(raw_file_path),
            db_path=self.db_path,
        )

        title = result.get("title") or "Page"
        logger.info(
            "Successfully SCRAPED %s via %s (hash: %s, chars: %d, new_links: %d)",
            url,
            extractor_used,
            content_hash,
            len(clean_md),
            newly_registered,
        )

        return {
            "url": url,
            "status": "SCRAPED",
            "title": title,
            "extractor": extractor_used,
            "content_hash": content_hash,
            "markdown": clean_md,
            "raw_path": str(raw_file_path),
            "new_links": newly_registered,
        }

    async def run_batch_extraction(
        self,
        batch_limit: int = 20,
        rate_limit: float = 1.0,
    ) -> Dict[str, Any]:
        """Process a batch of PENDING and retryable FAILED URLs from the registry."""
        pending_urls = get_pending_urls(limit=batch_limit, db_path=self.db_path)
        if not pending_urls:
            logger.info("No PENDING or retryable FAILED URLs found in registry.")
            return {"processed": 0, "scraped": 0, "empty": 0, "failed": 0, "new_links": 0, "pages": []}

        logger.info("Processing %d pending URLs from registry...", len(pending_urls))
        scraped_pages: List[Dict[str, Any]] = []
        counts = {"scraped": 0, "empty": 0, "failed": 0, "new_links": 0}

        for u in pending_urls:
            res = await self.extract_url(u)
            status = res["status"].lower()
            counts[status] = counts.get(status, 0) + 1
            counts["new_links"] += res.get("new_links", 0)

            if res["status"] == "SCRAPED":
                scraped_pages.append(res)

            await asyncio.sleep(rate_limit)

        return {
            "processed": len(pending_urls),
            "scraped": counts["scraped"],
            "empty": counts["empty"],
            "failed": counts["failed"],
            "new_links": counts["new_links"],
            "pages": scraped_pages,
        }

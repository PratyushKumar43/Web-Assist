"""Resilient web scraping and content extraction engine."""

import abc
import asyncio
import hashlib
import logging
import re
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from app.config import settings
from app.db import upsert_page

logger = logging.getLogger(__name__)


def compute_content_hash(text: str) -> str:
    """Compute deterministic SHA-256 hash of content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def is_same_domain(url: str, base_url: str) -> bool:
    """Verify that candidate URL belongs strictly to the target base domain."""
    base_netloc = urlparse(base_url).netloc.lower()
    target_netloc = urlparse(url).netloc.lower()
    return base_netloc == target_netloc or target_netloc.endswith("." + base_netloc)


class RobotsPolitenessValidator:
    """Validates robots.txt permissions and throttles requests."""

    def __init__(self, base_url: str, rate_limit_seconds: float = 1.0) -> None:
        self.base_url = base_url
        self.rate_limit_seconds = rate_limit_seconds
        self.rp = urllib.robotparser.RobotFileParser()
        self._initialized = False

    async def initialize(self) -> None:
        """Fetch and parse robots.txt asynchronously."""
        robots_url = urljoin(self.base_url, "/robots.txt")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(robots_url, headers={"User-Agent": "WebAssistBot/1.0"})
                if resp.status_code == 200:
                    self.rp.parse(resp.text.splitlines())
                    logger.info("Successfully parsed robots.txt from %s", robots_url)
                else:
                    self.rp.allow_all = True
                    logger.info("robots.txt not found (status %d), permitting all public paths", resp.status_code)
        except Exception as exc:
            logger.warning("Failed to fetch robots.txt (%s), permitting default public paths", exc)
            self.rp.allow_all = True
        self._initialized = True

    def is_allowed(self, url: str) -> bool:
        """Check if path is permitted by robots.txt."""
        if not self._initialized:
            return True
        return self.rp.can_fetch("WebAssistBot/1.0", url)


class BaseCrawler(abc.ABC):
    """Abstract interface for webpage extraction backends."""

    @abc.abstractmethod
    async def extract_markdown(self, url: str) -> Optional[Dict[str, str]]:
        """Extract clean markdown and page title from URL."""
        pass


class FirecrawlCrawler(BaseCrawler):
    """Primary scraper using Firecrawl API."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or settings.FIRECRAWL_API_KEY
        self.endpoint = "https://api.firecrawl.dev/v1/scrape"

    async def extract_markdown(self, url: str) -> Optional[Dict[str, str]]:
        if not self.api_key:
            return None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.endpoint, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("data", {}).get("markdown", "")
                title = data.get("data", {}).get("metadata", {}).get("title", "")
                return {"markdown": content, "title": title}
            raise RuntimeError(f"Firecrawl API error: {resp.status_code} - {resp.text}")


class TinyFishCrawler(BaseCrawler):
    """Fallback scraper using TinyFish AI (TinyFetch API at https://www.tinyfish.ai/)."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or settings.TINYFISH_API_KEY
        self.endpoint = "https://api.fetch.tinyfish.ai"

    async def extract_markdown(self, url: str) -> Optional[Dict[str, str]]:
        if not self.api_key:
            return None
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "urls": [url],
            "format": "markdown",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.endpoint, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    first = results[0]
                    return {
                        "markdown": first.get("text", ""),
                        "title": first.get("title", ""),
                    }
            raise RuntimeError(f"TinyFish AI API error: {resp.status_code} - {resp.text}")


class LocalCleanCrawler(BaseCrawler):
    """Zero-dependency HTML scraper with boilerplate stripping and table preservation."""

    async def extract_markdown(self, url: str) -> Optional[Dict[str, str]]:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WebAssistBot/1.0"}
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract title
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""

            # Remove navigation, scripts, footers, and cookie banners
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
                tag.decompose()

            # Clean markdown conversion with table preservation
            markdown_text = md(
                str(soup),
                heading_style="ATX",
                strip=["a", "img"],
            )
            # Remove excessive empty lines
            markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text).strip()
            return {"markdown": markdown_text, "title": title}


class ResilientIngestionEngine:
    """Orchestrates politeness, primary Firecrawl scraping, and TinyFish AI failover."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        raw_storage_dir: str = "./data/raw",
    ) -> None:
        self.base_url = base_url or settings.SITE_URL
        self.raw_dir = Path(raw_storage_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.politeness = RobotsPolitenessValidator(self.base_url, settings.CRAWL_RATE_LIMIT)
        self.firecrawl = FirecrawlCrawler()
        self.tinyfish = TinyFishCrawler()
        self.local_fallback = LocalCleanCrawler()

    async def initialize(self) -> None:
        """Initialize politeness validator."""
        await self.politeness.initialize()

    async def fetch_page(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch a single page with politeness, failover, and raw caching."""
        if not is_same_domain(url, self.base_url):
            logger.warning("Skipping out-of-domain URL: %s", url)
            return None

        if not self.politeness.is_allowed(url):
            logger.warning("URL disallowed by robots.txt: %s", url)
            upsert_page(
                page_id=compute_content_hash(url),
                url=url,
                title="",
                content_hash="",
                crawled_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                status="skipped",
                skip_reason="robots.txt disallow",
            )
            return None

        # Respect rate limit
        await asyncio.sleep(settings.CRAWL_RATE_LIMIT)

        # 1. Try Firecrawl
        result: Optional[Dict[str, str]] = None
        source_engine = "firecrawl"
        try:
            result = await self.firecrawl.extract_markdown(url)
        except Exception as exc:
            logger.warning("Firecrawl failed for %s (%s). Attempting TinyFish AI fallback...", url, exc)

        # 2. Try TinyFish AI failover
        if not result:
            source_engine = "tinyfish"
            try:
                result = await self.tinyfish.extract_markdown(url)
            except Exception as exc:
                logger.warning("TinyFish AI failed for %s (%s). Using local clean parser...", url, exc)

        # 3. Direct local clean parser fallback
        if not result:
            source_engine = "local_parser"
            result = await self.local_fallback.extract_markdown(url)

        if not result or not result.get("markdown"):
            logger.error("Failed to extract content for %s with all engines.", url)
            return None

        markdown = result["markdown"]
        title = result.get("title") or "Page"
        content_hash = compute_content_hash(markdown)
        crawled_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Cache raw markdown to disk
        raw_file_path = self.raw_dir / f"{content_hash}.md"
        raw_file_path.write_text(markdown, encoding="utf-8")

        # Upsert page metadata to SQLite
        page_id = compute_content_hash(url)
        upsert_page(
            page_id=page_id,
            url=url,
            title=title,
            content_hash=content_hash,
            crawled_at=crawled_at,
            status="indexed",
            raw_path=str(raw_file_path),
        )

        logger.info(
            "Successfully indexed %s via %s (hash: %s, bytes: %d)",
            url,
            source_engine,
            content_hash,
            len(markdown),
        )

        return {
            "page_id": page_id,
            "url": url,
            "title": title,
            "content_hash": content_hash,
            "crawled_at": crawled_at,
            "markdown": markdown,
            "source_engine": source_engine,
            "raw_path": str(raw_file_path),
        }

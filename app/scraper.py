"""Resilient web scraping, URL discovery, and content extraction engine."""

import abc
import asyncio
import hashlib
import logging
import re
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urldefrag, urljoin, urlparse

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
    base_netloc = urlparse(base_url).netloc.lower().lstrip("www.")
    target_netloc = urlparse(url).netloc.lower().lstrip("www.")
    return base_netloc == target_netloc or target_netloc.endswith("." + base_netloc)


def clean_url(url: str) -> str:
    """Normalize URL by stripping fragments and trailing slashes."""
    defragged, _ = urldefrag(url)
    parsed = urlparse(defragged)
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


class RobotsPolitenessValidator:
    """Validates robots.txt permissions and throttles requests."""

    def __init__(self, base_url: str, rate_limit_seconds: float = 1.0) -> None:
        self.base_url = base_url
        self.rate_limit_seconds = rate_limit_seconds
        self.rp = urllib.robotparser.RobotFileParser()
        self.sitemaps: List[str] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Fetch and parse robots.txt asynchronously, discovering declared sitemaps."""
        robots_url = urljoin(self.base_url, "/robots.txt")
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(robots_url, headers={"User-Agent": "WebAssistBot/1.0"})
                if resp.status_code == 200:
                    lines = resp.text.splitlines()
                    self.rp.parse(lines)
                    for line in lines:
                        if line.lower().startswith("sitemap:"):
                            parts = line.split(":", 1)
                            if len(parts) > 1:
                                self.sitemaps.append(parts[1].strip())
                    logger.info("Parsed robots.txt from %s (found %d sitemaps)", robots_url, len(self.sitemaps))
                else:
                    self.rp.allow_all = True
                    logger.info("robots.txt not found (status %d), permitting default paths", resp.status_code)
        except Exception as exc:
            logger.warning("Failed to fetch robots.txt (%s), permitting default paths", exc)
            self.rp.allow_all = True
        self._initialized = True

    def is_allowed(self, url: str) -> bool:
        """Check if URL path is permitted by robots.txt."""
        if not self._initialized:
            return True
        return self.rp.can_fetch("WebAssistBot/1.0", url)


class BaseCrawler(abc.ABC):
    """Abstract interface for webpage extraction backends."""

    @abc.abstractmethod
    async def extract_markdown(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract clean markdown, page title, and optional discovered links."""
        pass


class FirecrawlCrawler(BaseCrawler):
    """Primary scraper using Firecrawl API (https://docs.firecrawl.dev/)."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or settings.FIRECRAWL_API_KEY
        self.scrape_endpoint = "https://api.firecrawl.dev/v1/scrape"
        self.map_endpoint = "https://api.firecrawl.dev/v1/map"

    async def extract_markdown(self, url: str) -> Optional[Dict[str, Any]]:
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
        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post(self.scrape_endpoint, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("data", {}).get("markdown", "")
                title = data.get("data", {}).get("metadata", {}).get("title", "")
                return {"markdown": content, "title": title, "links": []}
            raise RuntimeError(f"Firecrawl API error: {resp.status_code} - {resp.text}")

    async def map_urls(self, base_url: str, limit: int = 50) -> List[str]:
        """Discover URL map from Firecrawl /v1/map endpoint."""
        if not self.api_key:
            return []
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"url": base_url, "limit": limit}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self.map_endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    return resp.json().get("links", [])
        except Exception as exc:
            logger.warning("Firecrawl map call failed: %s", exc)
        return []


class TinyFishCrawler(BaseCrawler):
    """Fallback scraper using TinyFish AI TinyFetch (https://docs.tinyfish.ai/)."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or settings.TINYFISH_API_KEY
        self.endpoint = "https://api.fetch.tinyfish.ai"

    async def extract_markdown(self, url: str) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "urls": [url],
            "format": "markdown",
            "links": True,
            "ttl": 3600,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(self.endpoint, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    first = results[0]
                    return {
                        "markdown": first.get("text", ""),
                        "title": first.get("title", ""),
                        "links": first.get("links", []),
                    }
            raise RuntimeError(f"TinyFish AI API error: {resp.status_code} - {resp.text}")


class LocalCleanCrawler(BaseCrawler):
    """Zero-dependency HTML scraper with boilerplate stripping and table preservation."""

    async def extract_markdown(self, url: str) -> Optional[Dict[str, Any]]:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WebAssistBot/1.0"}
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")

            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""

            # Discover internal links
            links: List[str] = []
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                full_url = urljoin(url, href)
                if is_same_domain(full_url, url):
                    links.append(clean_url(full_url))

            # Strip non-content elements
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
                tag.decompose()

            # Markdown conversion preserving table structure
            markdown_text = md(str(soup), heading_style="ATX", strip=["img"])
            markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text).strip()
            return {"markdown": markdown_text, "title": title, "links": links}


class ResilientIngestionEngine:
    """Orchestrates politeness, multi-engine scraping, URL discovery, and batch crawls."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        raw_storage_dir: str = "./data/raw",
    ) -> None:
        self.base_url = clean_url(base_url or settings.SITE_URL)
        self.raw_dir = Path(raw_storage_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.politeness = RobotsPolitenessValidator(self.base_url, settings.CRAWL_RATE_LIMIT)
        self.firecrawl = FirecrawlCrawler()
        self.tinyfish = TinyFishCrawler()
        self.local_fallback = LocalCleanCrawler()

    async def initialize(self) -> None:
        """Initialize politeness validator."""
        await self.politeness.initialize()

    async def discover_urls(self, limit: int = 50) -> List[str]:
        """Harvest URLs across Firecrawl map, robots.txt sitemaps, and base page extraction."""
        discovered: Set[str] = {self.base_url}

        # 1. Try Firecrawl map
        if self.firecrawl.api_key:
            logger.info("Discovering URLs via Firecrawl /v1/map...")
            mapped_links = await self.firecrawl.map_urls(self.base_url, limit=limit)
            for link in mapped_links:
                if is_same_domain(link, self.base_url):
                    discovered.add(clean_url(link))
            if len(discovered) > 5:
                logger.info("Firecrawl map discovered %d URLs.", len(discovered))
                return sorted(list(discovered))[:limit]

        # 2. Try Sitemaps from robots.txt or default sitemap.xml
        candidate_sitemaps = list(self.politeness.sitemaps) or [urljoin(self.base_url, "/sitemap.xml")]
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for sitemap_url in candidate_sitemaps:
                try:
                    resp = await client.get(sitemap_url)
                    if resp.status_code == 200:
                        root = ET.fromstring(resp.text)
                        # Extract all <loc> elements across namespaces
                        for loc in root.iter():
                            if loc.tag.endswith("loc") and loc.text:
                                text_url = clean_url(loc.text.strip())
                                if is_same_domain(text_url, self.base_url):
                                    discovered.add(text_url)
                except Exception as exc:
                    logger.debug("Sitemap parse error for %s: %s", sitemap_url, exc)

        # 3. Seed from base page scrape (TinyFish or Local)
        if len(discovered) <= 1:
            base_page = await self.fetch_page(self.base_url)
            if base_page and "discovered_links" in base_page:
                for link in base_page["discovered_links"]:
                    if is_same_domain(link, self.base_url):
                        discovered.add(clean_url(link))

        return sorted(list(discovered))[:limit]

    async def fetch_page(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch a single page with politeness, failover, and raw caching."""
        target_url = clean_url(url)
        if not is_same_domain(target_url, self.base_url):
            logger.warning("Skipping out-of-domain URL: %s", target_url)
            return None

        if not self.politeness.is_allowed(target_url):
            logger.warning("URL disallowed by robots.txt: %s", target_url)
            upsert_page(
                page_id=compute_content_hash(target_url),
                url=target_url,
                title="",
                content_hash="",
                crawled_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                status="skipped",
                skip_reason="robots.txt disallow",
            )
            return None

        # Respect rate limit
        await asyncio.sleep(settings.CRAWL_RATE_LIMIT)

        result: Optional[Dict[str, Any]] = None
        source_engine = "firecrawl"

        # 1. Try Firecrawl
        try:
            result = await self.firecrawl.extract_markdown(target_url)
        except Exception as exc:
            logger.warning("Firecrawl failed for %s (%s). Falling back to TinyFish AI...", target_url, exc)

        # 2. Try TinyFish AI fallback
        if not result or not result.get("markdown"):
            source_engine = "tinyfish"
            try:
                result = await self.tinyfish.extract_markdown(target_url)
            except Exception as exc:
                logger.warning("TinyFish AI failed for %s (%s). Falling back to local parser...", target_url, exc)

        # 3. Local clean parser fallback
        if not result or not result.get("markdown"):
            source_engine = "local_parser"
            result = await self.local_fallback.extract_markdown(target_url)

        if not result or not result.get("markdown"):
            logger.error("Failed to extract content for %s with all engines.", target_url)
            return None

        markdown = result["markdown"]
        title = result.get("title") or "Page"
        discovered_links = result.get("links", [])
        content_hash = compute_content_hash(markdown)
        crawled_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Cache raw markdown to disk
        raw_file_path = self.raw_dir / f"{content_hash}.md"
        raw_file_path.write_text(markdown, encoding="utf-8")

        # Upsert page metadata to SQLite
        page_id = compute_content_hash(target_url)
        upsert_page(
            page_id=page_id,
            url=target_url,
            title=title,
            content_hash=content_hash,
            crawled_at=crawled_at,
            status="indexed",
            raw_path=str(raw_file_path),
        )

        logger.info(
            "Indexed %s via %s (hash: %s, chars: %d)",
            target_url,
            source_engine,
            content_hash,
            len(markdown),
        )

        return {
            "page_id": page_id,
            "url": target_url,
            "title": title,
            "content_hash": content_hash,
            "crawled_at": crawled_at,
            "markdown": markdown,
            "source_engine": source_engine,
            "discovered_links": discovered_links,
            "raw_path": str(raw_file_path),
        }

    async def crawl_site(self, max_pages: int = 20) -> Dict[str, Any]:
        """Perform a breadth-first crawl across the target domain up to max_pages."""
        await self.initialize()
        discovered_urls = await self.discover_urls(limit=max_pages * 2)

        queue: List[str] = list(discovered_urls)
        visited: Set[str] = set()
        indexed_pages: List[Dict[str, Any]] = []
        skipped_urls: List[str] = []

        logger.info("Starting site crawl. Discovered %d candidate URLs, max_pages=%d", len(queue), max_pages)

        while queue and len(indexed_pages) < max_pages:
            current_url = queue.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)

            logger.info("Crawling [%d/%d]: %s", len(indexed_pages) + 1, max_pages, current_url)
            page_record = await self.fetch_page(current_url)
            if page_record:
                indexed_pages.append(page_record)
                # Expand queue from newly discovered links
                for new_link in page_record.get("discovered_links", []):
                    clean_link = clean_url(new_link)
                    if clean_link not in visited and clean_link not in queue and is_same_domain(clean_link, self.base_url):
                        queue.append(clean_link)
            else:
                skipped_urls.append(current_url)

        return {
            "base_url": self.base_url,
            "total_visited": len(visited),
            "indexed_count": len(indexed_pages),
            "skipped_count": len(skipped_urls),
            "indexed_pages": indexed_pages,
            "skipped_urls": skipped_urls,
        }

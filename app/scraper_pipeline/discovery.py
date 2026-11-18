"""Stage 1: Multi-Source URL Discovery module.

Discovers URLs from Firecrawl /map, XML Sitemaps (robots.txt), and navigation crawls,
normalizes them (stripping tracking params and trailing slashes), and saves them
to the persistent URL registry as PENDING before scraping.
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Set
from urllib.parse import parse_qsl, urlencode, urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.scraper_pipeline.registry import register_urls

logger = logging.getLogger(__name__)

TRACKING_PARAM_PREFIXES = ("utm_", "fbclid", "gclid", "_ga", "_gl", "mc_", "yclid")
IGNORED_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".css", ".js", ".ico", ".woff", ".woff2", ".ttf", ".eot",
    ".mp4", ".mp3", ".zip", ".tar", ".gz", ".rar", ".exe", ".dmg",
)


def is_same_domain(url: str, base_url: str) -> bool:
    """Verify that candidate URL belongs strictly to the target base domain."""
    base_netloc = urlparse(base_url).netloc.lower().lstrip("www.")
    target_netloc = urlparse(url).netloc.lower().lstrip("www.")
    return base_netloc == target_netloc or target_netloc.endswith("." + base_netloc)


def clean_and_normalize_url(raw_url: str, base_url: str) -> Optional[str]:
    """Normalize URL by stripping fragments, tracking queries, and trailing slashes."""
    if not raw_url or not isinstance(raw_url, str):
        return None

    # Resolve relative URLs
    full_url = urljoin(base_url, raw_url.strip())
    defragged, _ = urldefrag(full_url)
    parsed = urlparse(defragged)

    if parsed.scheme not in ("http", "https"):
        return None

    if not is_same_domain(defragged, base_url):
        return None

    path = parsed.path.lower()
    if any(path.endswith(ext) for ext in IGNORED_EXTENSIONS):
        return None

    # Strip tracking query parameters
    cleaned_params = []
    for k, v in parse_qsl(parsed.query, keep_blank_values=False):
        k_lower = k.lower()
        if any(k_lower.startswith(prefix) for prefix in TRACKING_PARAM_PREFIXES):
            continue
        if k_lower in ("ref", "source", "sessionid", "phpsessid", "jsessionid"):
            continue
        cleaned_params.append((k, v))

    clean_query = urlencode(cleaned_params)

    # Normalize trailing slash: root '/' is kept, subpaths strip trailing slash
    clean_path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
    if not clean_path:
        clean_path = "/"

    netloc = parsed.netloc.lower()
    scheme = parsed.scheme.lower()

    if clean_query:
        return f"{scheme}://{netloc}{clean_path}?{clean_query}"
    return f"{scheme}://{netloc}{clean_path}"


async def discover_via_firecrawl_map(base_url: str, limit: int = 150) -> List[str]:
    """Collect known sitemap and cached URLs via Firecrawl /map endpoint."""
    if not settings.FIRECRAWL_API_KEY or settings.FIRECRAWL_API_KEY.startswith("<"):
        logger.info("Firecrawl API key not set; skipping Firecrawl map discovery.")
        return []

    logger.info("Calling Firecrawl /v1/map on root domain: %s (limit=%d)...", base_url, limit)
    headers = {
        "Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "url": base_url,
        "limit": limit,
        "includeSubdomains": True,
    }

    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post("https://api.firecrawl.dev/v1/map", json=payload, headers=headers)
            if resp.status_code == 200:
                links = resp.json().get("links", [])
                logger.info("Firecrawl /map returned %d raw URLs.", len(links))
                return links
            logger.warning("Firecrawl /map returned status %d: %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.warning("Firecrawl /map request failed (%s). Continuing to next sources.", exc)
    return []


async def discover_via_sitemaps(base_url: str) -> List[str]:
    """Parse declared sitemaps from robots.txt and default /sitemap.xml."""
    discovered: Set[str] = set()
    sitemap_candidates = [urljoin(base_url, "/sitemap.xml"), urljoin(base_url, "/robots.txt")]

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        # Check robots.txt for Sitemap: directives
        try:
            r_resp = await client.get(urljoin(base_url, "/robots.txt"), headers={"User-Agent": "WebAssistBot/1.0"})
            if r_resp.status_code == 200:
                for line in r_resp.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sm_url = line.split(":", 1)[1].strip()
                        if sm_url not in sitemap_candidates:
                            sitemap_candidates.append(sm_url)
        except Exception as exc:
            logger.debug("Robots.txt check error: %s", exc)

        for sitemap_url in sitemap_candidates:
            if not sitemap_url.endswith(".xml"):
                continue
            try:
                resp = await client.get(sitemap_url)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.text)
                    for elem in root.iter():
                        if elem.tag.endswith("loc") and elem.text:
                            loc_url = elem.text.strip()
                            if is_same_domain(loc_url, base_url):
                                discovered.add(loc_url)
            except Exception as exc:
                logger.debug("Failed parsing sitemap %s: %s", sitemap_url, exc)

    logger.info("Sitemap discovery collected %d URLs.", len(discovered))
    return list(discovered)


async def discover_via_navigation_crawl(base_url: str, max_depth_pages: int = 15) -> List[str]:
    """Fast URL-only navigation crawler to catch linked pages missing from sitemaps."""
    discovered: Set[str] = {base_url}
    visited: Set[str] = set()
    queue: List[str] = [base_url]

    logger.info("Running fast URL-only navigation crawl (max_depth_pages=%d)...", max_depth_pages)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WebAssistBot/1.0"}

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=headers) as client:
        while queue and len(visited) < max_depth_pages:
            curr = queue.pop(0)
            if curr in visited:
                continue
            visited.add(curr)

            try:
                resp = await client.get(curr)
                if resp.status_code != 200 or "text/html" not in resp.headers.get("content-type", ""):
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    norm = clean_and_normalize_url(a["href"], base_url)
                    if norm and norm not in discovered:
                        discovered.add(norm)
                        if len(queue) < max_depth_pages * 3:
                            queue.append(norm)
            except Exception as exc:
                logger.debug("Navigation crawl skipped %s (%s)", curr, exc)

    logger.info("Navigation crawl discovered %d unique links from %d visited pages.", len(discovered), len(visited))
    return list(discovered)


async def run_multi_source_discovery(
    base_url: Optional[str] = None,
    map_limit: int = 150,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute Stage 1: multi-source discovery and save all normalized URLs to registry.db."""
    target_base = base_url or settings.SITE_URL

    logger.info("=== STAGE 1: MULTI-SOURCE URL DISCOVERY (%s) ===", target_base)

    # Execute all 3 discovery sources
    fc_task = discover_via_firecrawl_map(target_base, limit=map_limit)
    sm_task = discover_via_sitemaps(target_base)
    nav_task = discover_via_navigation_crawl(target_base, max_depth_pages=15)

    fc_urls, sm_urls, nav_urls = await asyncio.gather(fc_task, sm_task, nav_task)

    # Normalize all URLs
    normalized_all: Set[str] = set()
    for u in fc_urls + sm_urls + nav_urls + [target_base]:
        cleaned = clean_and_normalize_url(u, target_base)
        if cleaned:
            normalized_all.add(cleaned)

    # Save to persistent SQLite URL registry
    new_count = register_urls(sorted(list(normalized_all)), source_tag="stage1_discovery", db_path=db_path)

    summary = {
        "base_url": target_base,
        "firecrawl_map_count": len(fc_urls),
        "sitemap_count": len(sm_urls),
        "navigation_crawl_count": len(nav_urls),
        "total_unique_discovered": len(normalized_all),
        "newly_registered_pending": new_count,
    }
    logger.info(
        "Discovery complete: %d unique URLs normalized, %d newly registered into registry.db.",
        len(normalized_all),
        new_count,
    )
    return summary

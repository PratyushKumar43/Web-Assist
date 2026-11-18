"""Agentic live website search and on-demand ingestion tool."""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from app.catalog import extract_product_from_page
from app.chunk import chunk_document
from app.clean import clean_page_content
from app.config import settings
from app.indexer import get_indexer
from app.scraper import FirecrawlCrawler, TinyFishCrawler, is_same_domain

logger = logging.getLogger(__name__)

# Cached sitemap / discovered links for fast on-demand matching
_site_mapped_links: List[str] = []


def search_site_urls(query: str, domain_url: Optional[str] = None) -> List[str]:
    """Find live website URLs on the target domain matching the user's query keywords."""
    global _site_mapped_links
    root_url = domain_url or settings.SITE_URL

    query_tokens = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2 and t.lower() not in ["the", "and", "about", "for", "with", "what", "are", "benefits", "emirates", "nbd", "bank"]]
    if not query_tokens:
        query_tokens = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]

    def score_url(url: str) -> int:
        u_lower = url.lower()
        score = sum(4 for t in query_tokens if t in u_lower or t.rstrip("s") in u_lower)
        # Boost product-bearing sections
        if any(p in u_lower for p in ["/wealth/", "/accounts/", "/cards/", "/loans/", "/investments/", "/business-banking/"]):
            score += 5
        # Penalize press releases, media center, sponsorships, and merchant discount deals
        if any(p in u_lower for p in ["/media-center/", "/deals/", "/cio-corner/", "/careers/", "/campaigns/"]):
            score -= 4
        return score

    # 1. Check if we already have links cached in memory
    matched: List[str] = []
    if _site_mapped_links:
        for link in _site_mapped_links:
            link_lower = link.lower()
            if any(t in link_lower for t in query_tokens):
                matched.append(link)
        if matched:
            matched.sort(key=score_url, reverse=True)
            return matched[:5]

    # 2. Query Firecrawl /v1/map with search parameter
    if settings.FIRECRAWL_API_KEY:
        try:
            search_term = " ".join(query_tokens[:3])
            logger.info("Executing Firecrawl map discovery for: '%s'", search_term)
            headers = {
                "Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            }
            resp = httpx.post(
                "https://api.firecrawl.dev/v1/map",
                headers=headers,
                json={"url": root_url, "search": search_term},
                timeout=20.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                links = data.get("links", [])
                for link in links:
                    if is_same_domain(link, root_url) and not link.endswith((".pdf", ".jpg", ".png")):
                        if link not in _site_mapped_links:
                            _site_mapped_links.append(link)
                        link_lower = link.lower()
                        if any(t in link_lower for t in query_tokens):
                            matched.append(link)

                if matched:
                    matched.sort(key=score_url, reverse=True)
                    return matched[:5]
        except Exception as e:
            logger.warning("Firecrawl map live search failed: %s", e)

    # 3. Direct heuristic paths on known bank structures
    slug = "-".join(query_tokens[:3])
    candidates = [
        f"{root_url.rstrip('/')}/wealth/{slug}",
        f"{root_url.rstrip('/')}/accounts/{slug}",
        f"{root_url.rstrip('/')}/cards/{slug}",
        f"{root_url.rstrip('/')}/investments/{slug}",
    ]
    return candidates


async def live_site_search_and_ingest(query: str) -> List[Dict[str, Any]]:
    """Dynamically discover, scrape, and index a missing page from the target site."""
    logger.info("Agentic Tool Triggered: Searching live website for: '%s'", query)
    candidate_urls = search_site_urls(query)
    if not candidate_urls:
        logger.warning("No candidate live URLs found on site for query: '%s'", query)
        return []

    # Scraper instances
    firecrawl = FirecrawlCrawler() if settings.FIRECRAWL_API_KEY else None
    tinyfish = TinyFishCrawler() if settings.TINYFISH_API_KEY else None
    indexer = get_indexer()

    for url in candidate_urls[:3]:
        logger.info("Attempting on-demand live fetch for: %s", url)
        res = None

        # Try Firecrawl
        if firecrawl and settings.FIRECRAWL_API_KEY:
            try:
                res = await firecrawl.extract_markdown(url)
            except Exception as e:
                logger.warning("Firecrawl scrape failed for %s: %s", url, e)

        # Failover to TinyFish
        if not res and tinyfish and settings.TINYFISH_API_KEY:
            try:
                res = await tinyfish.extract_markdown(url)
            except Exception as e:
                logger.warning("TinyFish scrape failed for %s: %s", url, e)

        if res and res.get("markdown") and len(res["markdown"]) > 100:
            md_content = res["markdown"]
            page_title = res.get("title") or url
            logger.info("Successfully fetched %d chars from %s. Processing on-demand chunks...", len(md_content), url)

            # Product extraction
            product_meta = extract_product_from_page(
                page_url=url,
                title=page_title,
                markdown=md_content,
            )

            # Chunking with contextual breadcrumbs
            import datetime
            page_dict = {
                "url": url,
                "title": page_title,
                "markdown": md_content,
                "crawled_at": datetime.date.today().isoformat(),
            }
            new_chunks = chunk_document(page_dict, product_meta=product_meta)

            if new_chunks:
                # Upsert into Qdrant Cloud dynamically
                logger.info("Dynamically indexing %d chunks into Qdrant Cloud for: %s", len(new_chunks), url)
                indexer.upsert_chunks(new_chunks)

                # Return the newly created chunks directly
                for c in new_chunks:
                    c["score"] = 1.0  # Freshly fetched live match
                return new_chunks

    logger.warning("Could not ingest any live candidate page for query: '%s'", query)
    return []

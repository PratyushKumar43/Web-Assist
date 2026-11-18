"""Persistent URL Registry module for stateful, fault-tolerant web scraping.

Maintains URL lifecycle states (PENDING, SCRAPED, EMPTY, FAILED) across runs,
guaranteeing zero silent drops and clean restart/resumption capability.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


def get_registry_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open or create connection to the SQLite URL registry database."""
    target_path = Path(db_path or settings.REGISTRY_DB_PATH)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_registry(db_path: Optional[str] = None) -> None:
    """Initialize the persistent URL registry schema."""
    conn = get_registry_conn(db_path)
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS urls (
                url TEXT PRIMARY KEY,
                status TEXT NOT NULL, -- PENDING, SCRAPED, EMPTY, FAILED
                extractor TEXT,        -- firecrawl, tinyfish, local
                content_hash TEXT,
                retry_count INTEGER DEFAULT 0,
                last_error TEXT,
                discovered_at TEXT NOT NULL,
                scraped_at TEXT,
                raw_path TEXT,
                source_tag TEXT DEFAULT 'discovery'
            );

            CREATE INDEX IF NOT EXISTS idx_urls_status ON urls (status);
            CREATE INDEX IF NOT EXISTS idx_urls_extractor ON urls (extractor);
        """)
    conn.close()
    logger.info("URL Registry database initialized at: %s", db_path or settings.REGISTRY_DB_PATH)


def register_urls(
    urls: List[str],
    source_tag: str = "discovery",
    db_path: Optional[str] = None,
) -> int:
    """Bulk-register discovered URLs with PENDING status. Returns number of newly added URLs."""
    if not urls:
        return 0

    init_registry(db_path)
    conn = get_registry_conn(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    newly_added = 0

    with conn:
        cursor = conn.cursor()
        for u in urls:
            cursor.execute(
                """
                INSERT OR IGNORE INTO urls (url, status, discovered_at, source_tag)
                VALUES (?, 'PENDING', ?, ?)
                """,
                (u, now_iso, source_tag),
            )
            if cursor.rowcount > 0:
                newly_added += 1

    conn.close()
    if newly_added > 0:
        logger.info("Registered %d new URLs (source: %s).", newly_added, source_tag)
    return newly_added


def get_pending_urls(
    limit: int = 50,
    max_retries: int = 3,
    db_path: Optional[str] = None,
) -> List[str]:
    """Retrieve URLs ready for extraction (PENDING or retryable FAILED)."""
    init_registry(db_path)
    conn = get_registry_conn(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT url FROM urls
        WHERE status = 'PENDING'
           OR (status = 'FAILED' AND retry_count < ?)
        ORDER BY retry_count ASC, discovered_at ASC
        LIMIT ?
        """,
        (max_retries, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [row["url"] for row in rows]


def update_url_status(
    url: str,
    status: str,
    extractor: Optional[str] = None,
    content_hash: Optional[str] = None,
    error: Optional[str] = None,
    raw_path: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    """Atomically update status, extractor, and metadata for a URL."""
    conn = get_registry_conn(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()

    with conn:
        if status == "FAILED":
            conn.execute(
                """
                UPDATE urls
                SET status = ?,
                    extractor = COALESCE(?, extractor),
                    last_error = ?,
                    retry_count = retry_count + 1,
                    scraped_at = ?
                WHERE url = ?
                """,
                (status, extractor, error, now_iso, url),
            )
        else:
            conn.execute(
                """
                UPDATE urls
                SET status = ?,
                    extractor = COALESCE(?, extractor),
                    content_hash = COALESCE(?, content_hash),
                    last_error = ?,
                    raw_path = COALESCE(?, raw_path),
                    scraped_at = ?
                WHERE url = ?
                """,
                (status, extractor, content_hash, error, raw_path, now_iso, url),
            )
    conn.close()


def get_registry_summary(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Return aggregated metrics across the URL registry."""
    init_registry(db_path)
    conn = get_registry_conn(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM urls")
    total = cursor.fetchone()["total"]

    cursor.execute("SELECT status, COUNT(*) as count FROM urls GROUP BY status")
    status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}

    cursor.execute("SELECT extractor, COUNT(*) as count FROM urls WHERE extractor IS NOT NULL GROUP BY extractor")
    extractor_counts = {row["extractor"]: row["count"] for row in cursor.fetchall()}

    cursor.execute("SELECT source_tag, COUNT(*) as count FROM urls GROUP BY source_tag")
    source_counts = {row["source_tag"]: row["count"] for row in cursor.fetchall()}

    conn.close()
    return {
        "total_urls": total,
        "status_counts": status_counts,
        "extractor_counts": extractor_counts,
        "source_counts": source_counts,
    }


def get_scraped_pages(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all successfully scraped page records for quality gating and RAG."""
    init_registry(db_path)
    conn = get_registry_conn(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT url, status, extractor, content_hash, raw_path, scraped_at
        FROM urls
        WHERE status = 'SCRAPED'
        ORDER BY scraped_at ASC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

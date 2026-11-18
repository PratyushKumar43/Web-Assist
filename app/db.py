"""SQLite manifest and metadata persistence layer."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models import CrawledPageRecord, ProductItem

logger = logging.getLogger(__name__)


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Get an active SQLite connection, creating parent folders if needed."""
    path = Path(db_path or settings.SQLITE_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database tables for pages, products, chunks, and sessions."""
    conn = get_db_connection(db_path)
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pages (
                id TEXT PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                crawled_at TEXT NOT NULL,
                status TEXT NOT NULL,
                skip_reason TEXT,
                raw_path TEXT
            );

            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                url TEXT NOT NULL,
                page_id TEXT,
                FOREIGN KEY (page_id) REFERENCES pages (id)
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                page_id TEXT NOT NULL,
                product_id TEXT,
                section_path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                FOREIGN KEY (page_id) REFERENCES pages (id)
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources_json TEXT,
                answerable INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations (id)
            );
        """)
    conn.close()
    logger.info("SQLite database initialized successfully.")


def upsert_page(
    page_id: str,
    url: str,
    title: str,
    content_hash: str,
    crawled_at: str,
    status: str = "indexed",
    skip_reason: Optional[str] = None,
    raw_path: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    """Insert or update a crawled page record."""
    conn = get_db_connection(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO pages (id, url, title, content_hash, crawled_at, status, skip_reason, raw_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title,
                content_hash=excluded.content_hash,
                crawled_at=excluded.crawled_at,
                status=excluded.status,
                skip_reason=excluded.skip_reason,
                raw_path=excluded.raw_path;
            """,
            (page_id, url, title, content_hash, crawled_at, status, skip_reason, raw_path),
        )
    conn.close()


def get_page_by_url(url: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve page metadata by canonical URL."""
    conn = get_db_connection(db_path)
    cur = conn.execute("SELECT * FROM pages WHERE url = ?", (url,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_pages(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all recorded pages in the knowledge base."""
    conn = get_db_connection(db_path)
    cur = conn.execute("SELECT * FROM pages ORDER BY crawled_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def upsert_product(
    product_id: str,
    name: str,
    category: str,
    url: str,
    page_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    """Insert or update a product catalog entry."""
    conn = get_db_connection(db_path)
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO products (id, name, category, url, page_id)
            VALUES (?, ?, ?, ?, ?);
            """,
            (product_id, name, category, url, page_id),
        )
    conn.close()


def get_all_products(db_path: Optional[str] = None) -> List[ProductItem]:
    """Fetch all products in the catalog."""
    conn = get_db_connection(db_path)
    cur = conn.execute("SELECT name, category, url, page_id FROM products ORDER BY category, name")
    rows = cur.fetchall()
    conn.close()
    return [
        ProductItem(
            name=row["name"],
            category=row["category"],
            url=row["url"],
            page_id=row["page_id"],
        )
        for row in rows
    ]

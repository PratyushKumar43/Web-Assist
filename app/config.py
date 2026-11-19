"""Application configuration using Pydantic Settings."""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Explicitly load .env file into os.environ if present
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)


class Settings(BaseSettings):
    """Central configuration validated via Pydantic v2."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 1. Target Website (Strictly Confidential)
    SITE_URL: str = Field(
        default="https://example.com",
        description="Root URL of the target website to crawl.",
    )
    CRAWL_RATE_LIMIT: float = Field(
        default=1.0,
        description="Polite request rate limit in seconds between requests.",
    )

    # 2. LLM Providers (xAI Grok / Google Gemini / OpenRouter)
    XAI_API_KEY: Optional[str] = Field(
        default=None,
        description="xAI API key for Grok models (https://console.x.ai/).",
    )
    XAI_MODEL: str = Field(
        default="grok-build-0.1",
        description="xAI Grok model name used for chat generation (e.g. grok-build-0.1, grok-4.5).",
    )
    XAI_BASE_URL: str = Field(
        default="https://api.x.ai/v1",
        description="xAI API base endpoint.",
    )

    OPENROUTER_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenRouter API key for free/commercial LLMs (https://openrouter.ai/).",
    )
    OPENROUTER_MODEL: str = Field(
        default="meta-llama/llama-3.3-70b-instruct:free",
        description="Default OpenRouter model to invoke.",
    )
    OPENROUTER_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL.",
    )

    GEMINI_API_KEY: str = Field(
        default="",
        description="Google Gemini API key for embeddings and generation.",
    )
    GEMINI_MODEL: str = Field(
        default="gemini-2.0-flash",
        description="Primary LLM for query rewriting and answer generation.",
    )
    EMBEDDING_MODEL: str = Field(
        default="gemini-embedding-001",
        description="Dense embedding model (768 dimensions).",
    )
    EMBEDDING_DIM: int = Field(
        default=768,
        description="Dimension size of dense embeddings.",
    )

    # 3. Web Crawling & Scraping Ingestion
    FIRECRAWL_API_KEY: Optional[str] = Field(
        default=None,
        description="API key for Firecrawl primary scraper.",
    )
    TINYFISH_API_KEY: Optional[str] = Field(
        default=None,
        description="API key for TinyFish AI fallback scraper (https://www.tinyfish.ai/).",
    )

    # 4. Vector Database (Qdrant Dual Parity)
    QDRANT_URL: Optional[str] = Field(
        default=None,
        description="Qdrant Cloud endpoint URL (if empty, uses local embedded storage).",
    )
    QDRANT_API_KEY: Optional[str] = Field(
        default=None,
        description="Qdrant Cloud API key.",
    )
    QDRANT_COLLECTION: str = Field(
        default="site_kb",
        description="Name of the Qdrant vector collection.",
    )
    QDRANT_LOCAL_PATH: str = Field(
        default="./data/qdrant_data",
        description="Path for local embedded Qdrant storage.",
    )

    # 5. Local SQLite Manifest & URL Registry
    SQLITE_DB_PATH: str = Field(
        default="./data/kb.db",
        description="Path for SQLite database storing pages, products, and chunks manifest.",
    )
    REGISTRY_DB_PATH: str = Field(
        default="./data/registry.db",
        description="Path for persistent SQLite URL registry.",
    )

    # 6. Guardrails & Thresholds
    MIN_RELEVANCE_SCORE: float = Field(
        default=0.35,
        description="Minimum RRF score threshold to pass the relevance gate.",
    )
    SEMANTIC_SIMILARITY_MIN: float = Field(
        default=0.65,
        description="Minimum cosine similarity for pure dense retrieval chunks.",
    )
    TOP_K: int = Field(
        default=6,
        description="Number of chunks retrieved per query turn.",
    )
    STRICT_NUMBER_CHECK: bool = Field(
        default=True,
        description="Ensure all numbers/fees in generated answers match context verbatim.",
    )

    # 7. Environment Detection
    VERCEL: Optional[str] = Field(
        default=None,
        description="Automatically set by Vercel deployment environment.",
    )

    @property
    def is_cloud(self) -> bool:
        """Check whether app is running in cloud/serverless environment."""
        return bool(self.VERCEL or self.QDRANT_URL)


settings = Settings()

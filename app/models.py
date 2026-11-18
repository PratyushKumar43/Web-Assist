"""Canonical Pydantic v2 schemas and data contracts."""

from typing import List, Optional
from pydantic import BaseModel, Field


class SourceItem(BaseModel):
    """Verified source citation constructed server-side."""

    title: str = Field(description="Title of the source webpage.")
    url: str = Field(description="Canonical URL of the source webpage.")
    last_crawled: str = Field(description="Date the page was last crawled (YYYY-MM-DD).")


class ChatRequest(BaseModel):
    """Incoming user chat query."""

    session_id: str = Field(
        default="default-session",
        description="Unique UUID identifying the chat conversation thread.",
    )
    message: str = Field(
        min_length=1,
        max_length=2000,
        description="User question or prompt (1 to 2000 characters).",
    )


class ChatResponse(BaseModel):
    """Outgoing structured response from the chatbot."""

    answer: str = Field(description="Grounded answer text or polite fallback.")
    sources: List[SourceItem] = Field(
        default_factory=list,
        description="List of verified source citations.",
    )
    answerable: bool = Field(
        default=True,
        description="True if answered from site context; False if fallen back.",
    )
    intent: str = Field(
        default="FACT",
        description="Classified user intent: FACT, DISCOVERY, COMPARISON, or OUT_OF_SCOPE.",
    )
    products_in_context: List[str] = Field(
        default_factory=list,
        description="Names of products referenced or discussed in this turn.",
    )


class HealthResponse(BaseModel):
    """API health status and runtime information."""

    status: str = Field(default="ok", description="Server operational health.")
    environment: str = Field(description="'vercel' if cloud serverless, 'local' otherwise.")
    kb_status: str = Field(description="Knowledge base availability status.")


class ProductItem(BaseModel):
    """Product catalog entry."""

    name: str = Field(description="Exact product or service name.")
    category: str = Field(description="Product category (e.g. Credit Cards, Accounts, Loans).")
    url: str = Field(description="URL to the product page on the company website.")
    page_id: Optional[str] = Field(default=None, description="Internal page record ID.")


class LLMAnswerOutput(BaseModel):
    """Structured JSON schema enforced during Gemini generation."""

    answerable: bool = Field(
        description="True if context has sufficient information to answer; False otherwise.",
    )
    answer: str = Field(
        description="Grounded answer containing exact figures and conditions, or concise refusal.",
    )
    used_chunk_ids: List[str] = Field(
        default_factory=list,
        description="List of context chunk IDs directly used to formulate the answer.",
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Short 1-sentence explanation of answerability or refusal.",
    )


class CrawledPageRecord(BaseModel):
    """Database record for a crawled or scraped webpage."""

    id: str
    url: str
    title: str
    content_hash: str
    crawled_at: str
    status: str = "indexed"  # "indexed", "skipped", "error"
    skip_reason: Optional[str] = None
    markdown_content: Optional[str] = None


class ChunkRecord(BaseModel):
    """Individual heading-aware text chunk."""

    id: str
    page_id: str
    product_id: Optional[str] = None
    section_path: str
    chunk_index: int
    text: str
    content_hash: str

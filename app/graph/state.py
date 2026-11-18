"""LangGraph state definition for Website RAG Chatbot."""

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class ChatState(TypedDict, total=False):
    """Execution state passed through the LangGraph conversational nodes."""

    # Input message history and user query
    messages: List[Dict[str, str]]
    raw_query: str

    # Rewritten query resolving pronouns and context
    standalone_query: str

    # Classification & decomposition
    intent: str  # "FACT" | "DISCOVERY" | "COMPARISON" | "OUT_OF_SCOPE"
    target_category: Optional[str]  # e.g. "Credit Cards", "Debit Cards", "Current Accounts"
    sub_queries: List[str]

    # Context retrieval & evaluation
    retrieved_chunks: List[Dict[str, Any]]
    relevance_score: float
    is_relevant: bool
    needs_live_search: Optional[bool]
    live_searched_urls: Optional[List[str]]

    # Generation & output
    answer: str
    used_chunk_ids: List[str]
    citations: List[Dict[str, Any]]
    answerable: bool
    guardrail_passed: bool
    fallback_reason: Optional[str]
    products_in_context: List[str]

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
    sub_queries: List[str]

    # Context retrieval & evaluation
    retrieved_chunks: List[Dict[str, Any]]
    relevance_score: float
    is_relevant: bool

    # Generation & output
    answer: str
    used_chunk_ids: List[str]
    citations: List[Dict[str, Any]]
    answerable: bool
    guardrail_passed: bool
    fallback_reason: Optional[str]
    products_in_context: List[str]

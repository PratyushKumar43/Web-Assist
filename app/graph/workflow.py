"""LangGraph StateGraph workflow assembly and invocation engine."""

import logging
from typing import Any, Dict, List, Optional

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    citation_builder_node,
    fallback_node,
    generate_answer_node,
    grade_relevance_node,
    live_search_node,
    retrieve_context_node,
    rewrite_query_node,
    router_node,
)
from app.graph.state import ChatState
from app.models import ChatResponse, SourceItem

logger = logging.getLogger(__name__)


def route_after_router(state: ChatState) -> str:
    """Conditional edge: Route to fallback if out-of-scope; otherwise retrieve."""
    intent = state.get("intent", "FACT")
    if intent == "OUT_OF_SCOPE":
        return "fallback"
    return "retrieve"


def route_after_grade(state: ChatState) -> str:
    """Conditional edge: Route to generator if relevant, to live_search if needed, else fallback."""
    if state.get("needs_live_search", False):
        return "live_search"
    if state.get("is_relevant", False):
        return "generate"
    return "fallback"


def route_after_live_search(state: ChatState) -> str:
    """Conditional edge after agentic live search tool execution."""
    if state.get("is_relevant", False):
        return "generate"
    return "fallback"


def build_chat_graph():
    """Assemble and compile the LangGraph conversational StateGraph."""
    builder = StateGraph(ChatState)

    # 1. Register workflow nodes
    builder.add_node("rewrite", rewrite_query_node)
    builder.add_node("router", router_node)
    builder.add_node("retrieve", retrieve_context_node)
    builder.add_node("grade", grade_relevance_node)
    builder.add_node("live_search", live_search_node)
    builder.add_node("generate", generate_answer_node)
    builder.add_node("cite", citation_builder_node)
    builder.add_node("fallback", fallback_node)

    # 2. Add edges and conditional control flow
    builder.add_edge(START, "rewrite")
    builder.add_edge("rewrite", "router")

    builder.add_conditional_edges(
        "router",
        route_after_router,
        {
            "retrieve": "retrieve",
            "fallback": "fallback",
        },
    )

    builder.add_edge("retrieve", "grade")

    builder.add_conditional_edges(
        "grade",
        route_after_grade,
        {
            "generate": "generate",
            "live_search": "live_search",
            "fallback": "fallback",
        },
    )

    builder.add_conditional_edges(
        "live_search",
        route_after_live_search,
        {
            "generate": "generate",
            "fallback": "fallback",
        },
    )

    builder.add_edge("generate", "cite")
    builder.add_edge("cite", END)
    builder.add_edge("fallback", END)

    return builder.compile()


# Singleton compiled graph
_compiled_graph = None


def get_chat_graph():
    """Return singleton instance of the compiled LangGraph workflow."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_chat_graph()
    return _compiled_graph


async def run_chat_turn(
    query: str,
    messages: Optional[List[Dict[str, str]]] = None,
) -> ChatResponse:
    """Execute a single conversational turn through the compiled LangGraph."""
    graph = get_chat_graph()
    initial_state: ChatState = {
        "raw_query": query,
        "messages": messages or [],
    }

    result = await graph.ainvoke(initial_state)

    sources = [
        SourceItem(
            title=c["title"],
            url=c["url"],
            last_crawled=c.get("last_crawled", "2026-11-18"),
        )
        for c in result.get("citations", [])
    ]

    return ChatResponse(
        answer=result.get("answer", "No response generated."),
        sources=sources,
        answerable=result.get("answerable", True),
        intent=result.get("intent", "FACT"),
        products_in_context=result.get("products_in_context", []),
    )

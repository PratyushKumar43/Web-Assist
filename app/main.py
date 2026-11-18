"""FastAPI application entrypoint for Website RAG Chatbot."""

import logging
import os
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.graph.nodes import load_catalog_data
from app.graph.workflow import run_chat_turn
from app.models import ChatRequest, ChatResponse, HealthResponse, ProductItem

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Website RAG Chatbot API",
    description="Production-grade, highly defensible RAG Chatbot backend.",
    version="0.1.0",
)

# Enable CORS for local dev and preview deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session conversational histories
_sessions: Dict[str, List[Dict[str, str]]] = {}


@app.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Verify backend health and operational environment."""
    catalog = load_catalog_data()
    kb_ready = len(catalog) > 0 or bool(settings.QDRANT_URL)
    return HealthResponse(
        status="ok",
        environment="vercel" if settings.is_cloud else "local",
        kb_status="ready" if kb_ready else "unbuilt",
    )


@app.get("/api/products", response_model=List[ProductItem])
async def get_products() -> List[ProductItem]:
    """Retrieve full catalog of covered products and services."""
    catalog = load_catalog_data()
    return [
        ProductItem(
            name=p["name"],
            category=p["category"],
            url=p["url"],
            page_id=p.get("product_id"),
        )
        for p in catalog
    ]


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """Chat endpoint to process user queries through LangGraph state machine."""
    session_id = request.session_id or "default-session"
    history = _sessions.setdefault(session_id, [])

    # Execute LangGraph workflow
    response = await run_chat_turn(request.message, messages=history)

    # Append turns to session history (capped at last 10 messages)
    history.append({"role": "user", "content": request.message})
    history.append({"role": "assistant", "content": response.answer})
    if len(history) > 10:
        _sessions[session_id] = history[-10:]

    return response


# Mount static directory for browser UI
static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

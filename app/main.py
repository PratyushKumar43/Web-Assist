"""FastAPI application entrypoint for Website RAG Chatbot."""

import os
import tempfile

# Force all caches to writable /tmp for serverless/Lambda environments
_tmp = tempfile.gettempdir()
os.environ.setdefault("HF_HOME", os.path.join(_tmp, "hf_home"))
os.environ.setdefault("FASTEMBED_CACHE_PATH", os.path.join(_tmp, "fastembed"))
os.environ.setdefault("XDG_CACHE_HOME", os.path.join(_tmp, "cache"))
os.environ.setdefault("TRANSFORMERS_CACHE", os.path.join(_tmp, "transformers"))

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.diagnostics import diagnostics_router
from app.graph.nodes import load_catalog_data
from app.graph.workflow import run_chat_turn
from app.models import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    ProductItem,
    UIChatResponse,
)
from app.ui_view import build_ui_payload

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

# Mount developer diagnostic & testing endpoints for Swagger UI
app.include_router(diagnostics_router)

# In-memory session conversational histories
_sessions: Dict[str, List[Dict[str, str]]] = {}

# Answer ratings are appended here for offline review (data/ is git-ignored).
FEEDBACK_LOG = Path(__file__).resolve().parent.parent / "data" / "feedback.jsonl"


async def _run_turn(request: ChatRequest) -> ChatResponse:
    """Execute one conversational turn and persist it to the session history."""
    session_id = request.session_id or "default-session"
    history = _sessions.setdefault(session_id, [])

    response = await run_chat_turn(request.message, messages=history)

    # Append turns to session history (capped at last 10 messages)
    history.append({"role": "user", "content": request.message})
    history.append({"role": "assistant", "content": response.answer})
    if len(history) > 10:
        _sessions[session_id] = history[-10:]

    return response


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
    """Canonical chat contract: grounded answer, citations, and routed intent."""
    return await _run_turn(request)


@app.post("/api/chat/ui", response_model=UIChatResponse)
async def chat_ui_endpoint(request: ChatRequest) -> UIChatResponse:
    """Same turn, projected onto the render-ready view model the browser draws."""
    return build_ui_payload(await _run_turn(request))


@app.post("/api/feedback", response_model=FeedbackResponse)
async def feedback_endpoint(request: FeedbackRequest) -> FeedbackResponse:
    """Record an answer rating for offline review of groundedness."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "interaction_id": request.interaction_id,
        "rating": request.rating,
    }
    try:
        FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with FEEDBACK_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError as exc:
        logger.warning("Could not persist feedback to %s: %s", FEEDBACK_LOG, exc)

    return FeedbackResponse(status="recorded", interaction_id=request.interaction_id)


# Mount static directory for browser UI
static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

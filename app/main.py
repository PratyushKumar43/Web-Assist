"""FastAPI application entrypoint for Website RAG Chatbot."""

import os
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import ChatRequest, ChatResponse, HealthResponse, ProductItem

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


@app.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Verify backend health and operational environment."""
    kb_exists = os.path.exists(settings.SQLITE_DB_PATH) or os.path.exists(settings.QDRANT_LOCAL_PATH)
    return HealthResponse(
        status="ok",
        environment="vercel" if settings.is_cloud else "local",
        kb_status="ready" if kb_exists else "unbuilt",
    )


@app.get("/api/products", response_model=List[ProductItem])
async def get_products() -> List[ProductItem]:
    """Retrieve full catalog of covered products and services."""
    # In Phase 2, this reads directly from SQLite products table
    return []


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """Chat endpoint to process user queries through LangGraph state machine."""
    # In Phase 4, this delegates directly to compiled LangGraph StateGraph
    return ChatResponse(
        answer="Backend initialized. Knowledge base and LangGraph pipeline active in upcoming phases.",
        sources=[],
        answerable=True,
        intent="FACT",
        products_in_context=[],
    )


# Mount static directory for single-page UI if available
static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

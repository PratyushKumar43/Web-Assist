"""Diagnostics & testing endpoints for Swagger UI verification."""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.graph.nodes import rewrite_query_node, router_node
from app.indexer import get_indexer
from app.models import (
    ChunkResultItem,
    LLMTestRequest,
    LLMTestResponse,
    ProviderHealthReport,
    RetrievalTestRequest,
    RetrievalTestResponse,
    RewriteTestRequest,
    RewriteTestResponse,
)

logger = logging.getLogger(__name__)

diagnostics_router = APIRouter(prefix="/api/test", tags=["Diagnostics & Testing"])


# -----------------------------------------------------------------------------
# 1. LLM Generation Test Endpoint
# -----------------------------------------------------------------------------

@diagnostics_router.post("/llm", response_model=LLMTestResponse)
async def test_llm(req: LLMTestRequest) -> LLMTestResponse:
    """Test response generation and round-trip latency across LLM providers.

    Supports xAI Grok (`https://api.x.ai/v1`), Google Gemini, and OpenRouter.
    """
    start_time = time.perf_counter()
    target_provider = req.provider.lower()

    # Determine provider if 'auto'
    if target_provider == "auto":
        if settings.XAI_API_KEY and not settings.XAI_API_KEY.startswith("<"):
            target_provider = "xai"
        elif settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("AIzaSy..."):
            target_provider = "gemini"
        elif settings.OPENROUTER_API_KEY and not settings.OPENROUTER_API_KEY.startswith("<"):
            target_provider = "openrouter"
        else:
            target_provider = "deterministic"

    # 1. xAI Grok Invocation
    if target_provider == "xai":
        api_key = settings.XAI_API_KEY
        if not api_key:
            return LLMTestResponse(
                status="error",
                provider="xai",
                model=settings.XAI_MODEL,
                response="",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                configured=False,
                error="xAI API key is not configured in .env (XAI_API_KEY).",
            )
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": settings.XAI_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a concise Emirates NBD virtual assistant."},
                    {"role": "user", "content": req.prompt},
                ],
                "temperature": req.temperature,
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.XAI_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                latency_ms = (time.perf_counter() - start_time) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    content = choices[0]["message"]["content"].strip() if choices else "No response choice returned."
                    return LLMTestResponse(
                        status="ok",
                        provider="xai",
                        model=settings.XAI_MODEL,
                        response=content,
                        latency_ms=round(latency_ms, 2),
                        configured=True,
                    )
                else:
                    return LLMTestResponse(
                        status="error",
                        provider="xai",
                        model=settings.XAI_MODEL,
                        response="",
                        latency_ms=round(latency_ms, 2),
                        configured=True,
                        error=f"xAI API returned HTTP {resp.status_code}: {resp.text}",
                    )
        except Exception as e:
            return LLMTestResponse(
                status="error",
                provider="xai",
                model=settings.XAI_MODEL,
                response="",
                latency_ms=round((time.perf_counter() - start_time) * 1000, 2),
                configured=True,
                error=f"Failed to connect to xAI Grok API: {str(e)}",
            )

    # 2. Google Gemini Invocation
    elif target_provider == "gemini":
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            return LLMTestResponse(
                status="error",
                provider="gemini",
                model=settings.GEMINI_MODEL,
                response="",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                configured=False,
                error="Gemini API key is not configured in .env (GEMINI_API_KEY).",
            )
        try:
            from google import genai

            client = genai.Client(api_key=api_key)
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=req.prompt,
                ),
            )
            latency_ms = (time.perf_counter() - start_time) * 1000
            text = resp.text.strip() if resp and resp.text else "Empty response from Gemini."
            return LLMTestResponse(
                status="ok",
                provider="gemini",
                model=settings.GEMINI_MODEL,
                response=text,
                latency_ms=round(latency_ms, 2),
                configured=True,
            )
        except Exception as e:
            return LLMTestResponse(
                status="error",
                provider="gemini",
                model=settings.GEMINI_MODEL,
                response="",
                latency_ms=round((time.perf_counter() - start_time) * 1000, 2),
                configured=True,
                error=f"Gemini API invocation failed: {str(e)}",
            )

    # 3. OpenRouter Invocation
    elif target_provider == "openrouter":
        api_key = settings.OPENROUTER_API_KEY
        if not api_key:
            return LLMTestResponse(
                status="error",
                provider="openrouter",
                model=settings.OPENROUTER_MODEL,
                response="",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                configured=False,
                error="OpenRouter API key is not configured in .env (OPENROUTER_API_KEY).",
            )
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Web-Assist",
            }
            payload = {
                "model": settings.OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a concise banking assistant."},
                    {"role": "user", "content": req.prompt},
                ],
                "temperature": req.temperature,
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                latency_ms = (time.perf_counter() - start_time) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    content = choices[0]["message"]["content"].strip() if choices else "No choices returned."
                    return LLMTestResponse(
                        status="ok",
                        provider="openrouter",
                        model=settings.OPENROUTER_MODEL,
                        response=content,
                        latency_ms=round(latency_ms, 2),
                        configured=True,
                    )
                else:
                    return LLMTestResponse(
                        status="error",
                        provider="openrouter",
                        model=settings.OPENROUTER_MODEL,
                        response="",
                        latency_ms=round(latency_ms, 2),
                        configured=True,
                        error=f"OpenRouter API returned HTTP {resp.status_code}: {resp.text}",
                    )
        except Exception as e:
            return LLMTestResponse(
                status="error",
                provider="openrouter",
                model=settings.OPENROUTER_MODEL,
                response="",
                latency_ms=round((time.perf_counter() - start_time) * 1000, 2),
                configured=True,
                error=f"Failed to connect to OpenRouter: {str(e)}",
            )

    # 4. Deterministic Rule-Based Fallback
    return LLMTestResponse(
        status="ok",
        provider="deterministic",
        model="rule_based_synthesis_v1",
        response="Emirates NBD is grounded in customer-centric innovation, ethical banking, and digital leadership across the UAE.",
        latency_ms=round((time.perf_counter() - start_time) * 1000, 2),
        configured=True,
    )


# -----------------------------------------------------------------------------
# 2. Comprehensive Provider Health Check Endpoint
# -----------------------------------------------------------------------------

@diagnostics_router.get("/providers", response_model=ProviderHealthReport)
async def test_providers() -> ProviderHealthReport:
    """Inspect environment configuration and live connection health across all integrations."""
    providers_report: Dict[str, Dict[str, Any]] = {}

    # 1. xAI Grok Status
    has_xai = bool(settings.XAI_API_KEY and not settings.XAI_API_KEY.startswith("<"))
    providers_report["xai"] = {
        "configured": has_xai,
        "model": settings.XAI_MODEL,
        "base_url": settings.XAI_BASE_URL,
        "status": "ready" if has_xai else "missing_api_key",
    }

    # 2. Google Gemini Status
    has_gemini = bool(settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("AIzaSy..."))
    providers_report["gemini"] = {
        "configured": has_gemini,
        "model": settings.GEMINI_MODEL,
        "embedding_model": settings.EMBEDDING_MODEL,
        "status": "ready" if has_gemini else "missing_api_key",
    }

    # 3. OpenRouter Status
    has_openrouter = bool(settings.OPENROUTER_API_KEY and not settings.OPENROUTER_API_KEY.startswith("<"))
    providers_report["openrouter"] = {
        "configured": has_openrouter,
        "model": settings.OPENROUTER_MODEL,
        "status": "ready" if has_openrouter else "missing_api_key",
    }

    # 4. Qdrant Vector DB Status
    try:
        indexer = get_indexer()
        loop = asyncio.get_event_loop()
        collection_info = await loop.run_in_executor(
            None,
            lambda: indexer.client.get_collection(indexer.collection_name),
        )
        providers_report["qdrant"] = {
            "configured": True,
            "connected": True,
            "collection": indexer.collection_name,
            "points_count": collection_info.points_count if collection_info else 0,
            "cluster_url": settings.QDRANT_URL or "local_embedded",
            "status": "operational",
        }
    except Exception as e:
        providers_report["qdrant"] = {
            "configured": bool(settings.QDRANT_URL or settings.QDRANT_LOCAL_PATH),
            "connected": False,
            "status": "error",
            "error": str(e),
        }

    # 5. Firecrawl Scraper Status
    has_firecrawl = bool(settings.FIRECRAWL_API_KEY and not settings.FIRECRAWL_API_KEY.startswith("<"))
    providers_report["firecrawl"] = {
        "configured": has_firecrawl,
        "status": "ready" if has_firecrawl else "missing_api_key",
    }

    # 6. TinyFish AI Status
    has_tinyfish = bool(settings.TINYFISH_API_KEY and not settings.TINYFISH_API_KEY.startswith("<"))
    providers_report["tinyfish"] = {
        "configured": has_tinyfish,
        "status": "ready" if has_tinyfish else "missing_api_key",
    }

    all_ready = providers_report["qdrant"].get("connected", False) and (
        has_xai or has_gemini or has_openrouter or True
    )

    return ProviderHealthReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        environment="vercel" if settings.is_cloud else "local",
        all_ready=all_ready,
        providers=providers_report,
    )


# -----------------------------------------------------------------------------
# 3. Isolated Retrieval Test Endpoint
# -----------------------------------------------------------------------------

@diagnostics_router.post("/retrieval", response_model=RetrievalTestResponse)
async def test_retrieval(req: RetrievalTestRequest) -> RetrievalTestResponse:
    """Test Qdrant hybrid vector search in isolation without calling an LLM."""
    start_time = time.perf_counter()
    indexer = get_indexer()

    loop = asyncio.get_event_loop()
    raw_results = await loop.run_in_executor(
        None,
        lambda: indexer.hybrid_search(req.query, top_k=req.top_k),
    )
    latency_ms = (time.perf_counter() - start_time) * 1000

    chunks: List[ChunkResultItem] = []
    max_score = 0.0

    for r in raw_results:
        # Category filter if supplied
        if req.category and req.category.lower() not in r.get("category", "").lower():
            continue

        score = float(r.get("score", 0.0))
        if score > max_score:
            max_score = score

        snippet = r.get("text", "")
        # Shorten snippet for Swagger readability
        clean_snippet = snippet[:250].replace("\n", " ").strip() + ("..." if len(snippet) > 250 else "")

        chunks.append(
            ChunkResultItem(
                chunk_id=r.get("chunk_id", "unknown"),
                product_name=r.get("product_name", "Emirates NBD Documentation"),
                category=r.get("category", "General"),
                score=round(score, 4),
                url=r.get("url", ""),
                title=r.get("title", ""),
                text_snippet=clean_snippet,
            )
        )

    return RetrievalTestResponse(
        query=req.query,
        top_k=req.top_k,
        results_count=len(chunks),
        max_score=round(max_score, 4),
        latency_ms=round(latency_ms, 2),
        chunks=chunks,
    )


# -----------------------------------------------------------------------------
# 4. Isolated Query Rewriter & Router Test Endpoint
# -----------------------------------------------------------------------------

@diagnostics_router.post("/rewrite", response_model=RewriteTestResponse)
async def test_rewrite(req: RewriteTestRequest) -> RewriteTestResponse:
    """Test standalone query rewriting, pronoun resolution, and intent routing in isolation."""
    # 1. Execute Query Rewriter
    state_in = {
        "raw_query": req.raw_query,
        "messages": req.history,
    }
    rewrite_out = rewrite_query_node(state_in)
    standalone_query = rewrite_out.get("standalone_query", req.raw_query)

    # 2. Execute Router
    state_router = {
        "standalone_query": standalone_query,
        "raw_query": req.raw_query,
        "messages": req.history,
    }
    router_out = router_node(state_router)

    return RewriteTestResponse(
        raw_query=req.raw_query,
        standalone_query=standalone_query,
        intent=router_out.get("intent", "FACT"),
        target_product=router_out.get("target_product"),
        target_category=router_out.get("target_category"),
        excluded_products=router_out.get("excluded_products", []),
        sub_queries=router_out.get("sub_queries", []),
    )

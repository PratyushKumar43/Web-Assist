"""Tests for Developer Diagnostic & Testing Endpoints on Swagger."""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_diagnostics_providers_health():
    """Verify GET /api/test/providers returns comprehensive readiness report."""
    response = client.get("/api/test/providers")
    assert response.status_code == 200
    data = response.json()
    assert "timestamp" in data
    assert "environment" in data
    assert "providers" in data
    assert "all_ready" in data

    providers = data["providers"]
    assert "xai" in providers
    assert "gemini" in providers
    assert "openrouter" in providers
    assert "qdrant" in providers
    assert "firecrawl" in providers
    assert "tinyfish" in providers
    assert providers["qdrant"]["status"] in ["operational", "ready", "connected", "error"]


def test_diagnostics_isolated_retrieval():
    """Verify POST /api/test/retrieval performs isolated Qdrant hybrid search."""
    payload = {
        "query": "U By Emaar Signature Credit Card annual fee",
        "top_k": 3,
    }
    response = client.post("/api/test/retrieval", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == payload["query"]
    assert data["top_k"] == 3
    assert data["results_count"] >= 0
    assert "latency_ms" in data
    assert isinstance(data["chunks"], list)
    if data["chunks"]:
        first = data["chunks"][0]
        assert "chunk_id" in first
        assert "product_name" in first
        assert "score" in first
        assert "text_snippet" in first


def test_diagnostics_isolated_rewrite():
    """Verify POST /api/test/rewrite resolves pronouns and extracts intent."""
    payload = {
        "raw_query": "what is its annual fee?",
        "history": [
            {"role": "user", "content": "Tell me about U By Emaar Signature Credit Card"},
            {"role": "assistant", "content": "The U By Emaar Signature Credit Card is a premier lifestyle card."},
        ],
    }
    response = client.post("/api/test/rewrite", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "u by emaar" in data["standalone_query"].lower()
    assert data["intent"] in ["FACT", "DISCOVERY", "COMPARISON"]


def test_diagnostics_llm_auto_invocation():
    """Verify POST /api/test/llm executes test prompt and returns latency and model output."""
    payload = {
        "provider": "auto",
        "prompt": "What are Emirates NBD's core banking values? Answer in 1 short sentence.",
        "temperature": 0.2,
    }
    response = client.post("/api/test/llm", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["ok", "error"]
    assert "provider" in data
    assert "model" in data
    assert "latency_ms" in data
    assert data["latency_ms"] >= 0

"""Integration tests for FastAPI endpoints: /api/health, /api/products, /api/chat, and UI."""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_api_health_endpoint():
    """Verify /api/health reports operational status and kb readiness."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["kb_status"] in ["ready", "unbuilt"]
    assert "environment" in data


def test_api_products_endpoint():
    """Verify /api/products returns catalog list with valid schemas."""
    res = client.get("/api/products")
    assert res.status_code == 200
    products = res.json()
    assert isinstance(products, list)
    if products:
        p = products[0]
        assert "name" in p
        assert "category" in p
        assert "url" in p


def test_api_chat_endpoint_fact():
    """Verify POST /api/chat handles single product fact query."""
    payload = {
        "session_id": "test-session-api",
        "message": "What is the annual fee of U By Emaar Signature Credit Card?",
    }
    res = client.post("/api/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["answerable"] is True
    assert "answer" in data
    assert len(data["sources"]) > 0


def test_api_chat_endpoint_fallback():
    """Verify POST /api/chat falls back on out-of-scope query."""
    payload = {
        "session_id": "test-session-api",
        "message": "How do I make chocolate cake?",
    }
    res = client.post("/api/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["answerable"] is False
    assert data["intent"] == "OUT_OF_SCOPE"
    assert len(data["sources"]) == 0


def test_static_index_html():
    """Verify root / serves the HTML browser chat interface."""
    res = client.get("/")
    assert res.status_code == 200
    assert "Emirates NBD Assistant" in res.text
    assert "Qdrant Hybrid RAG" in res.text

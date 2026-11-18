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
    """Verify root / serves the WhatsApp-style HTML chat interface."""
    res = client.get("/")
    assert res.status_code == 200
    assert "Lexi" in res.text
    assert "Qdrant Hybrid RAG" in res.text
    assert "/api/chat/ui" in res.text


def test_api_chat_ui_endpoint_returns_view_model():
    """Verify POST /api/chat/ui returns the render-ready payload the browser draws."""
    payload = {
        "session_id": "test-session-ui",
        "message": "What savings and account options can I open?",
    }
    res = client.post("/api/chat/ui", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["intent"] == "DISCOVERY"
    assert data["cache_hit"] is False
    assert data["answerable"] is True
    assert data["interaction_id"]
    assert data["intro"]
    assert len(data["cards"]) > 0
    card = data["cards"][0]
    for key in ("name", "category", "fee", "requirement", "highlight", "url"):
        assert key in card
    assert len(data["sources"]) > 0
    assert data["next_chips"]


def test_api_feedback_endpoint_records_rating():
    """Verify POST /api/feedback acknowledges an answer rating."""
    res = client.post(
        "/api/feedback",
        json={"interaction_id": "abc123", "rating": "up"},
    )
    assert res.status_code == 200
    assert res.json() == {"status": "recorded", "interaction_id": "abc123"}


def test_api_feedback_rejects_unknown_rating():
    """Verify the rating field is validated."""
    res = client.post("/api/feedback", json={"interaction_id": "abc123", "rating": "sideways"})
    assert res.status_code == 422


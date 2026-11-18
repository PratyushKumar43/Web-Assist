import pytest
import asyncio
from app.graph.state import ChatState
from app.graph.nodes import (
    rewrite_query_node,
    router_node,
    retrieve_context_node,
    deterministic_grounded_synthesis,
    citation_builder_node,
)


def test_turn1_credit_cards_discovery():
    state: ChatState = {
        "raw_query": "Which credit cards do you offer?",
        "messages": [],
    }
    # 1. Rewriter
    rw_res = rewrite_query_node(state)
    assert "Which credit cards do you offer?" in rw_res["standalone_query"]
    state["standalone_query"] = rw_res["standalone_query"]

    # 2. Router
    r_res = router_node(state)
    assert r_res["intent"] == "DISCOVERY"
    assert r_res["target_category"] == "Credit Cards"


def test_turn2_rejection_and_pivot_to_original_topic():
    # User previously asked for credit cards, bot replied erroneously about current accounts
    messages = [
        {"role": "user", "content": "Which credit cards do you offer?"},
        {
            "role": "assistant",
            "content": "According to official Emirates NBD documentation for Standard Current Account: Plus Maximizer - Current account: AED 5,000 to AED 14,999",
        },
    ]
    state: ChatState = {
        "raw_query": "but i didnt ask for Standard Current Account,show me all types",
        "messages": messages,
    }
    rw_res = rewrite_query_node(state)
    rewritten = rw_res["standalone_query"]
    # Must recover "credit cards" and drop "Standard Current Account"
    assert "credit cards" in rewritten.lower()
    assert "current account" not in rewritten.lower()

    state["standalone_query"] = rewritten
    r_res = router_node(state)
    assert r_res["intent"] == "DISCOVERY"
    assert r_res["target_category"] == "Credit Cards"


def test_turn3_broad_catalog_discovery():
    state: ChatState = {
        "raw_query": "what products you offers?",
        "messages": [],
    }
    rw_res = rewrite_query_node(state)
    assert "what products do you offer" in rw_res["standalone_query"]

    state["standalone_query"] = rw_res["standalone_query"]
    r_res = router_node(state)
    assert r_res["intent"] == "DISCOVERY"
    assert r_res.get("target_category") is None


def test_turn4_debit_cards_typo_and_discovery():
    state: ChatState = {
        "raw_query": "how me all debit cards options",
        "messages": [],
    }
    # Typo correction: "how me" -> "show me"
    rw_res = rewrite_query_node(state)
    assert rw_res["standalone_query"].startswith("show me all debit cards")

    state["standalone_query"] = rw_res["standalone_query"]
    r_res = router_node(state)
    assert r_res["intent"] == "DISCOVERY"
    assert r_res["target_category"] == "Debit Cards"


def test_turn5_elliptical_followup():
    # After debit cards discussion, user says "any other"
    messages = [
        {"role": "user", "content": "how me all debit cards options"},
        {
            "role": "assistant",
            "content": "Here are the verified Debit Cards: Visa Classic Debit Card, Visa Signature Debit Card, Visa Infinite Debit Card.",
        },
    ]
    state: ChatState = {
        "raw_query": "any other",
        "messages": messages,
    }
    rw_res = rewrite_query_node(state)
    assert "debit cards" in rw_res["standalone_query"].lower()

    state["standalone_query"] = rw_res["standalone_query"]
    r_res = router_node(state)
    assert r_res["intent"] == "DISCOVERY"
    assert r_res["target_category"] == "Debit Cards"


@pytest.mark.asyncio
async def test_strict_category_isolation_retrieval():
    # Test Credit Cards retrieval
    state_cc: ChatState = {
        "standalone_query": "Which credit cards do you offer?",
        "raw_query": "Which credit cards do you offer?",
        "intent": "DISCOVERY",
        "target_category": "Credit Cards",
        "sub_queries": ["Which credit cards do you offer?"],
    }
    res_cc = await retrieve_context_node(state_cc)
    chunks_cc = res_cc["retrieved_chunks"]
    assert len(chunks_cc) > 0
    # Ensure NO Current Account or Savings Account chunk exists in Credit Cards context
    for c in chunks_cc:
        cat = c.get("category", "").lower()
        prod = c.get("product_name", "").lower()
        assert "current account" not in cat and "current account" not in prod
        assert "savings account" not in cat and "savings account" not in prod

    # Test Debit Cards retrieval
    state_dc: ChatState = {
        "standalone_query": "show me all debit cards options",
        "raw_query": "how me all debit cards options",
        "intent": "DISCOVERY",
        "target_category": "Debit Cards",
        "sub_queries": ["show me all debit cards options"],
    }
    res_dc = await retrieve_context_node(state_dc)
    chunks_dc = res_dc["retrieved_chunks"]
    assert len(chunks_dc) > 0
    for c in chunks_dc:
        cat = c.get("category", "").lower()
        prod = c.get("product_name", "").lower()
        assert "credit card" not in cat and "credit card" not in prod
        assert "current account" not in cat and "current account" not in prod


def test_deterministic_synthesis_category_filtering():
    # DISCOVERY with target_category = "Debit Cards"
    ans, used_ids = deterministic_grounded_synthesis(
        "show me all debit cards options",
        "DISCOVERY",
        [{"chunk_id": "c1", "text": "Visa Classic Debit Card"}],
        target_category="Debit Cards",
    )
    assert "Hi! I'm Lexi" not in ans
    assert "| Product Name | Category |" in ans
    assert "Debit Cards" in ans
    assert "Visa Classic Debit Card" in ans
    assert "U By Emaar Signature Credit Card" not in ans
    assert "Standard Current Account" not in ans

    # DISCOVERY with target_category = "Credit Cards"
    ans_cc, used_ids_cc = deterministic_grounded_synthesis(
        "which credit cards do you offer",
        "DISCOVERY",
        [{"chunk_id": "c2", "text": "Skywards Signature"}],
        target_category="Credit Cards",
    )
    assert "Hi! I'm Lexi" not in ans_cc
    assert "| Product Name | Category |" in ans_cc
    assert "Credit Cards" in ans_cc
    assert "Skywards Signature Credit Card" in ans_cc or "Emirates NBD Skywards" in ans_cc or "U By Emaar" in ans_cc
    assert "Standard Current Account" not in ans_cc


@pytest.mark.asyncio
async def test_gold_savings_certificate_rich_synthesis():
    """Verify Gold Savings Certificate provides full terms (100g, 999.9 fineness, branch redemption) without breadcrumb dumps."""
    from app.graph.workflow import run_chat_turn

    resp = await run_chat_turn("i want to know Gold Savings Certificate")
    assert resp.answerable is True
    assert resp.intent == "FACT"
    # Must NOT have raw breadcrumb line
    assert "Product: Gold Saving Certificates > Overview" not in resp.answer
    # Must NOT repeat "Hi! I'm Lexi" in body
    assert "Hi! I'm Lexi" not in resp.answer
    # Must contain rich verified terms
    ans_lower = resp.answer.lower()
    assert "100" in ans_lower or "grams" in ans_lower
    assert "999.9" in ans_lower or "fineness" in ans_lower or "gold" in ans_lower
    assert "redemption" in ans_lower or "branch" in ans_lower or "cash" in ans_lower


def test_citation_builder_category_filtering():
    state: ChatState = {
        "target_category": "Credit Cards",
        "used_chunk_ids": ["catalog_skywards"],
        "retrieved_chunks": [
            {
                "chunk_id": "catalog_skywards",
                "product_name": "Emirates NBD Skywards Signature Credit Card",
                "url": "https://www.emiratesnbd.com/en/cards/credit-cards/skywards-signature",
                "title": "Skywards Signature Credit Card | Emirates NBD",
            },
            {
                "chunk_id": "c_utility",
                "product_name": "Contact Emirates NBD",
                "url": "https://www.emiratesnbd.com/en/help-and-support/contact-us",
                "title": "Contact Us",
            },
            {
                "chunk_id": "c_wrong_cat",
                "product_name": "Standard Current Account",
                "url": "https://www.emiratesnbd.com/en/accounts/current-accounts/standard-current-account",
                "title": "Current Account",
            },
        ],
    }
    citations = citation_builder_node(state)["citations"]
    assert len(citations) >= 1
    urls = [c["url"] for c in citations]
    assert "https://www.emiratesnbd.com/en/cards/credit-cards/skywards-signature" in urls
    assert "https://www.emiratesnbd.com/en/help-and-support/contact-us" not in urls
    assert "https://www.emiratesnbd.com/en/accounts/current-accounts/standard-current-account" not in urls

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


def test_comparison_intent_difference_in_phrasing():
    """'difference in X and Y' must route to COMPARISON intent."""
    state: ChatState = {
        "standalone_query": "difference in U By Emaar Signature Credit Card and Visa Flexi Credit Card",
    }
    result = router_node(state)
    assert result["intent"] == "COMPARISON"
    assert len(result.get("sub_queries", [])) >= 2
    assert "U By Emaar Signature Credit Card" in result.get("products_in_context", [])
    assert "Visa Flexi Credit Card" in result.get("products_in_context", [])


def test_followup_both_comparison_resolution():
    """'i want both difference' with two products in history must rewrite to explicit comparison."""
    state: ChatState = {
        "raw_query": "i want both difference",
        "messages": [
            {"role": "user", "content": "tell me about U By Emaar Signature Credit Card"},
            {"role": "assistant", "content": "Here is what you need to know about U By Emaar Signature Credit Card..."},
            {"role": "user", "content": "what about Visa Flexi Credit Card"},
            {"role": "assistant", "content": "Here is what you need to know about Visa Flexi Credit Card..."},
        ],
    }
    result = rewrite_query_node(state)
    resolved = result["standalone_query"].lower()
    assert "u by emaar" in resolved
    assert "visa flexi" in resolved
    assert "compare" in resolved


def test_about_emiratesnbd_routes_to_about():
    """'about emiratesnbd' must route to ABOUT intent, not FACT."""
    for q in ["about emiratesnbd", "about emirates nbd", "tell me about emirates nbd", "what is emirates nbd"]:
        state: ChatState = {"standalone_query": q}
        result = router_node(state)
        assert result["intent"] == "ABOUT"


@pytest.mark.asyncio
async def test_end_to_end_user_reported_flow():
    """Verify end-to-end user reported flow: about bank -> difference in cards -> both follow-up."""
    from app.graph.workflow import run_chat_turn

    # 1. Bank overview query
    resp1 = await run_chat_turn("about emiratesnbd")
    assert resp1.answerable is True
    assert resp1.intent == "ABOUT"
    assert "Emirates NBD" in resp1.answer
    assert "Product Categories" in resp1.answer
    assert "Credit Cards" in resp1.answer

    # 2. Comparison using 'difference in'
    resp2 = await run_chat_turn("difference in U By Emaar Signature Credit Card and Visa Flexi Credit Card")
    assert resp2.answerable is True
    assert resp2.intent == "COMPARISON"
    assert "| Feature / Detail |" in resp2.answer
    assert "U By Emaar Signature Credit Card" in resp2.answer
    assert "Visa Flexi Credit Card" in resp2.answer

    # 3. Follow-up: 'i want both difference'
    history = [
        {"role": "user", "content": "difference in U By Emaar Signature Credit Card and Visa Flexi Credit Card"},
        {"role": "assistant", "content": resp2.answer},
    ]
    resp3 = await run_chat_turn("i want both difference", messages=history)
    assert resp3.answerable is True
    assert resp3.intent == "COMPARISON"
    assert "| Feature / Detail |" in resp3.answer
    assert "U By Emaar Signature Credit Card" in resp3.answer
    assert "Visa Flexi Credit Card" in resp3.answer
    assert "AED 262.50" in resp3.answer or "Free for Life" in resp3.answer

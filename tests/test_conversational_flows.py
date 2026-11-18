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


# -----------------------------------------------------------------------------
# Regression tests: retrieval, memory, scraping noise, and routing fixes
# -----------------------------------------------------------------------------

def test_bare_continuation_tell_me_all():
    """'tell me all' after 'types of credit card' rewrites to an explicit credit cards query."""
    messages = [
        {"role": "user", "content": "types of credit card?"},
        {"role": "assistant", "content": "Here are the credit cards..."},
    ]
    result = rewrite_query_node({"raw_query": "tell me all", "messages": messages})
    assert "credit card" in result["standalone_query"].lower()
    assert result["standalone_query"].lower().startswith("list all")


def test_bare_affirmation_yes_binds_to_prior_topic():
    """'yes please' after a debit cards turn resolves to debit cards, not an unrelated page."""
    messages = [
        {"role": "user", "content": "how me all debit cards options"},
        {"role": "assistant", "content": "Here are the verified Debit Cards..."},
    ]
    result = rewrite_query_node({"raw_query": "yes please", "messages": messages})
    assert "debit cards" in result["standalone_query"].lower()


def test_tell_me_all_without_history_requests_catalog():
    """A first-turn 'tell me all' becomes an explicit catalog overview request."""
    rw = rewrite_query_node({"raw_query": "tell me all", "messages": []})
    assert rw["standalone_query"] == "List all Emirates NBD banking products and services"
    route = router_node({"standalone_query": rw["standalone_query"]})
    assert route["intent"] == "DISCOVERY"
    assert route.get("target_category") is None


def test_bare_affirmation_without_topic_is_not_rewritten():
    """A bare 'yes' with no banking history must not become a catalog query."""
    result = rewrite_query_node({"raw_query": "yes", "messages": []})
    assert result["standalone_query"] == "yes"


def test_bare_affirmation_after_product_question_keeps_product_thread():
    """'yes' after a single-product turn stays on that product, never a catalog listing."""
    messages = [
        {"role": "user", "content": "tell me about U By Emaar Signature Credit Card"},
        {"role": "assistant", "content": "Here is what you need to know about **U By Emaar Signature Credit Card**."},
    ]
    result = rewrite_query_node({"raw_query": "yes", "messages": messages})
    assert result["standalone_query"] == "tell me about U By Emaar Signature Credit Card"
    assert "list all" not in result["standalone_query"].lower()


def test_about_your_products_is_discovery():
    """'about your products' routes to DISCOVERY, not ABOUT or FACT."""
    result = router_node({"standalone_query": "about your products?", "raw_query": "about your products?"})
    assert result["intent"] == "DISCOVERY"


def test_types_of_credit_card_is_discovery():
    """'types of credit card?' routes to DISCOVERY with the credit cards category."""
    result = router_node({"standalone_query": "types of credit card?", "raw_query": "types of credit card?"})
    assert result["intent"] == "DISCOVERY"
    assert result.get("target_category") == "Credit Cards"


def test_list_all_cards_with_fees_stays_discovery():
    """A rewritten 'list all ... with annual fees' query is still DISCOVERY, not FACT."""
    result = router_node(
        {
            "standalone_query": "List all Emirates NBD credit cards with annual fees, minimum salary requirements, and key benefits"
        }
    )
    assert result["intent"] == "DISCOVERY"
    assert result.get("target_category") == "Credit Cards"


def test_three_turn_discovery_sequence():
    """Turns 1-3 of the reported failure: overview, credit card types, then 'tell me all'."""
    # Turn 1: broad overview
    rw1 = rewrite_query_node({"raw_query": "about your products?", "messages": []})
    route1 = router_node({"standalone_query": rw1["standalone_query"]})
    assert route1["intent"] == "DISCOVERY"

    # Turn 2: types of credit card
    history = [
        {"role": "user", "content": "about your products?"},
        {"role": "assistant", "content": "Here is an overview of the banking products..."},
    ]
    rw2 = rewrite_query_node({"raw_query": "types of credit card?", "messages": history})
    route2 = router_node({"standalone_query": rw2["standalone_query"]})
    assert route2["intent"] == "DISCOVERY"
    assert route2.get("target_category") == "Credit Cards"

    # Turn 3: bare continuation must inherit the credit cards topic
    history += [
        {"role": "user", "content": "types of credit card?"},
        {"role": "assistant", "content": "| Product Name | Category |\n| Visa Flexi Credit Card | Credit Cards |"},
    ]
    rw3 = rewrite_query_node({"raw_query": "tell me all", "messages": history})
    assert "credit card" in rw3["standalone_query"].lower()
    route3 = router_node({"standalone_query": rw3["standalone_query"]})
    assert route3["intent"] == "DISCOVERY"
    assert route3.get("target_category") == "Credit Cards"


def test_dom_noise_stripped():
    """Feedback widgets, survey prompts, and yes/no buttons are stripped from cleaned markdown."""
    from app.clean import strip_boilerplate

    dirty = (
        "Great product!\n"
        "Would you like to talk to us?\n"
        "We'd like to hear from you\n"
        "Thank you for your feedback!\n"
        "Was this information helpful?\n"
        "Yes No\n"
        "Skip to main content\n"
        "Enable accessibility\n"
    )
    cleaned = strip_boilerplate(dirty)
    assert "Would you like to talk to us" not in cleaned
    assert "We'd like to hear from you" not in cleaned
    assert "Thank you for your feedback" not in cleaned
    assert "Was this information helpful" not in cleaned
    assert "Skip to main content" not in cleaned
    assert "Yes No" not in cleaned
    assert "Great product!" in cleaned


def test_product_name_ignores_heading_noise():
    """product_name falls back to a cleaned <title>, never raw navigation or heading noise."""
    from app.chunk import chunk_document, clean_title_product_name

    assert clean_title_product_name("Skip to main content Visa Flexi Credit Card | Emirates NBD") == "Visa Flexi Credit Card"
    assert clean_title_product_name("Visa Flexi Credit Card - Emirates NBD") == "Visa Flexi Credit Card"

    page = {
        "url": "https://www.emiratesnbd.com/en/cards/credit-cards/visa-flexi",
        "title": "Skip to main content Visa Flexi Credit Card | Emirates NBD",
        "markdown": "# Rewards\n\nEarn up to 5% cashback on everyday spends.",
        "crawled_at": "2026-11-18",
    }
    chunks = chunk_document(page)
    assert chunks
    assert chunks[0]["product_name"] == "Visa Flexi Credit Card"


@pytest.mark.asyncio
async def test_catalog_anchor_chunks_never_become_products(monkeypatch):
    """Synthetic catalog-directory chunks are context only, never comparison products."""
    class FakeIndexer:
        def hybrid_search(self, query, top_k=6, query_filter=None):
            if "U By Emaar" in query:
                return [{
                    "chunk_id": "u-0",
                    "product_name": "U By Emaar Signature Credit Card",
                    "category": "Credit Cards",
                    "url": "https://www.emiratesnbd.com/en/cards/credit-cards/u-by-emaar",
                    "text": "U By Emaar annual fee AED 262.50",
                    "score": 0.9,
                }]
            return [
                {
                    "chunk_id": "catalog-directory-credit-cards",
                    "product_name": "Emirates NBD Credit Cards Directory",
                    "category": "general_catalog",
                    "url": "https://www.emiratesnbd.com/en",
                    "text": "What credit cards does Emirates NBD offer?",
                    "score": 0.95,
                },
                {
                    "chunk_id": "v-0",
                    "product_name": "Visa Flexi Credit Card",
                    "category": "Credit Cards",
                    "url": "https://www.emiratesnbd.com/en/cards/credit-cards/visa-flexi",
                    "text": "Visa Flexi benefits",
                    "score": 0.9,
                },
            ]

    monkeypatch.setattr("app.graph.nodes.get_indexer", lambda: FakeIndexer())

    state: ChatState = {
        "standalone_query": "difference in U By Emaar Signature Credit Card and Visa Flexi Credit Card",
        "intent": "COMPARISON",
        "sub_queries": [
            "U By Emaar Signature Credit Card features fees requirements",
            "Visa Flexi Credit Card features fees requirements",
        ],
        "products_in_context": ["U By Emaar Signature Credit Card", "Visa Flexi Credit Card"],
    }
    res = await retrieve_context_node(state)
    products = res["products_in_context"]
    assert "Emirates NBD Credit Cards Directory" not in products
    assert {"U By Emaar Signature Credit Card", "Visa Flexi Credit Card"} <= set(products)
    # The router's named pair is authoritative and keeps its order (no hash-seed ordering).
    assert products == ["U By Emaar Signature Credit Card", "Visa Flexi Credit Card"]

    answer, _ = deterministic_grounded_synthesis(
        state["standalone_query"], "COMPARISON", res["retrieved_chunks"], products_in_context=products
    )
    assert "U By Emaar Signature Credit Card" in answer
    assert "Visa Flexi Credit Card" in answer


@pytest.mark.asyncio
async def test_discovery_retrieval_dedupes_single_page_collapse(monkeypatch):
    """DISCOVERY widens top_k and caps chunks per product so one page cannot fill the context."""
    calls = {}

    class FakeIndexer:
        def hybrid_search(self, query, top_k=6, query_filter=None):
            calls["top_k"] = top_k
            calls["query_filter"] = query_filter
            chunks = [
                {
                    "chunk_id": f"flexi-{i}",
                    "product_name": "Visa Flexi Credit Card",
                    "category": "Credit Cards",
                    "url": "https://www.emiratesnbd.com/en/cards/credit-cards/visa-flexi",
                    "text": f"Visa Flexi detail {i}",
                    "score": 0.9 - i * 0.01,
                }
                for i in range(6)
            ]
            chunks.append(
                {
                    "chunk_id": "emaar-0",
                    "product_name": "U By Emaar Signature Credit Card",
                    "category": "Credit Cards",
                    "url": "https://www.emiratesnbd.com/en/cards/credit-cards/u-by-emaar",
                    "text": "U By Emaar detail",
                    "score": 0.8,
                }
            )
            return chunks

    monkeypatch.setattr("app.graph.nodes.get_indexer", lambda: FakeIndexer())

    state: ChatState = {
        "standalone_query": "List all Emirates NBD credit cards",
        "raw_query": "types of credit card?",
        "intent": "DISCOVERY",
        "target_category": "Credit Cards",
        "sub_queries": ["List all Emirates NBD credit cards"],
    }
    res = await retrieve_context_node(state)
    chunks = res["retrieved_chunks"]

    assert calls["top_k"] == 20
    # Category filter is pushed down to Qdrant when the catalog knows the category
    assert calls["query_filter"] is not None

    retrieved = [c for c in chunks if not str(c.get("chunk_id", "")).startswith("catalog_")]
    flexi = [c for c in retrieved if c.get("product_name") == "Visa Flexi Credit Card"]
    assert len(flexi) == 2, "only the top two chunks per product should survive dedup"
    assert len({c.get("product_name") for c in retrieved}) >= 2

def test_fact_answer_ignores_catalog_directory_and_metadata():
    """A FACT answer must not quote catalog directories or scraper metadata as product facts."""
    chunks = [
        {
            "chunk_id": "catalog-directory-credit-cards",
            "product_name": "Emirates NBD Credit Cards Directory",
            "category": "general_catalog",
            "url": "https://www.emiratesnbd.com/en",
            "text": "What credit cards does Emirates NBD offer? Emirates NBD offers 7 Credit Cards products.",
        },
        {
            "chunk_id": "meta-0",
            "product_name": "U By Emaar Signature Credit Card (Governing Policy)",
            "category": None,
            "url": "https://www.emiratesnbd.com/en/KFS/cards",
            "text": (
                "Official Regulatory & Policy Context for: U By Emaar Signature Credit Card\n"
                "Product Category: credit-cards"
            ),
        },
        {
            "chunk_id": "u-0",
            "product_name": "U By Emaar Signature Credit Card",
            "category": "Credit Cards",
            "url": "https://www.emiratesnbd.com/en/cards/credit-cards/u-by-emaar-signature-credit-card",
            "text": (
                "Earn 6.25% back as Upoints on all Emaar spends\n"
                "Redeem Upoints at over 2500 stores across the UAE"
            ),
        },
    ]

    answer, used_chunk_ids = deterministic_grounded_synthesis(
        "What is the annual fee of U By Emaar Signature Credit Card?", "FACT", chunks
    )

    assert "Emirates NBD offers 7 Credit Cards products" not in answer
    assert "Official Regulatory & Policy Context" not in answer
    assert "Product Category: credit-cards" not in answer
    assert "6.25%" in answer
    assert used_chunk_ids == ["u-0"]


def test_targeted_inquiry_entity_pinning():
    """Explicitly named product in query must take priority over top_chunk product."""
    chunks = [
        {
            "chunk_id": "sky-0",
            "product_name": "Emirates Skywards Visa Infinite Credit Card",
            "category": "Credit Cards",
            "url": "https://www.emiratesnbd.com/en/cards/credit-cards/emirates-skywards-infinite-credit-card",
            "text": "Earn up to 2 Skywards Miles per USD spend. Complimentary Silver Tier status.",
        },
        {
            "chunk_id": "voyager-0",
            "product_name": "Voyager World Credit Card",
            "category": "Credit Cards",
            "url": "https://www.emiratesnbd.com/en/cards/credit-cards/voyager-world-credit-card",
            "text": "Earn Voyager Miles redeemable for flights with any airline and hotel stays worldwide.",
        },
    ]

    answer, _ = deterministic_grounded_synthesis(
        "tell me more about Voyager World Credit Card, what is its annual fee and minimum salary?",
        "FACT",
        chunks,
    )

    assert "Voyager World Credit Card" in answer
    assert "AED 750" in answer
    assert "AED 15,000" in answer
    assert "Skywards" not in answer


def test_clean_facts_strips_chunk_prefix_and_images():
    """Internal chunk prefixes and markdown images must never leak into answer output."""
    chunks = [
        {
            "chunk_id": "test-chunk-1",
            "product_name": "Voyager World Credit Card",
            "category": "Credit Cards",
            "url": "https://www.emiratesnbd.com/en/cards/credit-cards/voyager-world-credit-card",
            "text": (
                "[Product: Instalment Payment Plan | Category: Credit Cards | Status: active]\n"
                "Product: Voyager World Credit Card > Features\n"
                "![balance conversion](https://www.emiratesnbd.com/img.png)\n"
                "Apply Now\n"
                "Earn 3 Voyager Miles per USD spent on international transactions\n"
                "Complimentary global airport lounge access via LoungeKey"
            ),
        }
    ]

    answer, _ = deterministic_grounded_synthesis(
        "what are the perks of Voyager World Credit Card?",
        "FACT",
        chunks,
    )

    assert "[Product:" not in answer
    assert "![balance" not in answer
    assert "Apply Now" not in answer
    assert "Voyager Miles" in answer


def test_both_fees_comparison_followup():
    """'what about both of their fees?' following a comparison must retain comparison intent and both products."""
    messages = [
        {"role": "user", "content": "Compare Corporate Virtual Mobile Card and U By Emaar Signature Card"},
        {"role": "assistant", "content": "Here is a side-by-side comparison between Corporate Virtual Mobile Card and U By Emaar Signature Card..."},
    ]
    state: ChatState = {
        "raw_query": "what about both of their fees?",
        "messages": messages,
    }

    rw_res = rewrite_query_node(state)
    rewritten = rw_res["standalone_query"]
    assert "corporate virtual mobile card" in rewritten.lower()
    assert "u by emaar signature" in rewritten.lower()

    state["standalone_query"] = rewritten
    r_res = router_node(state)
    assert r_res["intent"] == "COMPARISON"
    assert len(r_res.get("products_in_context", [])) == 2

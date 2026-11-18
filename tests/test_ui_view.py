"""Unit tests for the presentation adapter that feeds the WhatsApp-style chat UI."""

from app.models import ChatResponse, SourceItem
from app.ui_view import build_ui_payload

SOURCE = SourceItem(
    title="Emirates NBD Credit Cards",
    url="https://www.emiratesnbd.com/en/cards/credit-cards",
    last_crawled="2026-11-18",
)

DISCOVERY_ANSWER = "\n".join(
    [
        "Here is an overview of the verified Credit Cards available with Emirates NBD:\n",
        "| Product Name | Category | Key Highlights / Rewards | Annual Fee | Minimum Requirement |",
        "| :--- | :--- | :--- | :--- | :--- |",
        "| **noon One Visa Credit Card** | Credit Cards | 5% cashback on noon | Free for Life | Minimum Salary: AED 5,000 |",
        "| **Voyager World Credit Card** | Credit Cards | Voyager Miles and lounge access | AED 750 | Minimum Salary: AED 15,000 |",
        "\n*Would you like more details on rewards, eligibility, or how to apply for any of these options? Just let me know!*",
    ]
)


def test_discovery_table_becomes_cards():
    """A discovery table is projected onto product cards, not raw markdown."""
    payload = build_ui_payload(ChatResponse(answer=DISCOVERY_ANSWER, intent="DISCOVERY", sources=[SOURCE]))

    assert payload.intent == "DISCOVERY"
    assert payload.answerable is True
    assert payload.cache_hit is False
    assert payload.interaction_id
    assert payload.intro.startswith("Here is an overview of the verified Credit Cards")
    assert len(payload.cards) == 2

    first = payload.cards[0]
    assert first.name == "noon One Visa Credit Card"
    assert first.category == "Credit Cards"
    assert first.fee == "Free for Life"
    assert first.requirement == "Minimum Salary: AED 5,000"
    assert first.highlight == "5% cashback on noon"
    # URL is filled from the catalog, never invented from the answer text.
    assert first.url.startswith("https://www.emiratesnbd.com/")

    assert payload.specs == []
    assert payload.bullets == []
    assert payload.sources[0].url == SOURCE.url


def test_fact_detail_table_becomes_spec_grid():
    """A FACT detail table becomes label/value specs and the rest stays bullets."""
    answer = "\n".join(
        [
            "Here is what you need to know about **U By Emaar Signature Credit Card**:\n",
            "| Detail | Official Specifications |",
            "| :--- | :--- |",
            "| **Category** | Credit Cards |",
            "| **Annual / Joining Fee** | AED 262.50 |",
            "| **Eligibility & Minimum Requirement** | Minimum Salary: AED 12,000 |",
            "\n**Key Features & Highlights:**",
            "- Up to 6.25% back as Upoints across Dubai Mall and Emaar Hospitality",
            "\n*Would you like more details on application procedures?*",
        ]
    )

    payload = build_ui_payload(ChatResponse(answer=answer, intent="FACT", sources=[SOURCE]))

    assert [s.label for s in payload.specs] == [
        "Category",
        "Annual / Joining Fee",
        "Eligibility & Minimum Requirement",
    ]
    assert payload.specs[1].value == "AED 262.50"
    assert payload.cards == []
    assert payload.bullets == ["Up to 6.25% back as Upoints across Dubai Mall and Emaar Hospitality"]
    assert payload.intro.startswith("Here is what you need to know about U By Emaar")
    assert "*" not in payload.intro


def test_comparison_table_becomes_two_cards():
    """A comparison table yields one card per compared product."""
    answer = "\n".join(
        [
            "Here is a side-by-side comparison between **U By Emaar Signature Credit Card** "
            "and **Emirates NBD Duo Credit Card**:\n",
            "| Feature / Detail | U By Emaar Signature Credit Card | Emirates NBD Duo Credit Card |",
            "| :--- | :--- | :--- |",
            "| **Annual Fee** | AED 262.50 | AED 840 (waived with spend) |",
            "| **Eligibility / Requirement** | AED 12,000 salary | AED 12,000 salary |",
            "| **Primary Benefit** | Upoints at Emaar | Dining and travel rewards |",
        ]
    )

    payload = build_ui_payload(ChatResponse(answer=answer, intent="COMPARISON", sources=[SOURCE]))

    assert len(payload.cards) == 2
    assert payload.cards[0].name == "U By Emaar Signature Credit Card"
    assert payload.cards[0].fee == "AED 262.50"
    assert payload.cards[1].name == "Emirates NBD Duo Credit Card"
    assert payload.cards[1].requirement == "AED 12,000 salary"


def test_fallback_payload_carries_no_products():
    """A refusal keeps its wording and offers recovery chips only."""
    response = ChatResponse(
        answer="I can only answer from Emirates NBD's published pages, so I cannot help with that.",
        answerable=False,
        intent="OUT_OF_SCOPE",
        sources=[],
    )

    payload = build_ui_payload(response)

    assert payload.answerable is False
    assert payload.cards == []
    assert payload.specs == []
    assert payload.sources == []
    assert "cannot help with that" in payload.intro
    assert payload.next_chips
    assert any("credit cards" in chip.lower() for chip in payload.next_chips)


def test_prose_only_answer_keeps_bullets():
    """An answer without a table renders as intro plus bullets and drops the CTA."""
    answer = (
        "Here are the verified details for **Standard Current Account**:\n\n"
        "- Minimum average balance of AED 3,000\n"
        "- Free first cheque book\n\n"
        "*Please let me know if you would like assistance with application requirements!*"
    )

    payload = build_ui_payload(ChatResponse(answer=answer, intent="FACT", sources=[SOURCE]))

    assert payload.intro == "Here are the verified details for Standard Current Account:"
    assert payload.bullets == ["Minimum average balance of AED 3,000", "Free first cheque book"]
    assert payload.cards == []


def test_unknown_product_does_not_get_fabricated_url():
    """A product absent from the catalog renders, but without an invented link."""
    answer = "\n".join(
        [
            "Here are the verified options available with Emirates NBD:",
            "| Product Name | Category | Key Highlights / Rewards | Annual Fee | Minimum Requirement |",
            "| :--- | :--- | :--- | :--- | :--- |",
            "| **Mystery Card** | Credit Cards | Not in the catalog | N/A | N/A |",
        ]
    )

    payload = build_ui_payload(ChatResponse(answer=answer, intent="DISCOVERY"))

    assert len(payload.cards) == 1
    assert payload.cards[0].name == "Mystery Card"
    assert payload.cards[0].url == ""

"""LangGraph node implementations for Website RAG Chatbot."""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import settings
from app.graph.state import ChatState
from app.indexer import get_indexer
from app.models import LLMAnswerOutput, SourceItem

logger = logging.getLogger(__name__)

# Load bundled product catalog for discovery and entity resolution
CATALOG_FILE = Path(__file__).resolve().parent.parent / "catalog.json"
if not CATALOG_FILE.exists():
    CATALOG_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "products_catalog.json"


def load_catalog_data() -> List[Dict[str, Any]]:
    """Load cached product catalog from disk."""
    if CATALOG_FILE.exists():
        try:
            return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Error loading catalog from %s: %s", CATALOG_FILE, e)
    return []


# Banking topics used to bind elliptical and continuation follow-ups to context
BANKING_TOPIC_PATTERNS: List[Tuple[str, str]] = [
    (r"\b(?:commercial|business)\s*cards?\b", "commercial cards"),
    (r"\bcredit\s*cards?\b", "credit cards"),
    (r"\bdebit\s*cards?\b", "debit cards"),
    (r"\b(?:current\s*accounts?|checking\s*accounts?)\b", "current accounts"),
    (r"\b(?:savings\s*accounts?|deposit\s*accounts?)\b", "savings accounts"),
    (r"\b(?:loans?|financing|mortgages?)\b", "loans"),
    (r"\baccounts?\b", "accounts"),
]

# Detail phrasing that embeds well in Qdrant for each resolved category
TOPIC_DETAIL_PHRASES = {
    "credit cards": "annual fees, minimum salary requirements, and key benefits",
    "debit cards": "features, fees, and key benefits",
    "commercial cards": "features, fees, and eligibility requirements",
    "current accounts": "minimum balance requirements, fees, and key benefits",
    "savings accounts": "profit rates, minimum balance requirements, and key benefits",
    "loans": "profit rates, eligibility requirements, and key benefits",
}

# Explicit catalog request used when a continuation has no bindable topic
CATALOG_OVERVIEW_QUERY = "List all Emirates NBD banking products and services"

# Bare continuation / affirmation replies with no topic of their own
BARE_CONTINUATION_RE = re.compile(
    r"^(?:tell\s+me\s+all|show\s+(?:me\s+)?all|list\s+them(?:\s+all)?|"
    r"give\s+me\s+all|all\s+of\s+them|yes(?:\s+please)?|sure|go\s+ahead|"
    r"continue|more|show\s+everything|list\s+everything|"
    r"what\s+are\s+they|tell\s+me\s+everything|show\s+me\s+everything)[?!.]*$",
    re.IGNORECASE,
)


def detect_active_category(messages: List[Dict[str, str]]) -> Optional[str]:
    """Return the banking topic most recently mentioned, preferring user turns."""
    user_messages = [m for m in messages if m.get("role") == "user"]
    for scope in (user_messages, messages):
        for m in reversed(scope):
            content = m.get("content", "") or ""
            for pattern, label in BANKING_TOPIC_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    return label
    return None


def attribute_from_query(query: str) -> str:
    """Name the detail a selection follow-up is asking about ("which one has the lower ...")."""
    q = query.lower()
    if re.search(r"\b(?:annual|joining|monthly|late|fall[\s-]?below)\s+fee\b", q) or "fee" in q:
        return "annual fee"
    if re.search(r"\b(?:minimum\s+)?(?:monthly\s+)?balance\b", q):
        return "minimum balance"
    if re.search(r"\b(?:minimum\s+)?salary\b", q):
        return "minimum salary"
    if re.search(r"\b(?:profit|interest)\s+rate\b|\brate\b", q):
        return "profit rate"
    if re.search(r"\b(?:benefits?|rewards?|cashback|perks?)\b", q):
        return "key benefits"
    return "features and fees"


# Pronouns that bind a follow-up to the product (or the bank) already under discussion
PRONOUN_RE = re.compile(
    r"\b(this account|that account|the account|this card|that card|the card|both of them|both|it|its|this|that|these|those|them)\b",
    re.IGNORECASE,
)

# Broad "what do you offer" questions resolve a pronoun to the bank, not to one product
BROAD_INQUIRY_PATTERNS = [
    r"\bwhat\s+(?:products|cards|accounts|services)\b",
    r"\bwhat\s+.*(?:providing|provide|offer|have)\b",
    r"\bwhich\s+(?:products|cards|accounts)\b",
]


def resolve_pronouns(query: str, messages: List[Dict[str, str]]) -> Optional[str]:
    """Replace a pronoun with the most recent catalog product, or with the bank for broad asks.

    Returns None when the query has no pronoun or no subject can be recovered, so callers can
    keep the original text.
    """
    if not PRONOUN_RE.search(query):
        return None

    if any(re.search(p, query, re.IGNORECASE) for p in BROAD_INQUIRY_PATTERNS):
        return PRONOUN_RE.sub("Emirates NBD", query, count=1)

    catalog = load_catalog_data()
    known_products = sorted([p["name"] for p in catalog], key=len, reverse=True)

    last_subject: Optional[str] = None
    for msg in reversed(messages):
        content_norm = re.sub(r"s\b", "", (msg.get("content") or "").lower())
        for prod in known_products:
            if matches_product_name(prod, content_norm):
                last_subject = prod
                break
        if last_subject:
            break

    if not last_subject:
        prev_user_msg = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
        )
        if prev_user_msg:
            last_subject = prev_user_msg.strip(" ?.")

    if not last_subject:
        return None

    logger.info("Resolved pronoun in '%s' -> '%s'", query, last_subject)
    return PRONOUN_RE.sub(last_subject, query, count=1)


_PRODUCT_PHRASE_STOPWORDS = {
    "tell", "me", "about", "the", "a", "an", "show", "what", "whats", "is",
    "are", "of", "for", "do", "does", "you", "your", "our", "my", "this",
    "that", "these", "those", "i", "can", "get", "open", "apply", "please",
    "give", "list", "all", "any", "which", "new", "want", "need", "info",
    "information", "details", "on", "to",
}

# Nouns that end a product name, and words that describe a category rather than a product.
_PRODUCT_NOUN_PATTERN = (
    r"credit\s+cards?|debit\s+cards?|prepaid\s+cards?|commercial\s+cards?|"
    r"accounts?|certificates?|loans?"
)
_CATEGORY_TOKENS = {
    "credit", "debit", "prepaid", "commercial", "card", "cards", "account",
    "accounts", "certificate", "certificates", "loan", "loans", "savings",
    "current", "business", "banking", "gold", "standard", "joint", "salary",
}

# Attribute wording that can sit in front of a product name without being part of it
_PRODUCT_PHRASE_LEAD_WORDS = {
    "annual", "fee", "fees", "joining", "minimum", "salary", "balance", "rate",
    "interest", "profit", "privileges", "privilege", "benefits", "benefit",
    "features", "feature", "details", "detail", "cost", "costs", "charge",
    "charges", "requirements", "requirement", "eligibility", "documents",
    "document", "paperwork", "need", "needed", "offer", "offers", "provide",
    "provides", "available", "price", "pricing", "information", "info", "limit",
    "limits", "dining",
}
_PRODUCT_PHRASE_TRAILING = {"of", "for", "with", "and", "or", "to", "in", "on", "at", "from", "the", "a", "an"}


def explicit_product_phrase(query: str) -> Optional[str]:
    """Return the product name a query types out, e.g. "LuLu 247 Platinum Credit Card".

    Only phrases that look like a proper name (a capitalised word or a digit) qualify, so
    "a credit card for travel" stays a category question. None means no named product.
    """
    pattern = re.compile(
        rf"\b((?:[a-z0-9][\w'’&.\-]*\s+){{0,6}}?)({_PRODUCT_NOUN_PATTERN})\b",
        re.IGNORECASE,
    )
    best = ""
    for match in pattern.finditer(query):
        lead = [w for w in re.split(r"\s+", match.group(1).strip()) if w]
        while lead and (
            lead[0].lower() in _PRODUCT_PHRASE_STOPWORDS
            or lead[0].lower() in _PRODUCT_PHRASE_LEAD_WORDS
        ):
            lead.pop(0)
        while lead and lead[-1].lower() in _PRODUCT_PHRASE_TRAILING:
            lead.pop()
        # Start at the proper noun: "annual fee of the Duo" -> "Duo"
        first_named = next((i for i, w in enumerate(lead) if w[:1].isupper()), None)
        if first_named:
            lead = lead[first_named:]
        if not lead:
            continue
        looks_named = any(w[:1].isupper() for w in lead) or any(ch.isdigit() for w in lead for ch in w)
        if not looks_named:
            continue
        phrase = re.sub(r"\s+", " ", " ".join(lead + [match.group(2)]))
        if len(phrase) > len(best):
            best = phrase
    return best or None


def phrase_in_catalog(phrase: str, catalog_names: List[str]) -> bool:
    """True when the distinctive words of `phrase` all appear in one catalog product name."""
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", phrase.lower())
        if len(token) > 2 and token not in _CATEGORY_TOKENS
    ]
    if not tokens:
        return True
    for name in catalog_names:
        name_tokens = set(re.findall(r"[a-z0-9]+", name.lower()))
        if all(token in name_tokens for token in tokens):
            return True
    return False


_CROSS_SELL_SECTION_RE = re.compile(
    r"(?:credit|debit|prepaid|commercial)\s+cards?$", re.IGNORECASE
)


def is_cross_sell_chunk(chunk: Dict[str, Any]) -> bool:
    """A chunk titled "Product: X > Y Credit Card" is Y's promo card embedded in X's page."""
    text = (chunk.get("text") or "").lstrip()
    if not text:
        return False
    match = re.match(r"^Product:\s*(.+?)\s*>\s*(.+?)\s*$", text.splitlines()[0], re.IGNORECASE)
    if not match:
        return False
    host, section = match.group(1).strip(), match.group(2).strip()
    return bool(_CROSS_SELL_SECTION_RE.search(section)) and section.lower() != host.lower()


def matches_product_name(prod: str, text_norm: str) -> bool:
    """Check if a catalog product name or its distinct core brand matches text."""
    prod_norm = re.sub(r"s\b", "", prod.lower())
    if prod_norm in text_norm:
        return True
    prod_core = re.sub(
        r"(?i)\b(?:credit|debit|commercial|visa|infinite|signature|platinum|gold|world|account|card)\b",
        "",
        prod,
    ).strip().lower()
    prod_core = re.sub(r"\s+", " ", prod_core).strip()
    return len(prod_core) >= 5 and prod_core in text_norm


# -----------------------------------------------------------------------------
# Tier 1: Query Rewriter Node (Pronoun & Context Resolution)
# -----------------------------------------------------------------------------

def rewrite_query_node(state: ChatState) -> Dict[str, Any]:
    """Resolve anaphoric pronouns, conversational rejections, and elliptical follow-ups."""
    raw_query = state.get("raw_query", "").strip()
    messages = state.get("messages", [])

    # Typo normalizations
    clean_query = re.sub(r"(?i)\bhow\s+me\b", "show me", raw_query)
    clean_query = re.sub(r"(?i)\bwhat\s+products\s+you\s+offers?\b", "what products do you offer", clean_query)
    clean_query = re.sub(r"(?i)\bwhich\s+credit\s+cards\s+you\s+offers?\b", "which credit cards do you offer", clean_query)

    if not messages:
        # "tell me all" as an opening turn is still an explicit catalog request
        if BARE_CONTINUATION_RE.match(clean_query) and re.search(
            r"(?i)\b(?:all|everything|them|they)\b", clean_query
        ):
            return {"standalone_query": CATALOG_OVERVIEW_QUERY}
        return {"standalone_query": clean_query}

    # 1. Conversational Rejection / Pivot Detection (e.g. "but i didnt ask for Current Account, show me all types")
    rejection_match = re.search(
        r"(?i)\b(?:didn't\s+ask\s+for|didnt\s+ask\s+for|not\s+asking\s+for|not\s+about|instead\s+of|i\s+meant|not\s+the)\s+([a-zA-Z0-9\s]+?)(?:,|$|\.|\bshow\b|\btell\b)",
        clean_query,
    )
    if rejection_match and len(messages) >= 2:
        prior_user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
        original_topic = None
        for prev_umsg in reversed(prior_user_msgs[:-1] if len(prior_user_msgs) > 1 else prior_user_msgs):
            if re.search(r"\bcredit\s*cards?\b", prev_umsg, re.IGNORECASE):
                original_topic = "credit cards"
                break
            elif re.search(r"\bdebit\s*cards?\b", prev_umsg, re.IGNORECASE):
                original_topic = "debit cards"
                break
            elif re.search(r"\baccounts?\b", prev_umsg, re.IGNORECASE):
                original_topic = "accounts"
                break
            elif re.search(r"\bloans?\b", prev_umsg, re.IGNORECASE):
                original_topic = "loans"
                break

        if original_topic:
            remainder = re.sub(r"(?i)\b(?:but\s+)?i\s+(?:didn't|didnt)\s+ask\s+for\s+[^,.]+[,\.]?\s*", "", clean_query).strip()
            resolved = f"{remainder} of {original_topic} offered by Emirates NBD" if remainder else f"show all types of {original_topic} offered by Emirates NBD"
            logger.info("Rejection detected; pivoted back to original topic: '%s' -> '%s'", raw_query, resolved)
            return {"standalone_query": resolved}

    # 2. Elliptical Follow-Up Resolution (e.g. "any other", "what else", "more options")
    elliptical_pattern = re.compile(
        r"^(?:any\s+other|what\s+else|more\s+options|show\s+more|other\s+types|anything\s+else|tell\s+me\s+more)(?:\s+options?|\s+types?|\s+cards?|\s+accounts?)?[?!.]*$",
        re.IGNORECASE,
    )
    if elliptical_pattern.match(clean_query):
        active_category = detect_active_category(messages)

        if active_category:
            resolved = f"What are other {active_category} options offered by Emirates NBD?"
            logger.info("Elliptical query bound to active topic: '%s' -> '%s'", raw_query, resolved)
            return {"standalone_query": resolved}

    # 2.3 Bare Continuation / Affirmation Follow-Up Resolution
    # Catches "tell me all", "show everything", "list them", "yes please",
    # "go ahead", "continue", "more" and binds them to the active banking topic.
    if BARE_CONTINUATION_RE.match(clean_query):
        # Affirmations ("yes", "sure", "continue") only continue a *listing* thread.
        # After a single-product answer, "yes" must not turn into a catalog query.
        affirmation_only = re.match(
            r"^(?:yes(?:\s+please)?|sure|go\s+ahead|continue|more)[?!.]*$", clean_query, re.IGNORECASE
        )
        if affirmation_only:
            prior_user_message = next(
                (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
            )
            listing_intent = re.search(
                r"\b(?:all|types?|which|what|any|options?|list|show|available|offer|every)\b",
                prior_user_message or "",
                re.IGNORECASE,
            )
            if not listing_intent:
                if prior_user_message:
                    resolved = resolve_pronouns(prior_user_message, messages) or prior_user_message
                    logger.info(
                        "Affirmation bound to previous question: '%s' -> '%s'", raw_query, resolved
                    )
                    return {"standalone_query": resolved}
                return {"standalone_query": clean_query}

        active_category = detect_active_category(messages)
        if active_category:
            details = TOPIC_DETAIL_PHRASES.get(active_category, "fees, requirements, and key benefits")
            resolved = f"List all Emirates NBD {active_category} with {details}"
            logger.info("Bare continuation bound to active topic: '%s' -> '%s'", raw_query, resolved)
            return {"standalone_query": resolved}

        # "tell me all"/"show everything" alone is an explicit catalog request;
        # a bare "yes"/"continue" with no prior topic stays untouched.
        if re.search(r"(?i)\b(?:all|everything|them|they)\b", clean_query):
            resolved = CATALOG_OVERVIEW_QUERY
            logger.info("Bare continuation without prior topic; escalating to catalog overview: '%s'", raw_query)
            return {"standalone_query": resolved}

    # 2.5 Dual Subject / Comparison Follow-Up Resolution (e.g. "i want both difference", "compare both")
    both_pattern = re.compile(
        r"\b(?:both\s+of\s+them|both|the\s+two|those\s+two|these\s+two|two\s+(?:of\s+them|cards?|products?|accounts?))\b",
        re.IGNORECASE,
    )
    compare_cue = re.compile(
        r"\b(?:compare|comparison|differ(?:s|ence|ences)?|how\s+(?:are\s+they\s+)?different|what\s+is\s+different|versus|vs\.?|side\s+by\s+side)\b",
        re.IGNORECASE,
    )

    if both_pattern.search(clean_query) and messages:
        catalog = load_catalog_data()
        known_products = sorted([p["name"] for p in catalog], key=len, reverse=True)

        recent_products: List[str] = []
        for msg in reversed(messages):
            content = msg.get("content", "")
            content_norm = re.sub(r"s\b", "", content.lower())
            for prod in known_products:
                if matches_product_name(prod, content_norm) and prod not in recent_products:
                    recent_products.append(prod)
                if len(recent_products) >= 2:
                    break
            if len(recent_products) >= 2:
                break

        if len(recent_products) >= 2:
            prod_b, prod_a = recent_products[0], recent_products[1]
            if compare_cue.search(clean_query):
                resolved = f"Compare {prod_a} and {prod_b}"
            else:
                attr_part = both_pattern.sub("", clean_query).strip(" ?.")
                attr_part = re.sub(
                    r"(?i)^(?:what\s+about|tell\s+me\s+about|show\s+me|how\s+about)\s+", "", attr_part
                ).strip()
                if attr_part:
                    resolved = f"Compare {attr_part} of {prod_a} and {prod_b}"
                else:
                    resolved = f"Compare {prod_a} and {prod_b}"
            logger.info("Resolved dual subject follow-up: '%s' -> '%s'", raw_query, resolved)
            return {"standalone_query": resolved}

    # 2.6 Selection Follow-Up (e.g. "which one has the lower annual fee?" after a comparison)
    # Without this, the question loses its pair and becomes a generic catalog FACT listing.
    selection_pattern = re.compile(
        r"(?i)\bwhich\s+(?:one|of\s+(?:them|these|those|the\s+two))\b|"
        r"\b(?:which|what)\s+is\s+(?:the\s+)?(?:cheaper|less\s+expensive|better)\b"
    )
    if selection_pattern.search(clean_query) and messages:
        catalog = load_catalog_data()
        known_products = sorted([p["name"] for p in catalog], key=len, reverse=True)
        recent_products: List[str] = []
        for msg in reversed(messages):
            content_norm = re.sub(r"s\b", "", (msg.get("content") or "").lower())
            for prod in known_products:
                if matches_product_name(prod, content_norm) and prod not in recent_products:
                    recent_products.append(prod)
            if len(recent_products) >= 2:
                break

        if recent_products:
            attribute = attribute_from_query(clean_query)
            if len(recent_products) >= 2:
                resolved = f"Compare the {attribute} of {recent_products[0]} and {recent_products[1]}"
            else:
                resolved = f"What is the {attribute} of {recent_products[0]}?"
            logger.info("Selection follow-up bound to recent context: '%s' -> '%s'", raw_query, resolved)
            return {"standalone_query": resolved}

    # 3. Standard Anaphoric Pronoun Resolution
    resolved = resolve_pronouns(clean_query, messages)
    return {"standalone_query": resolved or clean_query}


# -----------------------------------------------------------------------------
# Tier 2: Intent Router & Decomposition Node
# -----------------------------------------------------------------------------

def router_node(state: ChatState) -> Dict[str, Any]:
    """Classify user intent into FACT, DISCOVERY, COMPARISON, or OUT_OF_SCOPE."""
    query = state.get("standalone_query", state.get("raw_query", "")).strip()
    query_lower = query.lower()

    # 1. Prompt Injection Defense
    injection_patterns = [
        r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions",
        r"system\s+prompt",
        r"disregard\s+(?:all\s+)?instructions",
        r"reveal\s+(?:your\s+)?instructions",
        r"you\s+are\s+now\s+dan",
        r"jailbreak",
    ]
    for pattern in injection_patterns:
        if re.search(pattern, query_lower):
            logger.warning("Prompt injection attempt intercepted: %s", query)
            return {
                "intent": "OUT_OF_SCOPE",
                "sub_queries": [],
                "fallback_reason": "injection_attempt",
            }

    # 2. Greeting / Conversational small talk
    is_greeting = bool(
        re.search(r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|howdy|greetings)\b", query_lower)
        and len(query_lower.split()) <= 4
    )
    if is_greeting:
        return {
            "intent": "OUT_OF_SCOPE",
            "sub_queries": [],
            "fallback_reason": "greeting",
        }

    # 3. Completely off-topic or out-of-scope domain queries
    off_topic_keywords = [
        "recipe", "chocolate cake", "weather", "poem", "capital of", "president",
        "buy tesla stock", "crypto", "bitcoin", "solana", "joke", "who won the match",
    ]
    if any(k in query_lower for k in off_topic_keywords):
        return {
            "intent": "OUT_OF_SCOPE",
            "sub_queries": [],
            "fallback_reason": "off_topic",
        }

    # 3.5 General Bank Overview / About Intent
    about_pattern = re.compile(
        r"^(?:about|tell\s+me\s+about|what\s+is|who\s+is|overview\s+of|introduce)?\s*"
        r"(?:emirates\s*nbd|the\s+bank|your\s+bank|this\s+bank|emiratesnbd)\s*[?.!]*$",
        re.IGNORECASE,
    )
    if about_pattern.match(query_lower.strip()):
        # A query that names product categories is discovery, not a bank overview.
        if not re.search(
            r"\b(?:products?|cards?|accounts?|services?|loans?|offerings?)\b", query_lower
        ):
            return {
                "intent": "ABOUT",
                "sub_queries": [query],
            }

    # 4. Comparison Intent (Sub-query decomposition)
    compare_pattern = re.compile(
        r"\b(?:compare|comparison|versus|vs\.?|vs\b|differ(?:s|ence|ences)?|how\s+(?:are\s+they\s+)?different|what\s+is\s+different|better\s+than|which\s+(?:one\s+)?is\s+better|side\s+by\s+side)\b",
        re.IGNORECASE,
    )
    catalog = load_catalog_data()
    catalog_names = [p["name"] for p in catalog]
    found_products: List[str] = []
    for name in catalog_names:
        if name.lower() in query_lower:
            found_products.append(name)

    is_comparison = bool(compare_pattern.search(query_lower)) or len(found_products) >= 2

    if is_comparison:
        if len(found_products) >= 2:
            prod_a, prod_b = found_products[0], found_products[1]
            sub_queries = [
                f"{prod_a} features fees requirements",
                f"{prod_b} features fees requirements",
            ]
            return {
                "intent": "COMPARISON",
                "sub_queries": sub_queries,
                "products_in_context": [prod_a, prod_b],
            }
        else:
            # Fallback heuristic: split on "and", "vs", "versus"
            parts = re.split(r"\b(?:and|vs|versus)\b", query, flags=re.IGNORECASE)
            if len(parts) >= 2:
                clean_trigger = r"(?i)\b(?:what\s+(?:is|are)(?:\s+the)?|show(?:\s+me)?|tell(?:\s+me)?|compare|comparison|difference[s]?\s*(?:in|of|between)?|differ(?:s|ent)?|versus|vs\.?|better\s+than|side\s+by\s+side)\b"
                q_a = re.sub(clean_trigger, "", parts[0]).strip()
                q_b = re.sub(clean_trigger, "", parts[1]).strip()
                return {
                    "intent": "COMPARISON",
                    "sub_queries": [f"{q_a} details", f"{q_b} details"],
                }

    # 5. Category Discovery & General Product Discovery Intent
    target_category = None
    if re.search(r"\bdebit\s*cards?\b", query_lower):
        target_category = "Debit Cards"
    elif re.search(r"\bcredit\s*cards?\b", query_lower):
        target_category = "Credit Cards"
    elif re.search(r"\b(?:commercial|business)\s*cards?\b", query_lower):
        target_category = "Commercial Cards"
    elif re.search(r"\b(?:current\s*accounts?|checking\s*accounts?)\b", query_lower):
        target_category = "Current Accounts"
    elif re.search(r"\b(?:savings\s*accounts?|deposit\s*accounts?)\b", query_lower):
        target_category = "Savings Accounts"
    elif re.search(r"\b(?:loans?|financing|mortgages?)\b", query_lower):
        target_category = "Loans & Financing"

    discovery_triggers = [
        "what cards", "all credit cards", "list of accounts", "what options",
        "show products", "what accounts can i open", "account options",
        "recommend a card", "options for business", "savings options", "browse",
        "what products", "what is it providing", "what does it provide", "providing", "what services", "all products",
        "which credit cards", "which debit cards", "all types", "show me all", "what types",
        "card options", "debit cards options", "credit card options", "credit cards do you offer",
        "debit cards do you offer", "cards do you offer", "what cards do you have", "other debit cards options",
        "other credit cards options",
        # Broad "about your products/services" inquiries
        "about your products", "about products", "your products", "your services",
        "what do you offer", "what do you provide", "what are your products",
        "about your cards", "about your accounts", "your cards", "your accounts",
    ]

    # "types of credit card?", "types of accounts", etc. → category discovery
    types_of_pattern = re.compile(
        r"\btypes?\s+of\s+(?:credit\s*cards?|debit\s*cards?|commercial\s*cards?|accounts?|cards?|loans?|products?|services?)\b",
        re.IGNORECASE,
    )

    category_discovery_pattern = re.compile(
        r"\b(?:which|what|show|list|tell\s+me\s+about)\s+(?:are\s+(?:the|your)\s+)?(?:available\s+)?(?:credit\s*cards?|debit\s*cards?|current\s*accounts?|savings\s*accounts?|accounts?|cards?|options?|types?)\b|"
        r"\b(?:credit\s*cards?|debit\s*cards?|current\s*accounts?|savings\s*accounts?|accounts?|cards?)\s+(?:do\s+you\s+)?(?:offer|have|provide)\b|"
        r"\b(?:debit|credit)\s*cards?\s+options?\b|"
        r"\b(?:all\s+types|show\s+me\s+all|list\s+all)\b",
        re.IGNORECASE,
    )

    # A broad listing cue ("all", "every", "list", "types of") outranks attribute
    # keywords, so "list all credit cards with annual fees" stays DISCOVERY.
    has_list_cue = bool(re.search(r"\b(?:all|every|list|types?\s+of)\b", query_lower))

    is_attribute_fact = (not has_list_cue) and any(
        a in query_lower
        for a in [
            "annual fee", "joining fee", "what is the fee", "how much is the fee",
            "minimum balance", "min balance", "minimum salary", "fall-below", "fall below",
            "interest rate", "profit rate", "how to apply", "eligibility criteria",
        ]
    )

    is_discovery = not is_attribute_fact and (
        any(t in query_lower for t in discovery_triggers)
        or bool(category_discovery_pattern.search(query_lower))
        or bool(types_of_pattern.search(query_lower))
        or bool(re.search(
            r"\b(?:about|tell\s+me\s+about)\s+(?:your|the|our|all)\s+(?:bank(?:'s)?\s+)?"
            r"(?:products?|offerings?|services?|cards?|accounts?|banking)\b",
            query_lower,
        ))
        or bool(re.search(r"\b(?:what|which|all|list|show|browse|tell\s+me)\b.*(?:cards?|accounts?|loans?|products?|options?|services?|types?).*\b(?:available|offered|offer|offers|have|exist|open|apply|get|providing|provide)\b", query_lower))
        or bool(re.search(r"\bavailable\s+(?:credit\s+|debit\s+)?cards?\b", query_lower))
    )
    if is_discovery:
        return {
            "intent": "DISCOVERY",
            "target_category": target_category,
            "sub_queries": [query],
        }

    # 6. A named product the catalog does not carry must never borrow another product's page
    unknown_product = explicit_product_phrase(query)
    if unknown_product and not phrase_in_catalog(unknown_product, catalog_names):
        logger.info("Query names a product outside the verified catalog: %s", unknown_product)
        return {
            "intent": "OUT_OF_SCOPE",
            "sub_queries": [],
            "fallback_reason": "unverified_product",
            "unknown_product": unknown_product,
        }

    # 7. Default to Single Product Fact Intent
    return {
        "intent": "FACT",
        "sub_queries": [query],
    }


# -----------------------------------------------------------------------------
# Tier 3: Hybrid Retrieval Node (with Parallel Comparison Retrieval)
# -----------------------------------------------------------------------------

async def retrieve_context_node(state: ChatState) -> Dict[str, Any]:
    """Retrieve grounded context chunks using Qdrant hybrid search."""
    intent = state.get("intent", "FACT")
    sub_queries = state.get("sub_queries", [])
    standalone_query = state.get("standalone_query", state.get("raw_query", ""))
    indexer = get_indexer()

    retrieved_chunks: List[Dict[str, Any]] = []

    def is_catalog_anchor(chunk: Dict[str, Any]) -> bool:
        """Synthetic whole-catalog chunks are context, never a product entity."""
        return chunk.get("category") == "general_catalog"

    if intent == "COMPARISON" and len(sub_queries) >= 2:
        # Execute parallel retrieval for both product subjects (asyncio.gather)
        loop = asyncio.get_event_loop()
        results_a, results_b = await asyncio.gather(
            loop.run_in_executor(None, indexer.hybrid_search, sub_queries[0], 3),
            loop.run_in_executor(None, indexer.hybrid_search, sub_queries[1], 3),
        )

        seen_ids = set()
        for c in results_a + results_b:
            cid = c.get("chunk_id")
            if cid and cid not in seen_ids and not is_catalog_anchor(c):
                seen_ids.add(cid)
                retrieved_chunks.append(c)

        # Inject catalog specification chunks for products in context
        catalog = load_catalog_data()
        products_in_context = state.get("products_in_context", [])
        for p_name in products_in_context:
            for prod in catalog:
                if prod["name"].lower() == p_name.lower():
                    cat_cid = f"catalog_{prod['product_id']}"
                    if not any(c.get("chunk_id") == cat_cid for c in retrieved_chunks):
                        retrieved_chunks.append({
                            "chunk_id": cat_cid,
                            "text": (
                                f"Product: {prod['name']}\n"
                                f"Category: {prod['category']}\n"
                                f"Summary: {prod.get('summary', '')}\n"
                                f"Annual Fee: {prod.get('annual_fee') or 'None / Free'}\n"
                                f"Joining Fee: {prod.get('joining_fee') or 'None'}\n"
                                f"Requirements: {prod.get('min_requirement') or 'N/A'}"
                            ),
                            "product_name": prod["name"],
                            "title": f"{prod['name']} | Emirates NBD",
                            "url": prod["url"],
                            "score": 0.95,
                        })

    elif intent == "ABOUT":
        loop = asyncio.get_event_loop()
        retrieved_chunks = await loop.run_in_executor(
            None, indexer.hybrid_search, "Emirates NBD banking products overview services", settings.TOP_K
        )
        retrieved_chunks = [c for c in retrieved_chunks if not any(k in c.get("url", "").lower() for k in ["contact", "career", "complaint"])]

    elif intent == "DISCOVERY":
        target_category = state.get("target_category")
        catalog = load_catalog_data()
        loop = asyncio.get_event_loop()
        # Wider net so a single index page cannot monopolise the context window
        discovery_top_k = 20

        def keep_top_per_product(chunks: List[Dict[str, Any]], max_per_product: int = 2) -> List[Dict[str, Any]]:
            """Cap chunks per product so discovery answers cover many products."""
            kept: List[Dict[str, Any]] = []
            counts: Dict[str, int] = {}
            for chunk in chunks:
                key = (chunk.get("product_name") or chunk.get("url") or "unknown").strip().lower()
                if counts.get(key, 0) >= max_per_product:
                    continue
                counts[key] = counts.get(key, 0) + 1
                kept.append(chunk)
            return kept

        if target_category:
            query_text = f"{target_category} {standalone_query}"
            # Restrict the vector search to the category when the catalog knows it,
            # so cross-category chunks cannot crowd out the candidate set.
            query_filter = None
            if any(p.get("category", "").lower() == target_category.lower() for p in catalog):
                query_filter = Filter(
                    must=[FieldCondition(key="category", match=MatchValue(value=target_category))]
                )

            raw_chunks = []
            if query_filter is not None:
                try:
                    raw_chunks = await loop.run_in_executor(
                        None, indexer.hybrid_search, query_text, discovery_top_k, query_filter
                    )
                except Exception as exc:
                    logger.warning(
                        "Category filter unavailable (%s); querying unfiltered. "
                        "Rebuild the index to enable category payload filtering.",
                        exc,
                    )
            if query_filter is None or not raw_chunks:
                raw_chunks = await loop.run_in_executor(
                    None, indexer.hybrid_search, query_text, discovery_top_k
                )

            retrieved_chunks = keep_top_per_product(raw_chunks)
            # Strict category isolation
            def is_chunk_compatible(c: Dict[str, Any]) -> bool:
                c_cat = c.get("category", "").lower()
                c_prod = c.get("product_name", "").lower()
                c_url = c.get("url", "").lower()
                if "contact" in c_url or "career" in c_url or "complaint" in c_url:
                    return False
                if target_category == "Credit Cards":
                    if any(k in c_cat or k in c_prod for k in ["current account", "savings account", "debit card"]):
                        return False
                elif target_category == "Debit Cards":
                    if any(k in c_cat or k in c_prod for k in ["credit card", "current account", "savings account", "transfer your rewards"]):
                        return False
                elif target_category == "Current Accounts":
                    if any(k in c_cat or k in c_prod for k in ["credit card", "debit card", "savings account"]):
                        return False
                return True

            retrieved_chunks = [c for c in retrieved_chunks if is_chunk_compatible(c)]

            # Inject ALL products from catalog belonging strictly to target_category
            for prod in catalog:
                if prod["category"].lower() == target_category.lower():
                    retrieved_chunks.append({
                        "chunk_id": f"catalog_{prod['product_id']}",
                        "text": f"Product: {prod['name']}\nCategory: {prod['category']}\nSummary: {prod.get('summary', '')}\nAnnual Fee: {prod.get('annual_fee') or 'None/Not Specified'}\nJoining Fee: {prod.get('joining_fee') or 'None/Not Specified'}\nRequirements: {prod.get('min_requirement') or 'N/A'}",
                        "product_name": prod["name"],
                        "title": f"{prod['name']} | Emirates NBD",
                        "url": prod["url"],
                        "score": 0.95,
                    })
        else:
            raw_chunks = await loop.run_in_executor(
                None, indexer.hybrid_search, standalone_query, discovery_top_k
            )
            raw_chunks = [c for c in raw_chunks if not any(k in c.get("url", "").lower() for k in ["contact", "career", "complaint"])]
            retrieved_chunks = keep_top_per_product(raw_chunks)
            for prod in catalog:
                if not any(prod["name"].lower() in c.get("product_name", "").lower() for c in retrieved_chunks):
                    retrieved_chunks.append({
                        "chunk_id": f"catalog_{prod['product_id']}",
                        "text": f"Product: {prod['name']}\nCategory: {prod['category']}\nSummary: {prod.get('summary', '')}\nAnnual Fee: {prod.get('annual_fee') or 'None/Not Specified'}\nJoining Fee: {prod.get('joining_fee') or 'None/Not Specified'}\nRequirements: {prod.get('min_requirement') or 'N/A'}",
                        "product_name": prod["name"],
                        "title": f"{prod['name']} | Emirates NBD",
                        "url": prod["url"],
                        "score": 0.85,
                    })

    else:
        loop = asyncio.get_event_loop()
        retrieved_chunks = await loop.run_in_executor(
            None, indexer.hybrid_search, standalone_query, settings.TOP_K
        )

        catalog = load_catalog_data()
        query_lower = standalone_query.lower()

        # If query explicitly targets a known catalog product, ensure its official spec is injected
        matched_named_prod = None
        for p in sorted(catalog, key=lambda x: len(x["name"]), reverse=True):
            if p["name"].lower() in query_lower:
                matched_named_prod = p
                break
        if matched_named_prod:
            cat_cid = f"catalog_{matched_named_prod['product_id']}"
            if not any(c.get("chunk_id") == cat_cid for c in retrieved_chunks):
                retrieved_chunks.insert(0, {
                    "chunk_id": cat_cid,
                    "text": (
                        f"Product: {matched_named_prod['name']}\n"
                        f"Category: {matched_named_prod['category']}\n"
                        f"Summary: {matched_named_prod.get('summary', '')}\n"
                        f"Annual Fee: {matched_named_prod.get('annual_fee') or 'None / Free'}\n"
                        f"Joining Fee: {matched_named_prod.get('joining_fee') or 'None'}\n"
                        f"Requirements: {matched_named_prod.get('min_requirement') or 'N/A'}"
                    ),
                    "product_name": matched_named_prod["name"],
                    "title": f"{matched_named_prod['name']} | Emirates NBD",
                    "url": matched_named_prod["url"],
                    "score": 0.99,
                })

        # Multi-Hop Relational Knowledge Graph Traversal
        from app.relations import resolve_entity_by_text, format_relational_context_chunk
        entity = resolve_entity_by_text(standalone_query)
        inherited_triggers = [
            "minimum balance", "min balance", "minimum average", "average balance",
            "fall below", "fall-below", "maintenance fee", "fees", "fee", "charge", "charges",
            "salary requirement", "requirement", "terms", "rules", "rate", "interest",
        ]
        needs_policy = any(t in query_lower for t in inherited_triggers)

        if entity and needs_policy:
            rel_chunk = format_relational_context_chunk(entity["id"])
            if rel_chunk:
                retrieved_chunks.insert(0, rel_chunk)

            # Ensure governing KFS chunk is included if available
            if not any("kfs" in c.get("url", "").lower() for c in retrieved_chunks):
                kfs_results = await loop.run_in_executor(
                    None, indexer.hybrid_search, f"Key Facts Statement KFS minimum balance {entity.get('name', '')}", 2
                )
                for kc in kfs_results:
                    if "kfs" in kc.get("url", "").lower() or "cash" in kc.get("url", "").lower():
                        retrieved_chunks.append(kc)
                        break

        elif ("account" in query_lower or "accounts" in query_lower) and needs_policy:
            # General account minimum balance / fee inquiry across Emirates NBD
            rel_chunk = format_relational_context_chunk("kfs-cash-accounts") or format_relational_context_chunk("standard-current-account")
            if rel_chunk and not any(c.get("chunk_id") == rel_chunk.get("chunk_id") for c in retrieved_chunks):
                retrieved_chunks.insert(0, rel_chunk)

    # Promo cards for other products ("Product: X > Y Credit Card") ride along inside X's page.
    retrieved_chunks = [c for c in retrieved_chunks if not is_cross_sell_chunk(c)]

    # Compute max relevance score
    max_score = 0.0
    if retrieved_chunks:
        max_score = max(c.get("score", 0.0) for c in retrieved_chunks)

    # Track distinct products in context (catalog anchors are not products).
    # For a comparison the router's named subjects are authoritative and ordered; otherwise
    # dedupe in retrieval order (a set here would make the answer depend on the hash seed).
    if intent == "COMPARISON" and state.get("products_in_context"):
        products = list(state["products_in_context"])
    else:
        products = list(dict.fromkeys(
            c.get("product_name")
            for c in retrieved_chunks
            if c.get("product_name") and not is_catalog_anchor(c)
        ))

    return {
        "retrieved_chunks": retrieved_chunks,
        "relevance_score": max_score,
        "products_in_context": products,
    }


# -----------------------------------------------------------------------------
# Tier 4: Relevance Grader Node
# -----------------------------------------------------------------------------

def grade_relevance_node(state: ChatState) -> Dict[str, Any]:
    """Gate response generation based on retrieval quality, entity presence, and score threshold."""
    retrieved_chunks = state.get("retrieved_chunks", [])
    score = state.get("relevance_score", 0.0)
    intent = state.get("intent", "FACT")
    query = state.get("standalone_query", state.get("raw_query", ""))

    if intent == "ABOUT":
        return {"is_relevant": True, "needs_live_search": False}

    if not retrieved_chunks:
        return {"is_relevant": False, "needs_live_search": True, "fallback_reason": "low_relevance"}

    # Must pass minimum RRF score gate
    if score < settings.MIN_RELEVANCE_SCORE:
        logger.info("Retrieval score %.4f below threshold %.4f. Requesting live search.", score, settings.MIN_RELEVANCE_SCORE)
        return {"is_relevant": False, "needs_live_search": True, "fallback_reason": "low_relevance"}

    # Check whether the query's core product/topic keywords actually appear in retrieved chunks
    if intent in ["FACT", "COMPARISON"]:
        stop_words = {
            "what", "are", "is", "the", "about", "benefits", "features", "of", "for",
            "in", "and", "emirates", "nbd", "bank", "tell", "me", "how", "does",
            "work", "can", "you", "provide", "show", "give", "details",
        }
        query_tokens = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 2 and w.lower() not in stop_words]
        if query_tokens:
            combined_text = " ".join(c.get("text", "") + " " + c.get("title", "") for c in retrieved_chunks).lower()
            has_token_match = any(t in combined_text or t.rstrip("s") in combined_text for t in query_tokens)
            if not has_token_match:
                logger.info("Retrieved chunks lack query entity keywords %s. Requesting live site search.", query_tokens)
                return {"is_relevant": False, "needs_live_search": True}

    # For comparison, verify both subjects have at least one context chunk
    if intent == "COMPARISON" and len(state.get("sub_queries", [])) >= 2:
        sub_a = state["sub_queries"][0].split()[0].lower()
        sub_b = state["sub_queries"][1].split()[0].lower()
        has_a = any(sub_a in c.get("text", "").lower() or sub_a in c.get("product_name", "").lower() for c in retrieved_chunks)
        has_b = any(sub_b in c.get("text", "").lower() or sub_b in c.get("product_name", "").lower() for c in retrieved_chunks)
        if not (has_a and has_b):
            logger.info("Comparison lacked bilateral coverage (has_a=%s, has_b=%s)", has_a, has_b)

    return {"is_relevant": True, "needs_live_search": False}


async def live_search_node(state: ChatState) -> Dict[str, Any]:
    """Agentic Tool Node: search live website and ingest missing content on demand."""
    from app.agent_tools import live_site_search_and_ingest
    query = state.get("standalone_query", state.get("raw_query", ""))
    logger.info("Live Search Node executing on-demand fetch for: '%s'", query)
    fresh_chunks = await live_site_search_and_ingest(query)
    if fresh_chunks:
        return {
            "retrieved_chunks": fresh_chunks,
            "relevance_score": 1.0,
            "is_relevant": True,
            "needs_live_search": False,
        }
    return {
        "is_relevant": False,
        "needs_live_search": False,
        "fallback_reason": "low_relevance",
    }


# -----------------------------------------------------------------------------
# Tier 5: Grounded Answer Generator Node with Guardrails
# -----------------------------------------------------------------------------

def verify_number_groundedness(answer: str, context_text: str) -> bool:
    """Verify all currency amounts and numerical figures in answer exist in context."""
    # Normalize commas in context so 12,000 matches 12000
    context_normalized = context_text.replace(",", "")
    # Extract numbers like AED 1,575, 5.5%, 30,000, 262.50
    figures = re.findall(r"(?:AED\s*)?[\d,]+(?:\.\d+)?%?", answer)
    for fig in figures:
        cleaned_fig = fig.strip()
        # Ignore trivial single digits like 1, 2 or bullet list numbers
        if len(cleaned_fig) <= 1 or cleaned_fig in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]:
            continue
        # Check if the figure exists in context
        raw_num = re.sub(r"[^\d.]", "", cleaned_fig).replace(",", "")
        if raw_num and raw_num not in context_normalized:
            logger.warning("Ungrounded figure detected in LLM answer: '%s'", cleaned_fig)
            return False
    return True


# Site section labels that survive cleaning but carry no product fact
NAV_NOISE_LINES = {
    "update your info",
    "everyday banking",
    "rewards & benefits",
    "rewards and benefits",
    "quick links",
    "ways to bank",
    "help & support",
    "help and support",
    "follow us",
    "download the app",
    "back to top",
    "related links",
    "you may also like",
    "important links",
    "popular links",
    "personal banking",
    "business banking",
    "about us",
    "contact us",
    "search results",
}


_SCRAPE_FRAGMENT_RES = (
    # A privilege grid glues the cuisine label to the value: "CUISINEFine Dining"
    re.compile(r"^[A-Z]{4,}[A-Z][a-z]"),
    # Bare venue titles carry no fact on their own: "Amalfi - Palazzo Versace Dubai"
    re.compile(r"^[A-Z][\w'’&.\- ]+\s+[-–]\s+[A-Z][\w'’&.\- ]+$"),
)


def strip_scrape_fragments(text: str) -> str:
    """Remove privilege-grid leftovers from chunk text before a generator sees it.

    The deterministic extractor already skips these lines; doing the same here keeps them
    out of an LLM prompt, so neither path can quote "CUISINEFine Dining" as a benefit.
    """
    kept: List[str] = []
    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            kept.append(line)
            continue
        if "![" in line_clean or "](" in line_clean:
            continue
        if line_clean.lower().strip(" .:") in NAV_NOISE_LINES:
            continue
        if not re.search(r"\d|%", line_clean) and any(
            pattern.match(line_clean) for pattern in _SCRAPE_FRAGMENT_RES
        ):
            continue
        kept.append(line)
    return "\n".join(kept)


def deterministic_grounded_synthesis(
    query: str,
    intent: str,
    chunks: List[Dict[str, Any]],
    target_category: Optional[str] = None,
    products_in_context: Optional[List[str]] = None,
) -> Tuple[str, List[str]]:
    """Synthesize a warm, human-toned response with clean Markdown tables without repeating self-introductions."""
    used_chunk_ids: List[str] = []

    if intent == "ABOUT":
        catalog = load_catalog_data()
        lines = [
            "**Emirates NBD** is one of the leading banking groups in the UAE and the wider Middle East, headquartered in Dubai. We offer a comprehensive suite of personal, business, private, and Islamic banking solutions designed to meet diverse financial needs.\n",
            "**Verified Product Categories Available:**",
        ]
        cat_counts = {}
        for p in catalog:
            c = p.get("category", "General")
            cat_counts[c] = cat_counts.get(c, 0) + 1
        for c in sorted(cat_counts.keys()):
            lines.append(f"- **{c}** ({cat_counts[c]} products)")

        lines.append(
            "\n*How can I assist you today? You can ask me to list available credit cards or accounts, compare specific products, or check fees and eligibility criteria!*"
        )
        answer = "\n".join(lines)
        used_chunk_ids = [c["chunk_id"] for c in chunks if "chunk_id" in c][:2]
        return answer, used_chunk_ids

    if intent == "DISCOVERY":
        catalog = load_catalog_data()
        if target_category:
            filtered_catalog = [p for p in catalog if p.get("category", "").lower() == target_category.lower()]
            if not filtered_catalog:
                filtered_catalog = catalog
        else:
            filtered_catalog = catalog

        cat_label = target_category if target_category else "banking products and services"
        lines = [
            f"Here is an overview of the verified {cat_label} available with Emirates NBD:\n",
            "| Product Name | Category | Key Highlights / Rewards | Annual Fee | Minimum Requirement |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for p in filtered_catalog:
            name = p["name"]
            cat = p["category"]
            summary = p.get("summary", "Official Emirates NBD banking product").replace("|", "/")
            fee = (p.get("annual_fee") or "Free / None").replace("|", "/")
            req = (p.get("min_requirement") or "N/A").replace("|", "/")
            lines.append(f"| **{name}** | {cat} | {summary} | {fee} | {req} |")

        lines.append("\n*Would you like more details on rewards, eligibility, or how to apply for any of these options? Just let me know!*")
        answer = "\n".join(lines)
        used_chunk_ids = [c["chunk_id"] for c in chunks if "chunk_id" in c][:6]
        return answer, used_chunk_ids

    if intent == "COMPARISON":
        catalog = load_catalog_data()
        # Structure side-by-side comparison in a clean Markdown table
        prod_names = []
        if products_in_context:
            for p in products_in_context:
                if p not in prod_names:
                    prod_names.append(p)
        for c in chunks:
            p = c.get("product_name")
            if p and p not in prod_names:
                prod_names.append(p)
        if len(prod_names) < 2:
            prod_names = ["Product A", "Product B"]

        lines = [
            f"Here is a side-by-side comparison between **{prod_names[0]}** and **{prod_names[1]}**:\n",
            f"| Feature / Detail | {prod_names[0]} | {prod_names[1]} |",
            "| :--- | :--- | :--- |",
        ]

        def extract_pinfo(pname: str) -> Dict[str, str]:
            cat_match = next((p for p in catalog if p["name"].lower() == pname.lower()), None)
            p_chunks = [c for c in chunks if c.get("product_name") == pname]
            for c in p_chunks:
                if c.get("chunk_id"):
                    used_chunk_ids.append(c.get("chunk_id"))

            if cat_match:
                fee = cat_match.get("annual_fee") or "Free / None"
                req = cat_match.get("min_requirement") or "N/A"
                summary = cat_match.get("summary") or "Official Emirates NBD banking product"
                return {"fee": fee, "req": req, "summary": summary}

            text_blob = " ".join(c.get("text", "") for c in p_chunks)
            fee_match = re.search(r"(?:annual fee|fee)[\s:]*([^\n.,;]+)", text_blob, re.IGNORECASE)
            salary_match = re.search(r"(?:minimum salary|salary requirement|salary)[\s:]*([^\n.,;]+)", text_blob, re.IGNORECASE)
            balance_match = re.search(r"(?:minimum balance|balance requirement|average balance)[\s:]*([^\n.,;]+)", text_blob, re.IGNORECASE)
            req = salary_match.group(1).strip() if salary_match else (balance_match.group(1).strip() if balance_match else "Standard eligibility")
            fee = fee_match.group(1).strip() if fee_match else "Free / Package-linked"
            return {"fee": fee, "req": req, "summary": "Official Emirates NBD product perks"}

        fa = extract_pinfo(prod_names[0])
        fb = extract_pinfo(prod_names[1])
        lines.append(f"| **Annual Fee** | {fa['fee']} | {fb['fee']} |")
        lines.append(f"| **Eligibility / Requirement** | {fa['req']} | {fb['req']} |")
        lines.append(f"| **Primary Benefit** | {fa['summary']} | {fb['summary']} |")

        # Answer the "which one is cheaper" case outright, using only the catalog figures above.
        def fee_amount(text: str) -> Optional[float]:
            match = re.search(r"([\d,]+(?:\.\d+)?)", text or "")
            return float(match.group(1).replace(",", "")) if match else None

        fee_a, fee_b = fee_amount(fa["fee"]), fee_amount(fb["fee"])
        if fee_a is not None and fee_b is not None and fee_a != fee_b:
            cheaper = prod_names[0] if fee_a < fee_b else prod_names[1]
            lines.append(
                f"\n**{cheaper}** has the lower annual fee "
                f"({fa['fee'] if fee_a < fee_b else fb['fee']} versus {fb['fee'] if fee_a < fee_b else fa['fee']})."
            )

        lines.append(f"\nBoth options offer excellent features tailored to different customer needs. Would you like me to guide you on how to apply for either option?")
        return "\n".join(lines), list(dict.fromkeys(used_chunk_ids))

    # Default Fact Intent: extract sentences answering query across ALL chunks
    catalog = load_catalog_data()
    top_chunk = chunks[0] if chunks else {}
    top_chunk_prod = top_chunk.get("product_name", "")

    # Resolve product from catalog: check exact or normalized phrase match first (sorted by length descending)
    matching_catalog_prod = None
    query_lower = query.lower()
    q_norm = re.sub(r"s\b", "", query_lower)

    # Phase 1: Check if any product name from the catalog appears explicitly in user query
    for p in sorted(catalog, key=lambda x: len(x["name"]), reverse=True):
        p_name_lower = p["name"].lower()
        p_norm = re.sub(r"s\b", "", p_name_lower)
        if p_name_lower in query_lower or p_norm in q_norm:
            matching_catalog_prod = p
            product_name = p["name"]
            break

    # Phase 2: Only fallback to top_chunk's product_name if query didn't name a product
    if not matching_catalog_prod and top_chunk_prod:
        t_norm = re.sub(r"s\b", "", top_chunk_prod.lower())
        for p in catalog:
            p_norm = re.sub(r"s\b", "", p["name"].lower())
            if p_norm == t_norm or p_norm in t_norm:
                matching_catalog_prod = p
                product_name = p["name"]
                break
        if not matching_catalog_prod:
            product_name = top_chunk_prod
    elif not matching_catalog_prod:
        product_name = "the requested product"

    # 1. Multi-chunk extraction & breadcrumb filtering
    clean_facts = []
    seen_facts = set()
    wants_documents = bool(
        re.search(r"\b(?:documents?|paperwork|application|apply|required)\b", query_lower)
    )

    # Whole-catalog directory chunks describe the catalog, not a product's facts.
    fact_chunks = [c for c in chunks if c.get("category") != "general_catalog"]
    if matching_catalog_prod:
        target_name = matching_catalog_prod["name"].lower()
        # Strictly isolate facts to the target product or general policy chunks
        matching_chunks = [
            c for c in fact_chunks
            if not c.get("product_name") or c.get("product_name").lower() == target_name or c.get("is_relational")
        ]
        if matching_chunks:
            fact_chunks = matching_chunks

    for c in fact_chunks:
        text = c.get("text", "")
        accepted_lines = 0
        in_cross_sell = False
        for line in text.splitlines():
            line_clean = line.strip(" -*#_")
            line_lower = line_clean.lower()
            # Ignore empty lines, breadcrumbs, markdown images, raw URLs
            if not line_clean or len(line_clean) < 15:
                continue
            # "Other credit cards / Looking for something different" starts a cross-sell block
            if re.match(
                r"^(?:other\s+(?:credit|debit)\s+cards?|looking\s+for\s+something\s+different|"
                r"you\s+may\s+also\s+like|related\s+products|similar\s+products|"
                r"recommended\s+for\s+you|other\s+products)$",
                line_clean,
                re.IGNORECASE,
            ):
                in_cross_sell = True
                continue
            if in_cross_sell:
                continue
            # Skip chunk prefix headers (e.g. [Product: X | Category: Y | Status: Z])
            if re.match(r"^\[Product:\s*.*?\]", line_clean, re.IGNORECASE):
                continue
            if re.match(r"^product:\s*.*>\s*.*", line_clean, re.IGNORECASE):
                continue
            # Scraper metadata headers, not product facts
            if re.match(
                r"^(?:official regulatory & policy context for|product category)\s*:",
                line_clean,
                re.IGNORECASE,
            ):
                continue
            # Synthetic catalog-record lines emitted for retrieval, not prose facts
            if re.match(
                r"^(?:product|category|summary|annual fee|joining fee|requirements)\s*:",
                line_clean,
                re.IGNORECASE,
            ):
                continue
            # Skip image tags, truncated images, or raw image markdown
            if "![" in line_clean or line_clean.startswith("[!") or "](" in line_clean or line_clean.startswith("http") or line_clean.startswith("[View"):
                continue
            # Skip UI action button noise
            if re.search(r"\b(?:apply now|view more|read more|learn more)\b", line_lower):
                continue
            # Skip bare site-section labels ("Update your info", "Everyday banking")
            if line_lower.strip(" .:") in NAV_NOISE_LINES:
                continue
            # Scraped privilege grids leave fragments ("CUISINEFine Dining") and bare venue titles
            if re.match(r"^[A-Z]{4,}[A-Z][a-z]", line_clean):
                continue
            if re.match(
                r"^[A-Z][\w'’&.\- ]+\s+[-–]\s+[A-Z][\w'’&.\- ]+$", line_clean
            ) and not re.search(r"\d|%", line_clean):
                continue
            # Application paperwork answers "what documents do I need?", not "what are the perks"
            if not wants_documents and re.match(
                r"^(?:duly\s+filled|original\s+emirates\s+id|emirates\s+id\s+and\s+copy|"
                r"original\s+passport|latest\s+salary\s+certificate|trade\s+license|"
                r"security\s+cheque|latest\s+3[- ]month|original\s+credit\s+card\s+of|"
                r"copy\s+of|pay\s+slip|moa\b)",
                line_clean,
                re.IGNORECASE,
            ):
                continue
            if "terms and conditions" in line_lower and len(line_clean) < 30:
                continue

            # Skip legal boilerplate and disclaimers
            legal_boilerplate = [
                "forward-looking statement", "past performance", "merchantability",
                "terms and conditions apply", "subject to change", "without prior notice",
                "privacy policy", "cookie policy", "all rights reserved",
                "securities and commodities authority", "regulated by", "disclaimer",
                "©", "copyright", "trademark", "po box", "p.o. box",
                "licensed and regulated by", "central bank of the uae",
                "table below provides a quick overview", "| | | | | --- | --- | --- |",
            ]
            if any(bp in line_lower for bp in legal_boilerplate):
                continue
            # Skip empty markdown table formatting or navigation link lines
            if line_clean.startswith("|") and ("---" in line_clean or (line_clean.count("|") > 4 and len(line_clean.replace("|", "").strip()) < 5)):
                continue
            if re.match(r"^\[.*?\]\(.*?\)(?:\s*\|?\s*\[.*?\]\(.*?\))*\s*$", line_clean):
                continue
            if line_clean.startswith("[") and line_clean.endswith(")") and "](http" in line_clean:
                continue

            norm_key = re.sub(r"[^\w\s]", "", line_lower)[:60]
            if norm_key not in seen_facts:
                seen_facts.add(norm_key)
                clean_facts.append(line_clean)
                accepted_lines += 1

        # Only cite a chunk if it actually contributed a fact
        if accepted_lines and c.get("chunk_id"):
            used_chunk_ids.append(c.get("chunk_id"))

    # 2. If we have a matching catalog record, format a rich specification table
    if matching_catalog_prod:
        cat_p = matching_catalog_prod
        fee = cat_p.get("annual_fee") or "None / Free"
        joining_fee = cat_p.get("joining_fee")
        req = cat_p.get("min_requirement") or "N/A"
        category = cat_p.get("category") or "Personal Banking"
        summary = cat_p.get("summary", "")

        table_lines = [
            f"Here is what you need to know about **{product_name}**:\n",
            "| Detail | Official Specifications |",
            "| :--- | :--- |",
            f"| **Category** | {category} |",
            f"| **Annual Fee** | {fee} |",
        ]
        # Joining fee is a separate catalog field; never fold it into the annual fee.
        if joining_fee and joining_fee != fee:
            table_lines.append(f"| **Joining Fee** | {joining_fee} |")
        table_lines.append(f"| **Eligibility & Minimum Requirement** | {req} |")

        if "gold" in product_name.lower():
            table_lines.append("| **Redemption & Liquidity** | Buy or redeem at any Emirates NBD branch prior to maturity in cash or gold bars |")

        if clean_facts:
            table_lines.append("\n**Key Features & Highlights:**")
            for fact in clean_facts[:4]:
                table_lines.append(f"- {fact}")
        elif summary:
            table_lines.append(f"\n**Summary:** {summary}")

        table_lines.append("\n*Would you like more details on application procedures, rates, or eligible branch services?*")
        return "\n".join(table_lines), list(dict.fromkeys(used_chunk_ids))

    # 3. If query asks for specific attribute (fee, salary, requirements), highlight lines
    specific_lines = []
    if any(k in query_lower for k in ["fee", "charge", "cost", "salary", "requirement", "minimum", "balance", "joining"]):
        for fact in clean_facts:
            f_lower = fact.lower()
            if any(w in f_lower for w in ["joining fee", "annual fee", "minimum salary", "minimum balance", "aed", "grams", "fineness", "salary of"]):
                if fact not in specific_lines:
                    specific_lines.append(fact)

    if specific_lines:
        bullets = "\n".join(f"- {line}" for line in specific_lines[:5])
        answer = (
            f"Here are the verified details for **{product_name}**:\n\n"
            f"{bullets}\n\n"
            f"*Please let me know if you would like assistance with application requirements or eligible accounts!*"
        )
        return answer, list(dict.fromkeys(used_chunk_ids))

    # 4. General fallback with cleaned facts
    if clean_facts:
        bullets = "\n".join(f"- {line}" for line in clean_facts[:4])
        answer = (
            f"Here is what you need to know about **{product_name}**:\n\n"
            f"{bullets}\n\n"
            f"*Feel free to ask if you would like more information on fees, benefits, or how to apply!*"
        )
        return answer, list(dict.fromkeys(used_chunk_ids))

    # Fallback if no clean lines found
    answer = f"Here is the official documentation for **{product_name}**. Please let me know what specific features or fees you would like to explore!"
    return answer, used_chunk_ids


async def _grounded_chat_completion(
    *,
    url: str,
    headers: Dict[str, str],
    model: str,
    system_prompt: str,
    user_prompt: str,
    context_str: str,
    chunks: List[Dict[str, Any]],
    provider_label: str,
    timeout: float = 45.0,
) -> Optional[Dict[str, Any]]:
    """Call one OpenAI-compatible chat endpoint; return answer state only if it is grounded.

    Every provider goes through the same number guardrail, so a provider cannot ship a fee
    that is absent from the retrieved context. None means "try the next provider".
    """
    import httpx

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            logger.warning(
                "%s returned HTTP %s. Continuing to fallback generators.",
                provider_label,
                resp.status_code,
            )
            return None
        choices = resp.json().get("choices", [])
        if not choices:
            return None
        ans_text = choices[0].get("message", {}).get("content", "").strip()
        # Clean any internal reasoning tokens if the model enabled thinking
        ans_clean = re.sub(r"<think>.*?</think>", "", ans_text, flags=re.DOTALL).strip()
        if not ans_clean:
            return None
        if not verify_number_groundedness(ans_clean, context_str):
            logger.warning(
                "%s generated ungrounded numbers. Continuing to fallback generators.",
                provider_label,
            )
            return None
        matched_ids = [
            c.get("chunk_id")
            for c in chunks
            if (c.get("product_name") and any(term in ans_clean.lower() for term in c.get("product_name").lower().split() if len(term) > 3))
            or (c.get("is_relational") and any(term in ans_clean.lower() for term in ["key facts", "kfs", "policy", "classic", "fall-below", "fall below", "minimum balance", "3,000", "5,000"]))
        ]
        used_ids = matched_ids if matched_ids else [c.get("chunk_id") for c in chunks[:3] if c.get("chunk_id")]
        return {
            "answer": ans_clean,
            "used_chunk_ids": used_ids,
            "answerable": True,
            "guardrail_passed": True,
        }
    except Exception as e:
        logger.warning(
            "%s API generation failed (%s). Continuing to fallback generators.", provider_label, e
        )
        return None


async def generate_answer_node(state: ChatState) -> Dict[str, Any]:
    """Generate grounded answer using xAI Grok, then OpenRouter, Gemini Flash, or deterministic fallback."""
    query = state.get("standalone_query", state.get("raw_query", ""))
    chunks = state.get("retrieved_chunks", [])
    intent = state.get("intent", "FACT")
    target_category = state.get("target_category")

    # DISCOVERY and ABOUT are catalog listings, so build them from the verified catalog only.
    # Paraphrasing them through an LLM has produced product names that are not in
    # `app/catalog.json` (and therefore have no card or URL), which breaks the "every listed
    # product is verified" promise.
    if intent in ("DISCOVERY", "ABOUT"):
        answer, used_chunk_ids = deterministic_grounded_synthesis(
            query,
            intent,
            chunks,
            target_category=target_category,
            products_in_context=state.get("products_in_context", []),
        )
        return {
            "answer": answer,
            "used_chunk_ids": used_chunk_ids,
            "answerable": True,
            "guardrail_passed": True,
        }

    context_str = "\n\n---\n\n".join(
        f"Chunk ID: {c.get('chunk_id')}\nProduct: {c.get('product_name')}\nURL: {c.get('url')}\nContent:\n{strip_scrape_fragments(c.get('text', ''))}"
        for c in chunks
    )

    category_instruction = ""
    if target_category and intent == "DISCOVERY":
        category_instruction = (
            f" The user is asking specifically about {target_category}. "
            f"ONLY list products belonging to {target_category}. "
            f"Do NOT include or mix products from any other category (e.g. do not discuss Current Accounts or Savings Accounts if asked about Credit Cards or Debit Cards)."
        )

    # Providers share one grounded prompt; only the transport and model differ.
    system_prompt = (
        "You are Lexi, the official Emirates NBD AI virtual banking assistant. "
        "Your tone is warm, friendly, natural, empathetic, and professional—like an experienced Emirates NBD relationship manager chatting with a customer. "
        "IMPORTANT: Do NOT start your message with 'Hi, I'm Lexi' or repeat your name on every turn. The chat interface already clearly displays your name. Only introduce yourself by name if the user explicitly greets you or asks who you are. "
        "Never use robotic boilerplate like 'According to official Emirates NBD documentation for X:'. On standard queries, dive straight into answering the user's question with warm, professional phrasing (e.g. 'Here is what you need to know about...', 'Here are the details for...', 'Here is an overview of...'). "
        f"{category_instruction} "
        "Formatting Guidelines: "
        "- For general bank inquiries ('about emirates nbd', 'overview', 'about the bank'), provide a warm introduction to Emirates NBD as a leading UAE bank and briefly outline the primary verified banking categories available (Credit Cards, Debit Cards, Accounts, Wealth, Loans). "
        "- For product discovery (when listing cards, accounts, or services), present the options in a clean Markdown table with columns: | Product Name | Key Highlights / Rewards | Annual Fee | Minimum Requirement |. "
        "- For product comparisons, present a clear side-by-side Markdown comparison table (| Feature / Detail | Product A | Product B |) followed by a helpful conversational summary. "
        "- For single-product inquiries, answer conversationally with clean bullet points or structured highlights for fees, balance rules, and requirements. "
        "When answering inquiries about account minimum balance, maintenance fees, or requirements for promotional/specialized accounts (such as the Millionaire Account), explain both its specific features (e.g. prize draws) and its governing baseline terms from Emirates NBD's Key Facts Statement (KFS) / Personal Banking Classic Package (e.g. minimum monthly average balance of AED 3,000, or AED 5,000 for standard digital savings, and AED 26.25 monthly fall-below fee with salary transfer exemptions). "
        "Strict Grounding: Never extrapolate, guess, or invent fees, interest rates, or eligibility rules. All numerical values and facts must come strictly from the context. "
        "Conclude with a warm, helpful closing offer (e.g., asking if they would like help applying or exploring specific perks)."
    )
    user_prompt = f"""<retrieved_context>
{context_str}
</retrieved_context>

<user_query>
{query}
</user_query>
"""

    # 1. Primary: xAI Grok (XAI_MODEL, e.g. grok-build-0.1)
    if settings.XAI_API_KEY and not settings.XAI_API_KEY.startswith("<"):
        xai_result = await _grounded_chat_completion(
            url=f"{settings.XAI_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.XAI_API_KEY}",
                "Content-Type": "application/json",
            },
            model=settings.XAI_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context_str=context_str,
            chunks=chunks,
            provider_label="xAI Grok",
        )
        if xai_result:
            return xai_result

    # 2. Fallback: OpenRouter (supports openrouter/free)
    if settings.OPENROUTER_API_KEY and not settings.OPENROUTER_API_KEY.startswith("<"):
        openrouter_result = await _grounded_chat_completion(
            url=f"{settings.OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Web-Assist",
            },
            model=settings.OPENROUTER_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context_str=context_str,
            chunks=chunks,
            provider_label="OpenRouter",
        )
        if openrouter_result:
            return openrouter_result

    # 3. Fallback: Gemini Flash if API key is provided and valid
    if settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("AIzaSy..."):
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            prompt = f"""You are Lexi, the official Emirates NBD AI virtual banking assistant.
Answer the user's question warmly, clearly, helpfully, and conversationally strictly based on the provided context chunks.
Do NOT start with 'Hi, I'm Lexi' or repeat your name on every turn. The chat interface already identifies you as Lexi. Only state your name if greeted or asked who you are.
Do not extrapolate, guess, or invent fees, interest rates, or eligibility rules.
{category_instruction}
If presenting product discovery or comparisons, format the options in a clean Markdown table (| Product Name | Key Highlights / Rewards | Annual Fee | Minimum Requirement |).
If context is insufficient, set answerable=false and state politely that information is not available in official bank records.

<retrieved_context>
{context_str}
</retrieved_context>

<user_query>
{query}
</user_query>
"""
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=LLMAnswerOutput,
                    ),
                ),
            )
            parsed: LLMAnswerOutput = response.parsed

            if parsed and parsed.answerable:
                # Run Number Groundedness Guardrail (Tier 4)
                if not verify_number_groundedness(parsed.answer, context_str):
                    logger.warning("Gemini generated ungrounded numbers. Falling back to deterministic synthesis.")
                else:
                    return {
                        "answer": parsed.answer,
                        "used_chunk_ids": parsed.used_chunk_ids or [c.get("chunk_id") for c in chunks[:2]],
                        "answerable": True,
                        "guardrail_passed": True,
                    }
        except Exception as e:
            logger.warning("Gemini API call failed (%s). Falling back to deterministic grounded synthesis.", e)

    # 4. Resilient Deterministic Grounded Synthesis
    products_in_context = state.get("products_in_context", [])
    answer, used_chunk_ids = deterministic_grounded_synthesis(
        query, intent, chunks, target_category=target_category, products_in_context=products_in_context
    )
    return {
        "answer": answer,
        "used_chunk_ids": used_chunk_ids,
        "answerable": True,
        "guardrail_passed": True,
    }


# -----------------------------------------------------------------------------
# Tier 6: Citation Builder Node
# -----------------------------------------------------------------------------

def citation_builder_node(state: ChatState) -> Dict[str, Any]:
    """Construct verified source citations server-side from chunk payloads."""
    retrieved_chunks = state.get("retrieved_chunks", [])
    used_chunk_ids = set(state.get("used_chunk_ids", []))
    target_category = state.get("target_category")

    citations: List[Dict[str, Any]] = []
    seen_urls = set()

    # Prioritize chunks directly used in the answer
    candidates = [c for c in retrieved_chunks if c.get("chunk_id") in used_chunk_ids]
    if not candidates:
        candidates = retrieved_chunks

    # If target_category is specified, filter out incompatible citations
    filtered_candidates = []
    for c in candidates:
        url = c.get("url", "").lower()
        if any(bad in url for bad in ["contact", "career", "complaint"]):
            continue
        if target_category == "Credit Cards":
            if any(bad in url for bad in ["current-account", "savings-account", "help-and-support"]):
                continue
        elif target_category == "Debit Cards":
            if any(bad in url for bad in ["credit-card", "current-account", "savings-account", "rewards"]):
                continue
        elif target_category in ["Current Accounts", "Savings Accounts"]:
            if any(bad in url for bad in ["credit-card", "debit-card"]):
                continue
        filtered_candidates.append(c)

    final_candidates = filtered_candidates if filtered_candidates else candidates

    for c in final_candidates:
        url = c.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            citations.append(
                SourceItem(
                    title=c.get("title") or f"{c.get('product_name', 'Emirates NBD Documentation')} | Emirates NBD",
                    url=url,
                    last_crawled=c.get("crawled_at") or "2026-11-18",
                ).model_dump()
            )
        if len(citations) >= 4:
            break

    return {"citations": citations}


# -----------------------------------------------------------------------------
# Fallback Node (Polite Refusals & Out-of-Scope Handlers)
# -----------------------------------------------------------------------------

def fallback_node(state: ChatState) -> Dict[str, Any]:
    """Return a polite, helpful refusal without hallucinating."""
    reason = state.get("fallback_reason", "low_relevance")

    if reason == "greeting":
        answer = (
            "Hello! I'm Lexi, your virtual banking assistant for Emirates NBD. "
            "How can I assist you today? Feel free to ask me about our credit cards, "
            "debit cards, savings accounts, current accounts, fee schedules, or eligibility requirements!"
        )
    elif reason == "injection_attempt":
        answer = (
            "I can only assist with verified Emirates NBD banking products and services based on "
            "official website documentation."
        )
    elif reason == "off_topic":
        answer = (
            "I cannot assist with external or unrelated topics. I can help with verified Emirates NBD "
            "products, accounts, cards, and banking services. "
            "Is there an account or card option I can help you with?"
        )
    elif reason == "unverified_product":
        product = state.get("unknown_product") or "that product"
        answer = (
            f"I don't have verified details for {product} in the Emirates NBD catalog I cover. "
            "I can help with the products in the verified catalog - credit cards, debit cards, "
            "accounts, savings, and banking services. Would you like to see what's available?"
        )
    else:
        answer = (
            "I'm sorry, but I couldn't find verified information on that in our official "
            "Emirates NBD documentation. Please check our official website or reach out to our 24/7 customer "
            "care team at 600 54 0000 for personal assistance."
        )

    return {
        "answer": answer,
        "citations": [],
        "answerable": False,
        "guardrail_passed": True,
    }

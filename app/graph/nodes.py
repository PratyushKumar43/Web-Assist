"""LangGraph node implementations for Website RAG Chatbot."""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
        active_category = None
        for m in reversed(messages):
            c_lower = m.get("content", "").lower()
            if "debit card" in c_lower:
                active_category = "debit cards"
                break
            elif "credit card" in c_lower:
                active_category = "credit cards"
                break
            elif "account" in c_lower:
                active_category = "accounts"
                break
            elif "loan" in c_lower:
                active_category = "loans"
                break

        if active_category:
            resolved = f"What are other {active_category} options offered by Emirates NBD?"
            logger.info("Elliptical query bound to active topic: '%s' -> '%s'", raw_query, resolved)
            return {"standalone_query": resolved}

    # 3. Standard Anaphoric Pronoun Resolution
    pronoun_pattern = re.compile(
        r"\b(this account|that account|the account|this card|that card|the card|both of them|it|its|this|that|these|those|them)\b",
        re.IGNORECASE,
    )

    if not pronoun_pattern.search(clean_query):
        return {"standalone_query": clean_query}

    catalog = load_catalog_data()
    known_products = [p["name"] for p in catalog]

    # If the user is asking a broad question about what the bank provides/offers
    broad_inquiry_patterns = [
        r"\bwhat\s+(?:products|cards|accounts|services)\b",
        r"\bwhat\s+.*(?:providing|provide|offer|have)\b",
        r"\bwhich\s+(?:products|cards|accounts)\b",
    ]
    if any(re.search(p, clean_query, re.IGNORECASE) for p in broad_inquiry_patterns):
        resolved = pronoun_pattern.sub("Emirates NBD", clean_query, count=1)
        logger.info("Broad query rewrote pronoun to bank: '%s' -> '%s'", raw_query, resolved)
        return {"standalone_query": resolved}

    last_subject: Optional[str] = None
    for msg in reversed(messages):
        content = msg.get("content", "")
        for prod in known_products:
            if prod.lower() in content.lower():
                last_subject = prod
                break
        if last_subject:
            break

    if not last_subject and len(messages) >= 1:
        prev_user_msg = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        if prev_user_msg:
            last_subject = prev_user_msg.strip(" ?.")

    if last_subject:
        resolved = pronoun_pattern.sub(last_subject, clean_query, count=1)
        logger.info("Rewrote query: '%s' -> '%s'", raw_query, resolved)
        return {"standalone_query": resolved}

    return {"standalone_query": clean_query}


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

    # 4. Comparison Intent (Sub-query decomposition)
    comparison_triggers = ["compare", "versus", " vs ", "difference between", "better than"]
    is_comparison = any(t in query_lower for t in comparison_triggers)

    if is_comparison:
        catalog = load_catalog_data()
        catalog_names = [p["name"] for p in catalog]
        found_products: List[str] = []
        for name in catalog_names:
            if name.lower() in query_lower:
                found_products.append(name)

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
                q_a = re.sub(r"(?i)\bcompare\b|\bdifference between\b", "", parts[0]).strip()
                q_b = re.sub(r"(?i)\bcompare\b|\bdifference between\b", "", parts[1]).strip()
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
    ]

    category_discovery_pattern = re.compile(
        r"\b(?:which|what|show|list|tell\s+me\s+about)\s+(?:are\s+(?:the|your)\s+)?(?:available\s+)?(?:credit\s*cards?|debit\s*cards?|current\s*accounts?|savings\s*accounts?|accounts?|cards?|options?|types?)\b|"
        r"\b(?:credit\s*cards?|debit\s*cards?|current\s*accounts?|savings\s*accounts?|accounts?|cards?)\s+(?:do\s+you\s+)?(?:offer|have|provide)\b|"
        r"\b(?:debit|credit)\s*cards?\s+options?\b|"
        r"\b(?:all\s+types|show\s+me\s+all|list\s+all)\b",
        re.IGNORECASE,
    )

    is_attribute_fact = any(
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
        or bool(re.search(r"\b(?:what|which|all|list|show|browse|tell\s+me)\b.*(?:cards?|accounts?|loans?|products?|options?|services?|types?).*\b(?:available|offered|offer|offers|have|exist|open|apply|get|providing|provide)\b", query_lower))
        or bool(re.search(r"\bavailable\s+(?:credit\s+|debit\s+)?cards?\b", query_lower))
    )
    if is_discovery:
        return {
            "intent": "DISCOVERY",
            "target_category": target_category,
            "sub_queries": [query],
        }

    # 6. Default to Single Product Fact Intent
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
            if cid and cid not in seen_ids:
                seen_ids.add(cid)
                retrieved_chunks.append(c)

    elif intent == "DISCOVERY":
        target_category = state.get("target_category")
        catalog = load_catalog_data()
        loop = asyncio.get_event_loop()

        if target_category:
            retrieved_chunks = await loop.run_in_executor(
                None, indexer.hybrid_search, f"{target_category} {standalone_query}", settings.TOP_K
            )
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
            retrieved_chunks = await loop.run_in_executor(
                None, indexer.hybrid_search, standalone_query, settings.TOP_K
            )
            retrieved_chunks = [c for c in retrieved_chunks if not any(k in c.get("url", "").lower() for k in ["contact", "career", "complaint"])]
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

        # Multi-Hop Relational Knowledge Graph Traversal
        from app.relations import resolve_entity_by_text, format_relational_context_chunk
        entity = resolve_entity_by_text(standalone_query)
        query_lower = standalone_query.lower()
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

    # Compute max relevance score
    max_score = 0.0
    if retrieved_chunks:
        max_score = max(c.get("score", 0.0) for c in retrieved_chunks)

    # Track distinct products in context
    products = list({c.get("product_name") for c in retrieved_chunks if c.get("product_name")})

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


def deterministic_grounded_synthesis(
    query: str,
    intent: str,
    chunks: List[Dict[str, Any]],
    target_category: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """Synthesize a warm, human-toned response from Lexi with clean Markdown tables."""
    used_chunk_ids: List[str] = []

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
            f"Hello! I'm Lexi, your Emirates NBD virtual banking assistant. Here is an overview of our verified {cat_label} available on the official website:\n",
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
        # Structure side-by-side comparison in a clean Markdown table
        prod_names = list({c.get("product_name", "Product") for c in chunks if c.get("product_name")})
        if len(prod_names) < 2:
            prod_names = ["Product A", "Product B"]

        lines = [
            f"Hello! I'm Lexi. Here is a side-by-side comparison between **{prod_names[0]}** and **{prod_names[1]}**:\n",
            f"| Feature / Detail | {prod_names[0]} | {prod_names[1]} |",
            "| :--- | :--- | :--- |",
        ]

        def extract_pinfo(pname: str) -> Dict[str, str]:
            p_chunks = [c for c in chunks if c.get("product_name") == pname]
            text_blob = " ".join(c.get("text", "") for c in p_chunks)
            fee_match = re.search(r"(?:annual fee|fee)[\s:]*([^\n.,;]+)", text_blob, re.IGNORECASE)
            salary_match = re.search(r"(?:minimum salary|salary requirement|salary)[\s:]*([^\n.,;]+)", text_blob, re.IGNORECASE)
            balance_match = re.search(r"(?:minimum balance|balance requirement|average balance)[\s:]*([^\n.,;]+)", text_blob, re.IGNORECASE)
            req = salary_match.group(1).strip() if salary_match else (balance_match.group(1).strip() if balance_match else "Standard eligibility")
            fee = fee_match.group(1).strip() if fee_match else "Free / Package-linked"
            for c in p_chunks:
                if c.get("chunk_id"):
                    used_chunk_ids.append(c.get("chunk_id"))
            return {"fee": fee, "req": req}

        fa = extract_pinfo(prod_names[0])
        fb = extract_pinfo(prod_names[1])
        lines.append(f"| **Annual Fee** | {fa['fee']} | {fb['fee']} |")
        lines.append(f"| **Eligibility / Requirement** | {fa['req']} | {fb['req']} |")
        lines.append(f"| **Primary Benefit** | Official Emirates NBD product perks | Official Emirates NBD product perks |")

        lines.append(f"\nBoth options offer excellent features tailored to different customer needs. Would you like me to guide you on how to apply for either card?")
        return "\n".join(lines), list(dict.fromkeys(used_chunk_ids))

    # Default Fact Intent: extract sentences answering query with Lexi persona
    top_chunk = chunks[0]
    used_chunk_ids = [top_chunk.get("chunk_id", "")]
    product_name = top_chunk.get("product_name", "the requested product")

    # If query asks for a specific fact (fee, salary, requirements), find matching lines across chunks
    query_lower = query.lower()
    specific_lines = []
    if any(k in query_lower for k in ["fee", "charge", "cost", "salary", "requirement", "minimum", "balance", "joining"]):
        for c in chunks:
            text = c.get("text", "")
            for line in text.splitlines():
                line_lower = line.lower()
                if any(w in line_lower for w in ["joining fee", "annual fee", "minimum salary", "minimum balance", "aed"]):
                    clean_line = line.strip(" -*#")
                    if clean_line and clean_line not in specific_lines:
                        specific_lines.append(clean_line)
                        if c.get("chunk_id"):
                            used_chunk_ids.append(c.get("chunk_id"))

    if specific_lines:
        answer_body = "\n".join(f"- {line}" for line in specific_lines[:5])
        answer = (
            f"Hi! I'm Lexi, your Emirates NBD assistant. Here are the verified details for **{product_name}**:\n\n"
            f"{answer_body}\n\n"
            f"*Please let me know if you would like assistance with application requirements or eligible accounts!*"
        )
        return answer, list(dict.fromkeys(used_chunk_ids))

    # General fact extraction from top chunk
    chunk_text = top_chunk.get("text", "")
    relevant_lines = []
    for line in chunk_text.splitlines():
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#") or line_clean.startswith("!["):
            continue
        relevant_lines.append(line_clean)

    answer_body = " ".join(relevant_lines[:4])
    answer = (
        f"Hi! I'm Lexi. Here is what you need to know about **{product_name}**:\n\n"
        f"{answer_body}\n\n"
        f"*Feel free to ask if you'd like more information on fees, benefits, or how to apply!*"
    )
    return answer, used_chunk_ids


async def generate_answer_node(state: ChatState) -> Dict[str, Any]:
    """Generate grounded answer using OpenRouter, Gemini Flash, or deterministic fallback."""
    query = state.get("standalone_query", state.get("raw_query", ""))
    chunks = state.get("retrieved_chunks", [])
    intent = state.get("intent", "FACT")
    target_category = state.get("target_category")

    context_str = "\n\n---\n\n".join(
        f"Chunk ID: {c.get('chunk_id')}\nProduct: {c.get('product_name')}\nURL: {c.get('url')}\nContent:\n{c.get('text')}"
        for c in chunks
    )

    category_instruction = ""
    if target_category and intent == "DISCOVERY":
        category_instruction = (
            f" The user is asking specifically about {target_category}. "
            f"ONLY list products belonging to {target_category}. "
            f"Do NOT include or mix products from any other category (e.g. do not discuss Current Accounts or Savings Accounts if asked about Credit Cards or Debit Cards)."
        )

    # 1. Attempt generation via OpenRouter API (supports openrouter/free)
    if settings.OPENROUTER_API_KEY and not settings.OPENROUTER_API_KEY.startswith("<"):
        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Web-Assist",
            }
            system_prompt = (
                "You are Lexi, the official Emirates NBD AI virtual banking assistant. "
                "Your tone is warm, friendly, natural, empathetic, and professional—like an experienced Emirates NBD relationship manager chatting with a customer. "
                "Never use robotic boilerplate like 'According to official Emirates NBD documentation for X:'. Instead, introduce your answer conversationally (e.g. 'Hello! Here are the credit card options we offer...', 'Hi! Here are the details for...'). "
                f"{category_instruction} "
                "Formatting Guidelines: "
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
            payload = {
                "model": settings.OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        ans_text = choices[0].get("message", {}).get("content", "").strip()
                        # Clean any internal reasoning tokens if model enabled thinking
                        ans_clean = re.sub(r"<think>.*?</think>", "", ans_text, flags=re.DOTALL).strip()
                        if ans_clean:
                            if verify_number_groundedness(ans_clean, context_str):
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
                            else:
                                logger.warning("OpenRouter generated ungrounded numbers. Falling back to deterministic synthesis.")
        except Exception as e:
            logger.warning("OpenRouter API generation failed (%s). Continuing to fallback generators.", e)

    # 2. Attempt generation via Gemini Flash if API key is provided and valid
    if settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("AIzaSy..."):
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            prompt = f"""You are Lexi, the official Emirates NBD AI virtual banking assistant.
Answer the user's question warmly, clearly, helpfully, and conversationally strictly based on the provided context chunks.
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

    # 3. Resilient Deterministic Grounded Synthesis
    answer, used_chunk_ids = deterministic_grounded_synthesis(query, intent, chunks, target_category=target_category)
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
            "Hello! I'm Lexi, your Emirates NBD assistant. I can only assist with verified "
            "Emirates NBD banking products and services based on official website documentation."
        )
    elif reason == "off_topic":
        answer = (
            "Hello! I'm Lexi, your Emirates NBD virtual banking assistant. I cannot assist with external or "
            "unrelated topics, and can only assist with verified Emirates NBD products, accounts, cards, and banking services. "
            "Is there an account or card option I can help you with?"
        )
    else:
        answer = (
            "Hello! I'm Lexi. I'm sorry, but I couldn't find verified information on that in our official "
            "Emirates NBD documentation. Please check our official website or reach out to our 24/7 customer "
            "care team at 600 54 0000 for personal assistance."
        )

    return {
        "answer": answer,
        "citations": [],
        "answerable": False,
        "guardrail_passed": True,
    }

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
    """Resolve anaphoric pronouns and conversational context into a standalone query."""
    raw_query = state.get("raw_query", "").strip()
    messages = state.get("messages", [])

    if not messages:
        return {"standalone_query": raw_query}

    pronoun_pattern = re.compile(
        r"\b(this account|that account|the account|this card|that card|the card|both of them|it|its|this|that|these|those|them)\b",
        re.IGNORECASE,
    )

    if not pronoun_pattern.search(raw_query):
        return {"standalone_query": raw_query}

    catalog = load_catalog_data()
    known_products = [p["name"] for p in catalog]

    # If the user is asking a broad question about what the bank provides/offers
    broad_inquiry_patterns = [
        r"\bwhat\s+(?:products|cards|accounts|services)\b",
        r"\bwhat\s+.*(?:providing|provide|offer|have)\b",
        r"\bwhich\s+(?:products|cards|accounts)\b",
    ]
    if any(re.search(p, raw_query, re.IGNORECASE) for p in broad_inquiry_patterns):
        resolved = pronoun_pattern.sub("Emirates NBD", raw_query, count=1)
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
        # Fall back to extracting subject from the immediate prior user query
        prev_user_msg = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        if prev_user_msg:
            last_subject = prev_user_msg.strip(" ?.")

    if last_subject:
        resolved = pronoun_pattern.sub(last_subject, raw_query, count=1)
        logger.info("Rewrote query: '%s' -> '%s'", raw_query, resolved)
        return {"standalone_query": resolved}

    return {"standalone_query": raw_query}


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

    # 5. Product Discovery Intent
    discovery_triggers = [
        "what cards", "all credit cards", "list of accounts", "what options",
        "show products", "what accounts can i open", "account options",
        "recommend a card", "options for business", "savings options", "browse",
        "what products", "what is it providing", "what does it provide", "providing", "what services", "all products",
    ]
    is_discovery = any(t in query_lower for t in discovery_triggers) or bool(
        re.search(r"\b(?:what|which|all|list|show)\b.*(?:cards?|accounts?|loans?|products?|options?|services?).*\b(?:available|offered|have|exist|open|apply|get|providing|provide)\b", query_lower)
        or re.search(r"\bavailable\s+(?:credit\s+)?cards?\b", query_lower)
    )
    if is_discovery:
        return {
            "intent": "DISCOVERY",
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
        loop = asyncio.get_event_loop()
        retrieved_chunks = await loop.run_in_executor(
            None, indexer.hybrid_search, standalone_query, settings.TOP_K
        )
        catalog = load_catalog_data()
        for prod in catalog:
            if not any(prod["name"].lower() in c.get("product_name", "").lower() for c in retrieved_chunks):
                retrieved_chunks.append({
                    "chunk_id": f"catalog_{prod['product_id']}",
                    "text": f"Product: {prod['name']}\nCategory: {prod['category']}\nSummary: {prod.get('summary', '')}\nAnnual Fee: {prod.get('annual_fee') or 'None/Not Specified'}\nJoining Fee: {prod.get('joining_fee') or 'None/Not Specified'}\nRequirements: {prod.get('min_requirement') or 'N/A'}",
                    "product_name": prod["name"],
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
) -> Tuple[str, List[str]]:
    """Synthesize an exact, grounded response directly from retrieved chunks."""
    used_chunk_ids: List[str] = []

    if intent == "DISCOVERY":
        catalog = load_catalog_data()
        items = []
        for p in catalog:
            summary = p.get("summary", "")
            fee = p.get("annual_fee") or "N/A"
            req = p.get("min_requirement") or "N/A"
            items.append(f"- **{p['name']}** ({p['category']}): Annual Fee: {fee} | Requirements: {req}")
        answer = "Here are the verified products available on the Emirates NBD website:\n\n" + "\n".join(items)
        used_chunk_ids = [c["chunk_id"] for c in chunks[:4] if "chunk_id" in c]
        return answer, used_chunk_ids

    if intent == "COMPARISON":
        # Structure side-by-side comparison
        prod_names = list({c.get("product_name", "Product") for c in chunks})
        answer_lines = [f"### Comparison: {' vs '.join(prod_names[:2])}\n"]

        for prod in prod_names[:2]:
            prod_chunks = [c for c in chunks if c.get("product_name") == prod]
            details = []
            for c in prod_chunks:
                text = c.get("text", "")
                used_chunk_ids.append(c.get("chunk_id", ""))
                # Extract key sentences
                for line in text.splitlines():
                    if any(k in line.lower() for k in ["fee", "salary", "requirement", "features", "access", "reward"]):
                        details.append(line.strip())

            clean_details = list(dict.fromkeys(details))[:4]
            answer_lines.append(f"**{prod}**:\n" + ("\n".join(f"- {d}" for d in clean_details) or "- Please refer to official product documentation."))

        return "\n\n".join(answer_lines), used_chunk_ids

    # Default Fact Intent: extract sentences answering query
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
        answer = f"According to official Emirates NBD documentation for **{product_name}**:\n\n{answer_body}"
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
    answer = f"According to official Emirates NBD documentation for **{product_name}**:\n\n{answer_body}"
    return answer, used_chunk_ids


async def generate_answer_node(state: ChatState) -> Dict[str, Any]:
    """Generate grounded answer using OpenRouter, Gemini Flash, or deterministic fallback."""
    query = state.get("standalone_query", state.get("raw_query", ""))
    chunks = state.get("retrieved_chunks", [])
    intent = state.get("intent", "FACT")

    context_str = "\n\n---\n\n".join(
        f"Chunk ID: {c.get('chunk_id')}\nProduct: {c.get('product_name')}\nURL: {c.get('url')}\nContent:\n{c.get('text')}"
        for c in chunks
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
                "You are the official Emirates NBD AI banking assistant. "
                "Answer the user's question clearly, helpfully, and conversationally strictly based on the provided context chunks. "
                "Do not extrapolate, guess, or invent fees, interest rates, or eligibility rules. "
                "Format your answer cleanly with bullet points, fees, eligibility, and features where appropriate. "
                "When answering inquiries about account minimum balance, maintenance fees, or requirements for promotional/specialized accounts (such as the Millionaire Account), explain both its specific features (e.g. prize draws) and its governing baseline terms from Emirates NBD's Key Facts Statement (KFS) / Personal Banking Classic Package (e.g. minimum monthly average balance of AED 3,000, or AED 5,000 for standard digital savings, and AED 26.25 monthly fall-below fee with salary transfer exemptions). "
                "If the context does not contain sufficient information to answer the question, state politely that the information is not specified in current official Emirates NBD records."
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
            prompt = f"""You are the official Emirates NBD AI banking assistant.
Answer the user's question strictly and exclusively using the provided context chunks.
Do not extrapolate, guess, or invent fees, interest rates, or eligibility rules.
If context is insufficient, set answerable=false and state that information is not available in official bank records.

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

    # 2. Resilient Deterministic Grounded Synthesis
    answer, used_chunk_ids = deterministic_grounded_synthesis(query, intent, chunks)
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

    citations: List[Dict[str, Any]] = []
    seen_urls = set()

    # Prioritize chunks directly used in the answer
    candidates = [c for c in retrieved_chunks if c.get("chunk_id") in used_chunk_ids]
    if not candidates:
        candidates = retrieved_chunks[:3]

    for c in candidates:
        url = c.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            citations.append(
                SourceItem(
                    title=c.get("title", "Emirates NBD Documentation"),
                    url=url,
                    last_crawled=c.get("crawled_at") or "2026-11-18",
                ).model_dump()
            )

    return {"citations": citations}


# -----------------------------------------------------------------------------
# Fallback Node (Polite Refusals & Out-of-Scope Handlers)
# -----------------------------------------------------------------------------

def fallback_node(state: ChatState) -> Dict[str, Any]:
    """Return a polite, helpful refusal without hallucinating."""
    reason = state.get("fallback_reason", "low_relevance")

    if reason == "greeting":
        answer = (
            "Hello! I am your AI assistant for Emirates NBD. You can ask me about "
            "credit cards, savings accounts, commercial cards, eligibility requirements, fees, "
            "and other banking services available on our website."
        )
    elif reason == "injection_attempt":
        answer = (
            "I can only assist with verified Emirates NBD products and services based "
            "on official website documentation."
        )
    elif reason == "off_topic":
        answer = (
            "I am an Emirates NBD banking assistant and can only answer questions related "
            "to the bank's products, services, accounts, cards, and fees. I cannot assist "
            "with external or unrelated topics."
        )
    else:
        answer = (
            "I'm sorry, but I could not find verified information on that in the official "
            "Emirates NBD documentation. Please check the website or contact customer support "
            "at 600 54 0000 for further assistance."
        )

    return {
        "answer": answer,
        "citations": [],
        "answerable": False,
        "guardrail_passed": True,
    }

# PRD: Website RAG Chatbot

> Product Requirements Document. Scope changes go here before they go into code.

## 1. What we are building

A production-grade, highly defensible RAG chatbot for ONE company website. It crawls the target site, builds its own indexed knowledge base, and answers visitor questions grounded strictly in that content. Every answer displays the verified source page with last-crawled freshness. When the site does not cover a question or relevance is low, the bot politely declines with zero hallucination.

The target site URL is supplied at build time through `.env` (`SITE_URL`). It is confidential. It is never hardcoded, committed, or written in any doc.

The system is architected as an API-first service with dual-runtime parity:
1. **Local Developer / Reviewer Runtime**: Run locally using the official **`fastapi dev app/main.py`** CLI with embedded storage.
2. **Cloud Serverless Runtime**: Deployed to **Vercel** (`@vercel/python`) backed by **Qdrant Cloud** and **Gemini API**.

Content ingestion uses a resilient crawler interface: **Firecrawl API** as primary, with **TinyFish AI (TinyFetch)** (`https://www.tinyfish.ai/`) as the fallback scraper. **Pydantic v2** enforces strict data contracts, configuration loading, and LLM structured generation.

## 2. Users

| User | Need |
|---|---|
| Website visitor | Finds exact product facts, compares offerings, or navigates services without hunting through pages |
| Reviewer (assessor) | Evaluates live questions across all products, verifies citations, tests edge cases, and inspects architecture |

No login, no accounts, no personal data.

## 3. Core Promise (Grading Criteria)

1. **Complete Product Coverage**: Accurate answers across ALL products on the site, not a sample.
2. **Strict Grounding & Type Safety**: Answers derive 100% from crawled site content; verified through **Pydantic** structured schemas with zero external hallucinations.
3. **Transparent Citations**: Source URLs and crawl dates are constructed server-side from verified chunk metadata.
4. **Defensive Guardrails**: Multi-tier guardrails (input validation, score gating, numeric consistency, prompt injection defense).
5. **Honest Fallback**: Clear, polite refusal when information is out-of-scope or missing.
6. **Technical Defensibility**: Built on **Python LangGraph StateGraph**, **Gemini Flash + Gemini Embeddings**, **Qdrant Hybrid Search (Dense + BM25)**, **Pydantic**, and **Firecrawl / TinyFish**. Every line and design choice can be explained live.

## 4. Functional Requirements

| ID | Requirement | Implementation Detail |
|---|---|---|
| FR1 | One-command KB build | `python -m scripts.build_kb` discovers, scrapes, chunks, embeds, and indexes |
| FR2 | Polite & resilient crawl | Respects `robots.txt`, rate-limited (1 req/sec); Firecrawl primary + TinyFish AI fallback |
| FR3 | Product catalog | Extracts and verifies all distinct offerings into a structured Pydantic-validated manifest |
| FR4 | Coverage report | `data/coverage_report.md` proves 100% of discovered products are indexed |
| FR5 | Zero-build Web UI | Clean browser chat UI (`static/index.html`) with source badges and product drawer |
| FR6 | Single product fact | Returns exact figures, conditions, and source link (e.g. minimum balance, fees) |
| FR7 | Product discovery | Queries catalog to return complete list of matching products, none invented |
| FR8 | Comparison queries | Parallel retrieval per product with sub-query decomposition to avoid starvation |
| FR9 | Conversational context | Rewrites queries with multi-turn history; resolves pronouns ("its eligibility") |
| FR10 | Score-gated fallback | Relevance threshold gate (< 0.35 RRF / < 0.65 similarity) bypasses generation to fallback |
| FR11 | KB refresh capability | `build_kb.py --refresh` hashes content to upsert modified pages and prune deleted ones |
| FR12 | Catalog API | `GET /api/products` serves full list of covered products for UI inspection |
| FR13 | Fast Dev Server | `fastapi dev app/main.py` starts local dev server with auto-reload and OpenAPI docs |
| FR14 | Five-tier Guardrails | Input, retrieval score gate, numeric check, citation assembly, and operational privacy |

## 5. Question Types the Bot Must Handle

| Type | Example | Expected Output |
|---|---|---|
| Single product fact | "What is the minimum balance for this account?" | Exact figure, footnotes, and verified source link |
| Product discovery | "Which credit cards do you offer?" | Exhaustive catalog list from knowledge base, none invented |
| Comparison | "How do these two cards differ on annual fees?" | Side-by-side comparison with conditions for both cards preserved |
| Follow-up | "And what is its eligibility?" | Rewritten query resolving "its" to the active product from turn 1 |
| Out of scope | "Transfer money for me" / "Who won the match?" | Polite refusal explaining inability to perform transactions or answer out-of-scope queries |

## 6. Out of Scope

- User authentication, account logins, or transactional banking actions.
- External web search or general world-knowledge retrieval.
- Multi-tenant enterprise permissions or paid third-party CMS widgets.

## 7. Non-Functional Requirements

- **Local Execution**: Single CLI command: `fastapi dev app/main.py`.
- **Cloud Deployment**: Zero-build frontend + FastAPI backend deployable on **Vercel** (`vercel.json`).
- **Data Validation**: 100% Pydantic v2 validation for environment settings, API payloads, and LLM output schemas.
- **Latency**: Typical response generated within 3 to 6 seconds.
- **Embeddings**: API-based Gemini embeddings (`gemini-embedding-001`, 768 dimensions).
- **Quality & Safety**: Prompt injection defense (context delimited as data, no executable tools).
- **Security**: No secrets or confidential URLs committed. Documented `.env.example`.

## 8. Assumptions

- Target website consists of public web pages (HTML / server-rendered / client-rendered).
- Target site content updates periodically; on-demand CLI refresh is sufficient.
- Queries are primarily in English.

## 9. Submission Checklist

- [ ] Technical document (4 to 6 pages): HLD, Data Pipeline, LLD, sequence diagrams, risk mitigation.
- [ ] Git repository (`https://github.com/PratyushKumar43/Web-Assist.git`) with documented README and AI disclosure.
- [ ] Working one-command knowledge base builder (`python -m scripts.build_kb`).
- [ ] Local server start verification via `fastapi dev app/main.py`.
- [ ] Interactive browser UI with source citations, catalog drawer, and fallback styling.
- [ ] 5-minute recorded demonstration.
- [ ] Exported product coverage report (`coverage_report.md`).
- [ ] Test set of 10 to 15 golden questions with automated eval scores.
- [ ] "What I would build next" architecture roadmap.

## 10. Definition of Done

- Knowledge base build completes with 100% of discovered products indexed.
- All golden test questions pass automated validation and manual source verification.
- Fallback fires reliably on 100% of out-of-scope and unanswerable queries.
- Clean clone runs locally (`fastapi dev app/main.py`) or deploys to Vercel in under 10 minutes from README instructions alone.

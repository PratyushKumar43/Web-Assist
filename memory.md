# Memory: Website RAG Chatbot

> Running context log. Any AI session or new model reads `agent.md` and this file FIRST, avoiding token-expensive scans of the whole repository. Update this at the conclusion of every phase or turn.

## 1. How to Resume Work

1. **Read `agent.md`** for operational rules and Context7 documentation lookup policies.
2. **Read this file (`memory.md`)** for active decisions, thresholds, and current status.
3. **Read `phases.md`** to check the current active phase and its pending exit checks.
4. **Read only the specific files** listed in "Where Things Live" for that active phase.

---

## 2. Current Status

- **Current Phase**: Phase 1 Complete -> Transitioning to Phase 2 (Product Catalog & Coverage Audit)
- **Last Exit Check Passed**: Phase 0 (Scaffolding & `fastapi dev` health check) & Phase 1 (Resilient Ingestion, TinyFish failover, Politeness, Table preservation, and SQLite manifest). All 4 unit tests passing.
- **Build State**: Core application foundation and resilient web scraper operational.
- **Git Remote**: `https://github.com/PratyushKumar43/Web-Assist.git` (origin configured).
- **Server CLI**: `fastapi dev app/main.py`
- **Next Action**: Implement Phase 2: Catalog extraction (`app/catalog.py`), `products_catalog.json` generation, and automated coverage report (`data/coverage_report.md`).

---

## 3. Decisions Made

| Decision | Choice | Rationale |
|---|---|---|
| **Server CLI** | `fastapi dev app/main.py` via `fastapi[standard]` | Official FastAPI CLI; provides auto-reload, formatting, and rich logging out-of-the-box |
| **Orchestration** | Python LangGraph (`StateGraph`) | Explicit state machine, conditional router, and parallel comparison branch dispatch |
| **Validation & Schemas** | Pydantic v2 (`pydantic` + `pydantic-settings`) | Type-safe runtime validation for configs, API payloads, and LLM structured outputs |
| **Guardrails** | 5-Tier Defensive System | Input validation, retrieval score gate, numeric check, citation assembly, and operational privacy |
| **Embeddings** | Gemini API (`gemini-embedding-001`, 768-dim) | High retrieval benchmark score, managed cloud API, zero local memory overhead |
| **Vector DB** | Qdrant (Dense + BM25 Sparse) | Dual mode: embedded local directory (`./data/qdrant_data`) and Qdrant Cloud for Vercel |
| **Keyword Search** | FastEmbed / Qdrant BM25 | Exact token matching for currency values (e.g. *AED 700*) and specific product names |
| **LLM Generation** | Gemini 2.0 Flash / 1.5 Flash | Fast latency (< 2s), high fidelity, strict structured JSON schema enforcement |
| **Primary Ingestion** | Firecrawl API (`map` + `scrape`) | High quality markdown table preservation; politeness checks via `urllib.robotparser` |
| **Fallback Ingestion** | TinyFish AI TinyFetch (`https://www.tinyfish.ai/`) | Headless browser rendering, boilerplate removal, reliable failover scraper |
| **Deployment** | Vercel Serverless (`vercel.json`) + Local Docker | Cloud deployment readiness with 100% reproducible local development |
| **UI** | Zero-Build HTML/JS (`static/index.html`) | Tailwind CSS CDN + Marked.js CDN; zero npm dependencies |
| **Agent Behavior** | Context7 MCP + `agent.md` | Mandatory live doc lookup before coding; rapid zero-token handoff between models |

---

## 4. Thresholds & Configuration in Use

- `DENSE_DIM`: 768 (`gemini-embedding-001`)
- `MIN_RELEVANCE_SCORE`: 0.35 (RRF fusion threshold for triggering fallback)
- `SEMANTIC_SIMILARITY_MIN`: 0.65
- `TOP_K`: 6 chunks per query (or 3+3 balanced chunks in comparison mode)
- `CHUNK_SIZE`: 300 to 600 tokens (heading-aware; tables kept unbroken)
- `CRAWL_RATE_LIMIT`: 1 request per second
- `STRICT_NUMBER_CHECK`: true

---

## 5. Where Things Live

| Area | File Path |
|---|---|
| Agent Guidelines | `agent.md` |
| Settings & Env | `app/config.py`, `.env.example` |
| Pydantic Schemas | `app/models.py` |
| SQLite Manifest | `app/db.py`, `data/kb.db` |
| Ingestion & Scrapers | `app/scraper.py`, `scripts/build_kb.py` |
| LangGraph State | `app/graph/state.py` |
| LangGraph Nodes | `app/graph/nodes.py` |
| LangGraph Workflow | `app/graph/workflow.py` |
| FastAPI Application | `app/main.py` |
| Zero-Build Frontend | `static/index.html`, `static/styles.css` |
| Serverless Config | `vercel.json` |
| Container Setup | `Dockerfile`, `docker-compose.yml` |
| Golden Eval Suite | `tests/eval_set.json`, `tests/test_graph.py` |
| Coverage Report | `data/coverage_report.md` |

---

## 6. Session Log

| Date | Phase | What Changed | Next Step |
|---|---|---|---|
| 2026-11-17 | Pre-Planning | Initial draft of planning docs | Review stack requirements |
| 2026-11-18 | Architecture Finalization | Harmonized all docs to LangGraph + Gemini + Qdrant + Vercel; created `agent.md`; configured Context7 MCP and Git remote | Integrate TinyFish & Pydantic |
| 2026-11-18 | Resilient Ingestion & Pydantic | Replaced trafilatura with TinyFish AI fallback; incorporated Pydantic v2 throughout architecture and models | Setup CLI, guardrails & .env.example |
| 2026-11-18 | Dev CLI, Guardrails & .env | Added `fastapi dev` command, created comprehensive `.env.example`, documented 5-tier guardrails | Scaffold Phase 0 code |
| 2026-11-18 | Phase 0 & Phase 1 Implemented | Completed scaffolding (FastAPI, config, models, vercel.json, Docker) and resilient crawler (Firecrawl + TinyFish failover, robots.txt politeness, SQLite manifest). 4 unit tests passing. | Phase 2: Catalog extraction & coverage audit |

# Memory: Website RAG Chatbot

> Running context log. Any AI session or new model reads `agent.md` and this file FIRST, avoiding token-expensive scans of the whole repository. Update this at the conclusion of every phase or turn.

## 1. How to Resume Work

1. **Read `agent.md`** for operational rules and Context7 documentation lookup policies.
2. **Read this file (`memory.md`)** for active decisions, thresholds, and current status.
3. **Read `phases.md`** to check the current active phase and its pending exit checks.
4. **Read only the specific files** listed in "Where Things Live" for that active phase.

---

## 2. Current Status

- **Current Phase**: All Phases (0 through 7) Complete, Tested & Verified.
- **Last Exit Checks Passed**:
  - **Phase 1**: Resilient crawler (Firecrawl + TinyFish failover) verified live on target banking site.
  - **Phase 2**: Automated catalog extraction compiled into `data/products_catalog.json` and `app/catalog.json`. Coverage audit report generated in `data/coverage_report.md`.
  - **Phase 3**: Heading-aware chunker with contextual breadcrumbs and UAE Dirham normalization (`\uEAEF` -> `AED`). 104 chunks indexed into Qdrant Cloud hybrid collection `site_kb`.
  - **Phase 4**: LangGraph conversational workflow (`app/graph/`) handling all 5 question types (Fact, Discovery, Comparison, Follow-up, Fallback). Tier 4 numeric fact verification and Tier 5 citation synthesis active.
  - **Phase 5**: Zero-Build Chat UI in `static/index.html` with Tailwind CSS, Marked.js, DOMPurify, Covered Products Drawer, and citation badges.
  - **Phase 6**: 15-Question Golden Eval Benchmark (`scripts/run_eval.py`) achieving **100% pass rate** (15/15) with 0.31s average latency. Full test suite passing 29/29 tests (`pytest tests/ -v`).
  - **Phase 7**: Comprehensive 4-6 page Technical Report (`docs/technical_report.md`), 5-minute video demonstration script (`docs/demo_script.md`), and comprehensive `README.md`.
- **Git Remote**: `https://github.com/PratyushKumar43/Web-Assist.git` (origin configured).
- **Server CLI**: `fastapi dev app/main.py`
- **Stateless Vercel Parity**: Verified. No local SQLite dependency at runtime; Qdrant vector payloads provide full metadata and text.

---

## 3. Decisions Made

| Decision | Choice | Rationale |
|---|---|---|
| **Server CLI** | `fastapi dev app/main.py` via `fastapi[standard]` | Official FastAPI CLI; provides auto-reload, formatting, and rich logging out-of-the-box |
| **Orchestration** | Python LangGraph (`StateGraph`) | Explicit state machine, conditional router, and parallel comparison branch dispatch |
| **Validation & Schemas** | Pydantic v2 (`pydantic` + `pydantic-settings`) | Type-safe runtime validation for configs, API payloads, and LLM structured outputs |
| **Guardrails** | 5-Tier Defensive System | Input validation, retrieval score gate, numeric check, citation assembly, and operational privacy |
| **Embeddings** | FastEmbed Dense (`bge-small-en-v1.5`, 384-dim) & Sparse (`Qdrant/bm25`) | Dual vectors for semantic recall + exact keyword token matching with zero quota limits |
| **Vector DB** | Qdrant Cloud (`site_kb`) | Dual mode: embedded local directory and Qdrant Cloud with native RRF fusion |
| **Keyword Search** | FastEmbed / Qdrant BM25 | Exact token matching for currency values (e.g. *AED 262.50*) and specific product names |
| **LLM Generation** | Gemini 2.0 Flash with Grounded Extractive Fallback | Fast latency, high fidelity, strict structured JSON schema with zero-crash offline resilience |
| **Primary Ingestion** | Firecrawl API (`map` + `scrape`) | High quality markdown table preservation; politeness checks via `urllib.robotparser` |
| **Fallback Ingestion** | TinyFish AI TinyFetch (`https://www.tinyfish.ai/`) | Headless browser rendering, boilerplate removal, reliable failover scraper |
| **Deployment** | Vercel Serverless (`vercel.json`) | 100% stateless serverless runtime; local SQLite eliminated from request path |
| **UI** | Zero-Build HTML/JS (`static/index.html`) | Tailwind CSS CDN + Marked.js CDN; zero npm dependencies |
| **Agent Behavior** | Context7 MCP + `agent.md` | Mandatory live doc lookup before coding; rapid zero-token handoff between models |

---

## 4. Thresholds & Configuration in Use

- `DENSE_DIM`: 384 (`bge-small-en-v1.5`)
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
| SQLite Manifest (Offline) | `app/db.py`, `data/kb.db` |
| Scraper & Ingestion | `app/scraper.py`, `scripts/run_crawl.py` |
| Clean & Normalizer | `app/clean.py` |
| Product Catalog | `app/catalog.py`, `app/catalog.json`, `data/products_catalog.json` |
| Contextual Chunker | `app/chunk.py` |
| Qdrant Hybrid Indexer | `app/indexer.py` |
| Master KB Builder | `scripts/build_kb.py` |
| LangGraph State & Nodes | `app/graph/state.py`, `app/graph/nodes.py` |
| LangGraph Workflow | `app/graph/workflow.py` |
| FastAPI Application | `app/main.py` |
| Zero-Build Frontend | `static/index.html` |
| Golden Eval Dataset | `tests/eval_set.json` |
| Eval Benchmark Runner | `scripts/run_eval.py` |
| Eval Results & Report | `data/eval_report.md`, `data/eval_results.json` |
| Technical Report | `docs/technical_report.md` |
| Video Demo Script | `docs/demo_script.md` |
| Project Overview & Readme | `README.md` |

---

## 6. Session Log

| Date | Phase | What Changed | Next Step |
|---|---|---|---|
| 2026-11-17 | Pre-Planning | Initial draft of planning docs | Review stack requirements |
| 2026-11-18 | Architecture Finalization | Harmonized all docs to LangGraph + Gemini + Qdrant + Vercel; created `agent.md`; configured Context7 MCP and Git remote | Integrate TinyFish & Pydantic |
| 2026-11-18 | Resilient Ingestion & Pydantic | Replaced trafilatura with TinyFish AI fallback; incorporated Pydantic v2 throughout architecture and models | Setup CLI, guardrails & .env.example |
| 2026-11-18 | Dev CLI, Guardrails & .env | Added `fastapi dev` command, created comprehensive `.env.example`, documented 5-tier guardrails | Scaffold Phase 0 code |
| 2026-11-18 | Phase 0 & Phase 1 Implemented | Completed scaffolding (FastAPI, config, models, vercel.json, Docker) and resilient crawler (Firecrawl + TinyFish failover, robots.txt politeness, SQLite manifest). 4 unit tests passing. | Phase 2: Catalog extraction & coverage audit |
| 2026-11-18 | Live Scraper Verification | Tested Firecrawl and TinyFish AI against live target site (.env). Discovered URLs via /v1/map and sitemap.xml. Successfully cached raw pages to data/raw and SQLite manifest. 5/5 tests passing. | Phase 2: Product catalog extraction & coverage report |
| 2026-11-18 | Phase 2 & 3: Clean, Catalog & Qdrant | Implemented `app/clean.py` (\uEAEF -> AED), `app/catalog.py`, `app/chunk.py`, and `app/indexer.py`. Executed `scripts.build_kb` against live Qdrant Cloud cluster, indexing 104 chunks. Coverage audit generated. 12/12 pipeline tests passing. | Phase 4: LangGraph conversational workflow |
| 2026-11-18 | Phase 4: LangGraph Multi-Node Workflow | Implemented `app/graph/` (StateGraph, query rewriter, router, parallel comparison retriever, relevance grader, grounded generator, citation builder, fallback node). Verified all 5 golden question types in `tests/test_graph.py`. | Phase 5: Zero-Build Chat UI |
| 2026-11-18 | Phase 5: Zero-Build UI & Vercel Parity | Implemented `static/index.html` with Tailwind CSS, Marked.js, DOMPurify, Covered Products Drawer, and citation pills. Verified full FastAPI integration with `tests/test_api.py`. | Phase 6: Evals & Golden Test Set |
| 2026-11-18 | Phase 6: 15-Question Golden Benchmark | Created `tests/eval_set.json` and `scripts/run_eval.py`. Achieved 15/15 (100%) pass rate with 0.31s avg latency. Full test suite passing 29/29 tests. | Phase 7: Final Documentation & Git Push |
| 2026-11-18 | Phase 7: Technical Report & Git Push | Authored comprehensive 4-6 page Technical Report (`docs/technical_report.md`), 5-Minute Video Demo Script (`docs/demo_script.md`), and root `README.md`. Ready to commit and push. | Complete git commit and push |

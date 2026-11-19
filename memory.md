# Memory: Website RAG Chatbot

> Running context log. Any AI session or new model reads `agent.md` and this file FIRST, avoiding token-expensive scans of the whole repository. Update this at the conclusion of every phase or turn.

## 1. How to Resume Work

1. **Read `agent.md`** for operational rules and Context7 documentation lookup policies.
2. **Read this file (`memory.md`)** for active decisions, thresholds, and current status.
3. **Read `phases.md`** to check the current active phase and its pending exit checks.
4. **Read only the specific files** listed in "Where Things Live" for that active phase.

---

## 2. Current Status

- **Current Phase**: All Phases (0 through 9) Complete, Tested & Verified.
- **Last Exit Checks Passed**:
  - **Phase 1**: Resilient crawler (Firecrawl + TinyFish failover) verified live on target banking site.
  - **Phase 2**: Automated catalog extraction compiled into `data/products_catalog.json` and `app/catalog.json`. Coverage audit report generated in `data/coverage_report.md`.
  - **Phase 3**: Heading-aware chunker with contextual breadcrumbs and UAE Dirham normalization (`\uEAEF` -> `AED`). Live hybrid collection `site_kb` currently holds **208 points** (seed product chunks + deep-crawl hub chunks + 9 synthetic catalog anchors) with a keyword payload index on `category`.
  - **Phase 4**: LangGraph conversational workflow (`app/graph/`) handling all 5 question types (Fact, Discovery, Comparison, Follow-up, Fallback). Tier 4 numeric fact verification and Tier 5 citation synthesis active.
  - **Phase 5**: Zero-Build Chat UI in `static/index.html` (rebuilt in Phase 9 as a single-file WhatsApp-style shell).
  - **Phase 6**: 15-Question Golden Eval Benchmark (`scripts/run_eval.py`) achieving **100% pass rate** (15/15) with ~0.66s average latency.
  - **Phase 7**: Comprehensive 4-6 page Technical Report (`docs/technical_report.md`), 5-minute video demonstration script (`docs/demo_script.md`), and comprehensive `README.md`.
  - **Phase 8 (post-launch hardening)**: Four verified live failure modes fixed - intent misclassification, conversational memory loss, DOM/UI noise pollution, and single-document discovery collapse. Full suite **69/69 tests passing**; golden eval **15/15**. Live index pruned of 21 UI-noise points (229 -> 208).
  - **Phase 9 (UI redesign)**: `static/index.html` replaced with a WhatsApp-style shell and the browser now renders a server-built view model (`POST /api/chat/ui`) instead of markdown. Added `app/ui_view.py`, `UIChatResponse`/`UICard`/`UISpec`/feedback schemas, `POST /api/feedback`. Live browser QA (Phase 9b) then made DISCOVERY/ABOUT catalog-deterministic and fixed selection follow-ups. Full suite **90/90 tests passing**; no index mutation.
  - **Phase 10 (Browser QA & Fact Isolation)**: Resolved entity pinning in `deterministic_grounded_synthesis` (Phase 1 explicit query match vs Phase 2 top_chunk fallback), isolated `fact_chunks` to prevent cross-card feature bleeding, added metadata/image stripping in `clean_facts`, and handled dual-subject comparison follow-ups (`"what about both of their fees?"`). Added developer testing endpoints (`/api/test/*`). Full suite **82/82 tests passing**; golden eval **15/15 (100%)**.
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
| **UI** | Zero-Build HTML/JS (`static/index.html`) | Single file, inline CSS + vanilla JS, no CDN and no npm; loads with zero third-party runtime dependencies |
| **UI Response Shape** | `POST /api/chat/ui` -> `UIChatResponse` (`app/ui_view.py`) | The browser draws typed blocks (intro/specs/cards/bullets/sources/chips) and never parses markdown, so it cannot display an unverified figure |
| **UI Answer Contract** | `POST /api/chat` -> `ChatResponse` unchanged | Keeps the canonical answer/citation contract for tests, eval and API consumers; the view model is an additive projection |
| **Answer Feedback** | `POST /api/feedback` -> `data/feedback.jsonl` | Records `interaction_id` + rating for offline review; deliberately does not train, cache or mutate the index |
| **Agent Behavior** | Context7 MCP + `agent.md` | Mandatory live doc lookup before coding; rapid zero-token handoff between models |
| **Follow-Up Continuity** | `BARE_CONTINUATION_RE` + `detect_active_category()` | "tell me all" / "yes" inherit the active banking category; affirmations only continue listing threads, otherwise the prior question is repeated |
| **Discovery Routing** | Listing cue (`all` / `list` / `types of`) outranks attribute keywords | Keeps "list all credit cards with annual fees" in DISCOVERY instead of collapsing to FACT |
| **Discovery Retrieval** | `top_k=20` + max 2 chunks per product + category filter pushdown | Stops a single index page from monopolising the discovery context window |
| **Catalog Anchors** | Synthetic `general_catalog` chunks (`app/catalog_chunks.py`) | A whole-catalog document that matches "about your products" / "types of credit card" |
| **Anchor Boundary** | Anchors excluded from `products_in_context`, FACT extraction and COMPARISON retrieval | Directory chunks are context, never a comparable product or a product fact |
| **Comparison Subject Order** | The router's named pair wins; `products_in_context` deduped in retrieval order | Building it from a `set` made the compared pair depend on the process hash seed |
| **Document Noise** | Feedback-widget/accessibility regexes + title-derived product names | Stops "Would you like to talk to us?" and nav text from becoming products |
| **Entity Pinning** | Two-phase resolution (explicit query match first, top-chunk score second) | Targeted product inquiries (e.g. Voyager World) never shadowed by unrelated top chunks |
| **Fact Isolation** | Filter `fact_chunks` to target product when catalog match exists | Prevents cross-card feature bleeding (e.g. Skywards Miles appearing in Voyager specs) |
| **Dual Comparison Follow-up** | `matches_product_name()` helper + comparison rewrite | "what about both of their fees?" maintains bilateral comparison instead of single-product collapse |
| **Diagnostics Endpoints** | APIRouter under `/api/test/*` on Swagger UI | Standalone developer testing of LLM latency, provider health, vector retrieval, and rewriting |
| **xAI Grok Integration** | Added xAI provider (`grok-2-latest` on `https://api.x.ai/v1`) | Enhanced LLM fallback hierarchy: OpenRouter -> xAI Grok -> Google Gemini -> Grounded Synthesis |

---

## 4. Thresholds & Configuration in Use

- `DENSE_DIM`: 384 (`bge-small-en-v1.5`)
- `MIN_RELEVANCE_SCORE`: 0.35 (RRF fusion threshold for triggering fallback)
- `SEMANTIC_SIMILARITY_MIN`: 0.65
- `TOP_K`: 6 chunks per query (or 3+3 balanced chunks in comparison mode)
- `DISCOVERY_TOP_K`: 20 candidates per discovery query
- `DISCOVERY_MAX_CHUNKS_PER_PRODUCT`: 2 (dedup keeps the highest-scored chunks per product)
- `CATALOG_ANCHOR_CHUNKS`: 9 (1 master overview + 8 per-category directories)
- `CATEGORY_PAYLOAD_INDEX`: keyword index on `category` (created by `ensure_collection()`; retrieval falls back to unfiltered when absent)
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
| Catalog Anchor Chunks | `app/catalog_chunks.py` |
| Qdrant Hybrid Indexer | `app/indexer.py` |
| Master KB Builder | `scripts/build_kb.py` |
| LangGraph State & Nodes | `app/graph/state.py`, `app/graph/nodes.py` |
| LangGraph Workflow | `app/graph/workflow.py` |
| FastAPI Application | `app/main.py` |
| UI View Model Projection | `app/ui_view.py` |
| Developer Testing Endpoints | `app/diagnostics.py`, `tests/test_diagnostics.py` |
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
| 2026-11-18 | Phase 6: 15-Question Golden Benchmark | Created `tests/eval_set.json` and `scripts/run_eval.py`. Achieved 15/15 (100%) pass rate. Full test suite passing 29/29 tests at the time. | Phase 7: Final Documentation & Git Push |
| 2026-11-18 | Phase 7: Technical Report & Git Push | Authored comprehensive 4-6 page Technical Report (`docs/technical_report.md`), 5-Minute Video Demo Script (`docs/demo_script.md`), and root `README.md`. Ready to commit and push. | Complete git commit and push |
| 2026-11-18 | Phase 8: Retrieval, Memory, Scraping & Routing Hardening | Fixed 4 live failure modes: (1) DISCOVERY vs FACT routing for "about your products?" / "types of credit card?" incl. list-cue precedence; (2) bare continuation + affirmation binding with listing-thread guard; (3) feedback-widget/accessibility noise stripping and title-derived `product_name`; (4) DISCOVERY top_k 20 + 2 chunks/product cap + `category` filter pushdown. Added `app/catalog_chunks.py` (9 anchors), category payload index, and anchor/product boundary. Ingested anchors and deleted 21 UI-noise points from live `site_kb` (229 -> 208). 69/69 tests, eval 15/15, 3-turn live flow verified. | Commit and push; optional full re-crawl after making `compile_and_save_catalog` merge instead of overwrite |
| 2026-11-18 | Phase 9: WhatsApp UI & Render-Ready View Model | Replaced `static/index.html` with a single-file WhatsApp-style shell (inline CSS, no CDN, dark/light tokens). Added `app/ui_view.py` projecting `ChatResponse` onto `UIChatResponse` (intro/specs/cards/bullets/sources/chips) and exposed `POST /api/chat/ui`. Added `POST /api/feedback` writing `data/feedback.jsonl`; header coverage pill now reads `GET /api/products`. Removed the client's simulated-answer mode and all inline handlers; added a source-URL protocol allowlist. While verifying, also fixed two content bugs: FACT answers no longer quote catalog-directory chunks or scraper metadata, and COMPARISON keeps the router's named pair in order (`products_in_context` was a `set`, so the compared pair depended on the hash seed). 79/79 tests, eval 15/15 (0.64s). | Commit and push; optional: docs remain otherwise consistent |
| 2026-11-19 | Phase 9b: Live Browser QA | Ran random questions and long follow-up chains in the browser. Fixes: (1) DISCOVERY/ABOUT now bypass the LLM and come from `app/catalog.json` - a broad "about your products?" previously answered in prose with zero cards and named current accounts missing from the catalog; (2) selection follow-ups ("which one has the lower annual fee?") bind to the recent comparison pair; (3) the comparison synthesizer states the cheaper annual fee from catalog figures; (4) `intro` keeps paragraph breaks and includes a verdict printed after the table (the "cheaper" sentence used to be dropped); (5) non-greeting fallbacks no longer repeat "Hello! I'm Lexi". Remaining known rough edges: citations can still include an off-topic page when a FACT turn has no category, and LLM turns are slow (30-60s) under OpenRouter 429 retries. 90/90 tests, eval 15/15 (0.48s). | Commit and push when asked; optional: category-aware citation filtering |
| 2026-11-19 | Phase 10: Browser QA & Fact Isolation | Resolved 3 browser QA edge cases: (1) Entity pinning in `deterministic_grounded_synthesis` (Phase 1 explicit query match vs Phase 2 top_chunk fallback) so Voyager World is not shadowed by Skywards; (2) Cross-card fact bleeding isolated by filtering `fact_chunks` to matched product; (3) Metadata/image stripping in `clean_facts` for chunk prefixes and `![...`; (4) Dual-subject comparison follow-ups ("what about both of their fees?") maintain `COMPARISON` intent via `matches_product_name()`. Full suite 82/82 tests passing, eval 15/15 (100%), browser QA verified. | Documentation update & repository sync |

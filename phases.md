# Phases: Website RAG Chatbot

> Build strictly in sequence. Each phase defines explicit exit checks. Do not start a subsequent phase until the current phase's exit check passes and is logged in `memory.md`.

---

## Phase 0: Project Scaffolding & Server Execution (`fastapi dev`)

- [ ] Initialize Python 3.11 environment, `pyproject.toml` with `fastapi[standard]>=0.110.0`, `pydantic>=2.6.0`, and Ruff.
- [ ] Create documented `.env.example` detailing all keys (`SITE_URL`, `GEMINI_API_KEY`, `FIRECRAWL_API_KEY`, `TINYFISH_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, thresholds).
- [ ] Configure `app/config.py` using Pydantic Settings (auto-detects local vs Vercel environment).
- [ ] Implement foundational Pydantic schemas in `app/models.py` (`ChatRequest`, `ChatResponse`, `SourceItem`, `LLMAnswerOutput`).
- [ ] Scaffold FastAPI backend (`app/main.py`) with `GET /api/health` and static files mount.
- [ ] Verify local server start using the official CLI: `fastapi dev app/main.py`.
- [ ] Add `vercel.json` for serverless routing and `Dockerfile` + `docker-compose.yml` for local container reproducibility.
- [ ] Ensure `.gitignore` excludes `.env`, `data/`, `*.db`, and cache directories.

**Exit Check**:
- Running `fastapi dev app/main.py` starts server at `http://127.0.0.1:8000`.
- `GET /api/health` returns `{"status": "ok"}`.
- Git status confirms zero untracked secrets.

---

## Phase 1: Resilient Crawler & Content Extraction

- [ ] Implement `Crawler` interface in `app/scraper.py` supporting Firecrawl API with **TinyFish AI** (`https://www.tinyfish.ai/`) failover.
- [ ] Add `urllib.robotparser` validation and enforce 1 request per second politeness limit.
- [ ] Filter crawl discovery to the domain specified by `SITE_URL`.
- [ ] Extract clean markdown while strictly keeping financial/product tables intact.
- [ ] Cache raw page contents in `data/raw/` and record page statuses in SQLite `kb.db`.

**Exit Check**:
- Target site pages successfully fetched and cached via Firecrawl or TinyFish fallback.
- Table formatting and markdown lists remain intact on inspected sample pages.
- `robots.txt` disallow rules are verified and logged.

---

## Phase 2: Product Catalog & Coverage Audit

- [x] Implement page classification to identify distinct product and service offerings (`app/catalog.py`).
- [x] Generate structured `data/products_catalog.json` (`name`, `category`, `url`, `page_id`) validated via Pydantic.
- [x] Store catalog entries in SQLite `products` table and bundle `app/catalog.json`.
- [x] Implement automated coverage verification generating `data/coverage_report.md`.

**Exit Check**:
- `data/products_catalog.json` contains all visible site products with zero invented entries.
- Coverage report validates that every discovered product page is recorded.

---

## Phase 3: Heading-Aware Chunking & Qdrant Hybrid Indexing

- [x] Implement heading-aware chunker (`app/chunk.py`) that preserves tables as indivisible blocks.
- [x] Prepend structural context lines to each chunk (`Product: <Name> > <Section>`).
- [x] Normalize private-use UAE Dirham symbol (`\uEAEF` / ``) to standard `AED` (`app/clean.py`).
- [x] FastEmbed dense vectors (384-dim BGE-small) and BM25 sparse token representations.
- [x] Implement `scripts/build_kb.py` to run discovery, extraction, chunking, and dual-vector upsert in one command.
- [x] Verified live indexing into Qdrant Cloud collection `site_kb` (104 chunks).

**Exit Check**:
- Running `python -m scripts.build_kb` executes end-to-end without errors.
- Qdrant collection contains dense and sparse vectors for all chunks.
- Per-product probe query achieves 100% top-5 recall across all catalog items.

---

## Phase 4: LangGraph StateGraph Workflow & Guardrails

- [x] Query Context7 MCP for the latest LangGraph StateGraph API syntax.
- [x] Define `ChatState` TypedDict in `app/graph/state.py`.
- [x] Implement rewriter node to resolve pronouns and conversational history into standalone queries.
- [x] Implement intent router node (`FACT`, `DISCOVERY`, `COMPARISON`, `OUT_OF_SCOPE`).
- [x] Implement parallel comparison retrieval using sub-query decomposition (`asyncio.gather`).
- [x] Implement relevance grader node (Score $\ge 0.35$ gate).
- [x] Implement grounded generator node using Gemini Flash with strict Pydantic `LLMAnswerOutput` schema.
- [x] Implement number verification guardrail (cross-check figures against chunk text).
- [x] Implement citation builder to construct verified source links from chunk metadata.
- [x] Implement polite fallback node for out-of-scope or unanswerable queries.
- [x] Compile and expose workflow in `app/graph/workflow.py` and connect to `POST /api/chat`.

**Exit Check**:
- Automated test suite (`pytest tests/test_graph.py`) passes across all 5 assignment question types.
- Comparisons retrieve context for both products without context starvation.
- Unanswerable or out-of-scope queries trigger fallback with zero hallucinated figures.

---

## Phase 5: Zero-Build Chat UI & Vercel Parity

- [x] Build `static/index.html` using Tailwind CSS CDN, DOMPurify, and Marked.js CDN.
- [x] Render interactive source citation pills with page titles and "Last crawled" badges.
- [x] Style fallback responses with distinct amber warning visual cues.
- [x] Build covered products drawer/modal populated from `GET /api/products`.
- [x] Add quick-start suggestion chips covering all 5 evaluation categories.
- [x] Mount static directory in FastAPI and verify Vercel serverless static route handling.

**Exit Check**:
- Browser UI opens cleanly from `fastapi dev app/main.py` and handles multi-turn conversation, citations, and product drawer.
- Preview deployed or verified on Vercel environment.

---

## Phase 6: Evals, Tracing & Quality Assurance

- [x] Assemble 15 golden questions in `tests/eval_set.json` (3 per category).
- [x] Implement evaluation script measuring hit@k, groundedness, and fallback precision (`scripts/run_eval.py`).
- [x] Configure LangSmith or Langfuse tracing hooks for node latency and token tracking.
- [x] Execute prompt injection test ensuring data context delimiters prevent instruction hijacking.

**Exit Check**:
- Automated evaluation achieves 100% accuracy on golden test set (15/15 passed).
- Injection payloads are safely treated as passive text data.

---

## Phase 7: Final Documentation & Demo Deliverables

- [x] Write 4 to 6 page Technical Document (`docs/technical_report.md` with Mermaid diagrams).
- [x] Finalize `README.md` with setup guide, API prerequisites, Vercel instructions, and AI disclosure.
- [x] Export final `coverage_report.md` proving 100% product coverage.
- [x] Prepare 5-minute recorded demonstration script (`docs/demo_script.md`).
- [x] Verify clean checkout reproducibility from README alone.

**Exit Check**:
- Full repo adheres to coding standards, passes Ruff linter, and contains no secrets.

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

- [ ] Implement page classification to identify distinct product and service offerings.
- [ ] Generate structured `data/products_catalog.json` (`name`, `category`, `url`, `page_id`) validated via Pydantic.
- [ ] Store catalog entries in SQLite `products` table.
- [ ] Implement automated coverage verification generating `data/coverage_report.md`.

**Exit Check**:
- `data/products_catalog.json` contains all visible site products with zero invented entries.
- Coverage report validates that every discovered product page is recorded.

---

## Phase 3: Heading-Aware Chunking & Qdrant Hybrid Indexing

- [ ] Implement heading-aware chunker (300 to 600 tokens) that preserves tables as indivisible blocks.
- [ ] Prepend structural context lines to each chunk (`Product: <Name> > <Section>`).
- [ ] Integrate Gemini API for 768-dim dense embeddings (`gemini-embedding-001`).
- [ ] Integrate FastEmbed / Qdrant BM25 for sparse token representations.
- [ ] Implement `scripts/build_kb.py` to run discovery, extraction, chunking, and dual-vector upsert in one command.
- [ ] Add `--refresh` flag to re-crawl, hash-check, and incrementally update changed pages.

**Exit Check**:
- Running `python -m scripts.build_kb` executes end-to-end without errors.
- Qdrant collection contains dense and sparse vectors for all chunks.
- Per-product probe query achieves 100% top-5 recall across all catalog items.

---

## Phase 4: LangGraph StateGraph Workflow & Guardrails

- [ ] Query Context7 MCP for the latest LangGraph StateGraph API syntax.
- [ ] Define `ChatState` TypedDict in `app/graph/state.py`.
- [ ] Implement rewriter node to resolve pronouns and conversational history into standalone queries.
- [ ] Implement intent router node (`FACT`, `DISCOVERY`, `COMPARISON`, `OUT_OF_SCOPE`).
- [ ] Implement parallel comparison retrieval using sub-query decomposition (`asyncio.gather`).
- [ ] Implement relevance grader node (Score $\ge 0.35$ gate).
- [ ] Implement grounded generator node using Gemini Flash with strict Pydantic `LLMAnswerOutput` schema.
- [ ] Implement number verification guardrail (cross-check figures against chunk text).
- [ ] Implement citation builder to construct verified source links from chunk metadata.
- [ ] Implement polite fallback node for out-of-scope or unanswerable queries.
- [ ] Compile and expose workflow in `app/graph/workflow.py` and connect to `POST /api/chat`.

**Exit Check**:
- Automated test suite (`pytest tests/test_graph.py`) passes across all 5 assignment question types.
- Comparisons retrieve context for both products without context starvation.
- Unanswerable or out-of-scope queries trigger fallback with zero hallucinated figures.

---

## Phase 5: Zero-Build Chat UI & Vercel Parity

- [ ] Build `static/index.html` and `static/styles.css` using Tailwind CSS CDN and Marked.js CDN.
- [ ] Render interactive source citation pills with page titles and "Last crawled" badges.
- [ ] Style fallback responses with distinct amber warning visual cues.
- [ ] Build covered products drawer/modal populated from `GET /api/products`.
- [ ] Add quick-start suggestion chips covering all 5 evaluation categories.
- [ ] Mount static directory in FastAPI and verify Vercel serverless static route handling.

**Exit Check**:
- Browser UI opens cleanly from `fastapi dev app/main.py` and handles multi-turn conversation, citations, and product drawer.
- Preview deployed or verified on Vercel environment.

---

## Phase 6: Evals, Tracing & Quality Assurance

- [ ] Assemble 15 golden questions in `tests/eval_set.json` (3 per category).
- [ ] Implement evaluation script measuring hit@k, groundedness, and fallback precision.
- [ ] Configure LangSmith or Langfuse tracing hooks for node latency and token tracking.
- [ ] Execute prompt injection test ensuring data context delimiters prevent instruction hijacking.

**Exit Check**:
- Automated evaluation achieves $\ge 90\%$ accuracy on golden test set.
- Injection payloads are safely treated as passive text data.

---

## Phase 7: Final Documentation & Demo Deliverables

- [ ] Write 4 to 6 page Technical Document (Assumptions, HLD, Data Pipeline, LLD, and Risks with Mermaid diagrams).
- [ ] Finalize `README.md` with setup guide, API prerequisites, Vercel instructions, and AI disclosure.
- [ ] Export final `coverage_report.md` proving 100% product coverage.
- [ ] Prepare 5-minute recorded demonstration script.
- [ ] Verify clean checkout reproducibility from README alone.

**Exit Check**:
- Full repo adheres to coding standards, passes Ruff linter, and contains no secrets.

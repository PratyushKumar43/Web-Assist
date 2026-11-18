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
- [x] Generate synthetic catalog anchor chunks (`app/catalog_chunks.py`: 1 master overview + 1 directory per category) and upsert them with the KB build.
- [x] Create a keyword payload index on `category` at build time so retrieval can filter by category.
- [x] Verified live indexing into Qdrant Cloud collection `site_kb` (208 points).

**Exit Check**:
- Running `python -m scripts.build_kb` executes end-to-end without errors.
- Qdrant collection contains dense and sparse vectors for all chunks.
- Per-product probe query achieves 100% top-5 recall across all catalog items.
- A filtered query on `category = "Credit Cards"` succeeds without a payload-index error.

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
- [x] Resolve bare continuations and affirmations ("tell me all", "list them", "yes please") against the active banking topic.
- [x] Keep listing queries in DISCOVERY (listing cue outranks attribute keywords) and add "types of ..." / "about your products" triggers.
- [x] Diversify DISCOVERY retrieval (`top_k=20`, max 2 chunks per product, category filter pushdown) and exclude catalog anchors from product entities.

**Exit Check**:
- `python -m pytest tests/ -q` passes (69 tests) across all 5 assignment question types plus conversational continuations.
- Comparisons retrieve context for both products without context starvation.
- The 3-turn sequence "about your products?" -> "types of credit card?" -> "tell me all" keeps DISCOVERY intent and the Credit Cards category.
- Unanswerable or out-of-scope queries trigger fallback with zero hallucinated figures.

---

## Phase 5: Zero-Build Chat UI & Vercel Parity

- [x] Build `static/index.html` as a single file: inline CSS, vanilla JS, no CDN and no build step.
- [x] Render each answer as structured blocks (intro, spec grid, product cards, bullets) from a typed view model instead of client-side markdown.
- [x] Add `POST /api/chat/ui` (`app/ui_view.py`) projecting `ChatResponse` onto `UIChatResponse`.
- [x] Render collapsible source citations with page titles and "Last crawled" dates.
- [x] Style fallback responses with an amber bubble, a decline badge, and recovery chips.
- [x] Show the live catalog size in the header from `GET /api/products`.
- [x] Add quick-start suggestion chips drawn from the golden eval set.
- [x] Add per-answer thumbs feedback via `POST /api/feedback` (recorded, never mutates the index).
- [x] Mount static directory in FastAPI and verify Vercel serverless static route handling.

**Exit Check**:
- Browser UI opens cleanly from `fastapi dev app/main.py` and handles multi-turn conversation, citations, product cards, and fallback styling.
- `tests/test_ui_view.py` and `tests/test_api.py` cover the view model, the UI endpoint, and feedback validation.
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

---

## Phase 8: Retrieval, Memory, Scraping & Routing Hardening (Post-Launch)

Observed in live testing: intent misclassification, conversational memory loss, DOM/UI noise in product names, and single-document collapse on broad discovery.

- [x] **Scraping**: strip feedback widgets, survey prompts, accessibility banners, and yes/no button rows (`app/clean.py`).
- [x] **Chunking**: derive `product_name` from a cleaned `<title>`; never from raw `<h2>`/`<h3>` or navigation noise (`app/chunk.py`).
- [x] **Memory**: bind bare continuations and affirmations to the active topic; when no listing thread is active, repeat the prior question instead of inventing one (`app/graph/nodes.py`).
- [x] **Routing**: "about your products?" and "types of credit card?" route to DISCOVERY; listing cues outrank attribute keywords.
- [x] **Retrieval**: widen DISCOVERY to 20 candidates, cap 2 chunks per product, and push a `category` filter into Qdrant with an unfiltered fallback.
- [x] **Catalog anchors**: 9 synthetic overview/directory chunks generated and ingested (`app/catalog_chunks.py`).
- [x] **Live cleanup**: deleted 21 UI-noise points from `site_kb` (229 -> 208 points) and created the `category` keyword payload index.
- [x] **Regression guard**: catalog anchor chunks excluded from `products_in_context` and from COMPARISON retrieval.
- [x] **Fact purity**: FACT extraction ignores catalog-directory chunks and scraper metadata headers ("Official Regulatory & Policy Context for", "Product Category"), and only cites chunks that actually contributed a fact.
- [x] **Comparison determinism**: a COMPARISON keeps the router's named pair, in order; `products_in_context` is deduped in retrieval order instead of being built from a `set` (which made the compared pair depend on the process hash seed).

**Exit Check**:
- 3-turn sequence "about your products?" -> "types of credit card?" -> "tell me all" returns 21 -> 7 -> 7 rows with zero UI noise.
- `python -m pytest tests/ -q` passes 69/69; `python -m scripts.run_eval` passes 15/15.
- Filtered search (`category = "Credit Cards"`) returns results with no payload-index error.

---

## Phase 9: WhatsApp-Style UI & Render-Ready View Model (Post-Launch)

Replaced the Tailwind/Marked frontend with a single-file WhatsApp-style shell, and moved all shaping of the answer to the server so the browser can never invent content.

- [x] Rebuild `static/index.html` with inline CSS, a dark/light token set, bubbles, ticks, and a pill input.
- [x] Add `app/ui_view.py`: parses the grounded markdown answer once and projects it onto `intro`, `specs`, `cards`, `bullets`, `sources`, `next_chips`.
- [x] Add `UIChatResponse`, `UISpec`, `UICard`, `FeedbackRequest`, `FeedbackResponse` schemas to `app/models.py`.
- [x] Expose `POST /api/chat/ui` alongside the unchanged `POST /api/chat` contract.
- [x] Expose `POST /api/feedback`, recording `interaction_id` + rating to `data/feedback.jsonl`.
- [x] Populate the header coverage pill from `GET /api/products`; remove the hardcoded product count.
- [x] Remove the client-side simulated-response mode; a backend failure now renders an honest error bubble.
- [x] Escape all dynamic values and drive interactions through `data-*` attributes with one delegated listener.
- [x] Allow only `http(s)` source URLs through a protocol allowlist.

**Exit Check**:
- DISCOVERY renders product cards, FACT a spec grid, COMPARISON two cards, and OUT_OF_SCOPE an amber bubble with no cards.
- `python -m pytest tests/ -q` passes 78/78, including `tests/test_ui_view.py`.
- `node --check` on the page's script reports no syntax errors.

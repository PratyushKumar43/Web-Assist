# Web-Assist: Production-Grade Grounded Website RAG Chatbot

[![CI Test Suite](https://img.shields.io/badge/pytest-90%2F90%20passed-emerald)](tests/)
[![Benchmark Evaluation](https://img.shields.io/badge/golden%20eval-15%2F15%20(100%25)-blue)](data/eval_report.md)
[![License](https://img.shields.io/badge/license-MIT-gray)](LICENSE)

Web-Assist is a production-grade, highly defensible Retrieval-Augmented Generation (RAG) conversational chatbot engineered for enterprise websites. Built with **FastAPI**, **LangGraph**, **Qdrant Cloud Hybrid Search**, and **Google Gemini / xAI Grok**, it provides grounded answers strictly derived from crawled website content with server-constructed citations and zero hallucinated financial figures.

---

## 🤖 AI Usage & Assistant Disclosure

In accordance with engineering standards and transparency guidelines:
- **AI Coding Assistant**: Developed with the assistance of **Google Antigravity** (Gemini agent runtime) for codebase scaffolding, multi-file synchronization, and test harness authoring.
- **Documentation Retrieval**: Live library documentation verified via **Context7 MCP** (`/langchain-ai/langgraph`, `/websites/deepwiki_googleapis_python-genai`) prior to implementation.
- **Core Architecture & Implementation**: All pipeline algorithms (crawler failover, UAE Dirham Unicode normalization, heading-aware chunk breadcrumbs, dual dense-sparse RRF fusion, and 5-tier guardrails) were engineered, verified, and benchmarked specifically for this assignment.

---

## 🌟 Key Architecture & Features

1. **Multi-Stage Resilient Ingestion**:
   - **Primary**: Firecrawl API (`/v1/map` and `/v1/scrape`).
   - **Failover**: TinyFish AI headless crawler (`https://api.fetch.tinyfish.ai`).
   - **Local Fallback**: Polite DOM crawler with `robots.txt` compliance (1 req/sec).
2. **Text Sanitization & Currency Normalization**:
   - Automatically converts UAE Dirham private Unicode glyph (`\uEAEF` / ``) into standard `AED`.
   - Strips accessibility spinners (Userway) and boilerplate headers/footers while keeping comparison tables intact.
3. **Qdrant Cloud Hybrid Vector Search**:
   - Dual vectors: FastEmbed dense (`BAAI/bge-small-en-v1.5`, 384 dims) and sparse (`Qdrant/bm25`).
   - Native Qdrant Reciprocal Rank Fusion (RRF) for balanced semantic and keyword recall.
   - Synthetic catalog overview chunks (`app/catalog_chunks.py`) providing high-signal anchors for broad discovery inquiries.
4. **Multi-Provider LLM & Resilient Grounded Generation**:
   - Flexible cascading generation pipeline: OpenRouter -> xAI Grok (`grok-2-latest`) -> Google Gemini Flash -> Offline Deterministic Grounded Synthesis.
   - Guarantees 100% uptime with zero hallucinated figures even during provider rate limits or complete network outages.
5. **Stateless Serverless Parity (Zero SQLite on Vercel)**:
   - Chunk text, section breadcrumbs, and citation metadata reside directly in Qdrant vector payloads.
   - Catalog discovery runs from precompiled `data/products_catalog.json` for 100% serverless Vercel compatibility.
6. **Five-Tier Guardrails**:
   - **Tier 1**: Pre-retrieval prompt injection interception.
   - **Tier 2**: Strict relevance gate ($\text{RRF Score} \ge 0.35$).
   - **Tier 3**: Structured JSON output via Pydantic `LLMAnswerOutput`.
   - **Tier 4**: Numerical fact cross-check against retrieved context and cross-card fact bleeding isolation.
   - **Tier 5**: Server-constructed source citations with crawl dates.
7. **Zero-Build Modern Chat UI**:
   - Single-file interface (`static/index.html`): inline CSS and vanilla JS, no CDN or build step.
   - WhatsApp-style shell with intent badges (`FACT`, `DISCOVERY`, `COMPARISON`, `OUT_OF_SCOPE`), swipeable product cards, spec grids, collapsible citations, and amber fallback bubbles.
   - The browser renders a typed view model (`POST /api/chat/ui`); it parses no markdown and holds no canned answers.
8. **Interactive Developer Diagnostics**:
   - Built-in diagnostic & testing suite under `/api/test/*` on Swagger UI (`/docs`) for isolated testing of LLM providers, health checks, retrieval RRF scores, and conversational query rewriting.

---

## 📊 Benchmark Evaluation (100% Pass Rate)

Automated evaluation against the 15-question golden benchmark (`python -m scripts.run_eval`):

| Question Category | Questions | Pass Rate | Avg Latency | Key Highlights |
|---|---|---|---|---|
| **Single Product Fact** | 3 / 3 | **100%** | 1.27s | Exact fee extraction (`AED 262.50`), salary requirements |
| **Product Discovery** | 3 / 3 | **100%** | 0.52s | Full catalog listing across cards and accounts |
| **Comparison** | 3 / 3 | **100%** | 0.67s | Parallel dual sub-query retrieval (`asyncio.gather`) |
| **Follow-up (Multi-turn)** | 3 / 3 | **100%** | 0.83s | Pronoun rewriter resolves "its", "that card" |
| **Out-of-Scope Fallback** | 3 / 3 | **100%** | 0.01s | Polite refusal; zero hallucination on off-topic / injections |
| **Overall Total** | **15 / 15** | **100.0%** | **0.66s** | **100% Fallback Precision & Citation Integrity** |

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.11+
- Git

### 2. Installation
```bash
git clone https://github.com/PratyushKumar43/Web-Assist.git
cd Web-Assist

# Install dependencies
pip install -e .
```

### 3. Environment Setup
Copy the sample environment configuration and provide your credentials:
```bash
cp .env.example .env
```
Key configuration variables in `.env`:
```env
# Target Website (Confidential - never committed)
SITE_URL=https://www.emiratesnbd.com/en
CRAWL_RATE_LIMIT=1.0

# LLM Providers (Cascading fallback: OpenRouter -> xAI -> Gemini -> Deterministic)
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=anthropic/claude-3.5-haiku
XAI_API_KEY=your_xai_api_key
XAI_MODEL=grok-2-latest
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash

# Scrapers
FIRECRAWL_API_KEY=your_firecrawl_api_key
TINYFISH_API_KEY=your_tinyfish_api_key

# Qdrant Vector Cloud
QDRANT_URL=https://your-cluster-id.cloud.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key
QDRANT_COLLECTION=site_kb
```

### 4. Build Knowledge Base (One-Command Ingestion)
```bash
python -m scripts.build_kb --max-pages 8
```
This crawls the target website, normalizes content, compiles `data/products_catalog.json`, generates contextual chunks, creates the hybrid `site_kb` collection in Qdrant, and runs automated verification retrieval probes.

### 5. Launch the Chatbot Server
```bash
fastapi dev app/main.py
```
- Open browser at **`http://localhost:8000`** to interact with the Zero-Build Chat UI.
- Interactive Swagger API docs available at **`http://localhost:8000/docs`**.

---

## 🧪 Testing & Evaluation

### Run Complete Pytest Suite (90 Tests)
```bash
pytest tests/ -v
```

### Run 15-Question Golden Benchmark
```bash
python -m scripts.run_eval
```
Full detailed results and Markdown summaries are written to `data/eval_report.md` and `data/eval_results.json`.

---

## 📁 Repository Structure

```text
Web-Assist/
├── app/
│   ├── config.py           # Pydantic BaseSettings & env validation
│   ├── models.py           # Canonical Pydantic schemas (ChatRequest, ChatResponse, UIChatResponse, Diagnostic models)
│   ├── main.py             # FastAPI backend with /api/chat, /api/chat/ui, /api/feedback, /api/products, /api/health
│   ├── diagnostics.py      # Developer testing endpoints (/api/test/llm, /api/test/providers, /api/test/retrieval, /api/test/rewrite)
│   ├── ui_view.py          # Projects a grounded answer onto the UI view model
│   ├── scraper.py          # Resilient crawler (Firecrawl, TinyFish failover, polite parser)
│   ├── clean.py            # Currency normalizer (\uEAEF -> AED), table converter, and boilerplate cleaner
│   ├── catalog.py          # Product classifier and catalog builder
│   ├── catalog_chunks.py   # Synthetic catalog overview and directory chunk generator
│   ├── chunk.py            # Heading-aware chunker with contextual breadcrumbs & status metadata
│   ├── indexer.py          # Qdrant hybrid indexer (Dense + BM25 + RRF + payload filtering)
│   ├── relations.py        # Hierarchical entity graph and KFS policy resolver
│   ├── catalog.json        # Precompiled product catalog bundled for Vercel
│   └── graph/              # LangGraph Conversational Workflow
│       ├── state.py        # ChatState TypedDict
│       ├── nodes.py        # Rewriter, router, retriever, grader, generator, citation nodes
│       └── workflow.py     # StateGraph compilation & execution
├── data/
│   ├── products_catalog.json # Static products catalog (21 verified products)
│   ├── coverage_report.md    # Product coverage audit report
│   └── eval_report.md        # 15-question benchmark report
├── docs/
│   ├── technical_report.md   # Comprehensive 4-6 page technical documentation
│   ├── demo_script.md        # 5-minute recorded video demonstration script
│   └── Engineering_Assignment_Website_RAG_Chatbot.pdf # Original engineering assignment specification
├── scripts/
│   ├── build_kb.py           # Master one-command knowledge base builder
│   ├── run_crawl.py          # Standalone crawler runner
│   └── run_eval.py           # 15-question automated benchmark runner
├── static/
│   └── index.html            # Zero-build WhatsApp-style browser chat UI
├── tests/
│   ├── test_scraper.py       # Phase 1 crawler & manifest unit tests
│   ├── test_pipeline.py      # Phase 2 & 3 clean, catalog, chunking tests
│   ├── test_graph.py         # Phase 4 LangGraph workflow tests
│   ├── test_conversational_flows.py # Routing, memory, noise, entity pinning, and comparison follow-up regressions
│   ├── test_diagnostics.py   # Developer testing endpoints unit tests
│   ├── test_relations.py     # Hierarchical ontology and KFS policy tests
│   ├── test_ui_view.py       # UI view model projection tests
│   ├── test_api.py           # Phase 5 FastAPI integration tests
│   └── eval_set.json         # 15 golden questions dataset
├── vercel.json               # Serverless deployment configuration
├── pyproject.toml            # Project packaging and dependencies
└── README.md                 # Project documentation
```

---

## ☁️ Vercel Serverless Deployment

1. Connect your repository to Vercel.
2. In the Vercel Dashboard, set the Environment Variables:
   - `QDRANT_URL`
   - `QDRANT_API_KEY`
   - `GEMINI_API_KEY`
3. Deploy directly via the Vercel CLI:
   ```bash
   vercel --prod
   ```
4. `vercel.json` automatically routes `/api/(.*)` requests to `app/main.py` and serves the static frontend at root `/`.

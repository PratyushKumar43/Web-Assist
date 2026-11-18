# Rules: Website RAG Chatbot

> Inviolable guardrails for human and AI developers. Every contribution must adhere to these rules.

---

## 1. Always

- **Consult `agent.md` and `memory.md` FIRST**: Never consume context tokens by mass-reading the codebase.
- **Query Context7 MCP Before Implementing**: Before writing or modifying code that uses any external library, framework, SDK, or cloud service (e.g. LangGraph, FastAPI, Qdrant, Google GenAI, Pydantic), query Context7 MCP (`resolve-library-id` + `query-docs`) to verify current APIs and syntax.
- **Enforce Pydantic Validation Everywhere**: Use Pydantic v2 schemas (`pydantic.BaseModel` and `pydantic_settings.BaseSettings`) for all configuration, API request/response contracts, and structured LLM outputs.
- **Local Dev Server Execution**: Use `fastapi dev app/main.py` as the standard command for local development and testing.
- **Enforce 5-Tier Guardrails**: Always enforce input length/injection checks, retrieval score gate, numeric consistency checks, server-constructed citations, and privacy boundaries.
- **Phase Discipline**: Work on ONE phase at a time as outlined in `phases.md`. Do not start a subsequent phase until the current phase's exit check passes.
- **Explainability**: Keep code modular and clean; every single line and architectural choice must be easily explainable in a live review call.
- **Type Safety & Docstrings**: Include Python type hints and concise docstrings for all functions and data models.
- **Log State Updates**: Update `memory.md` (Current Status, Decisions, Session Log) at the end of each session or phase.

---

## 2. Never

- **Never Hardcode the Site URL**: The target website URL, domain name, and specific product names are strictly confidential. The target URL resides solely in `.env` (`SITE_URL`).
- **Never Commit Secrets or Local Data**: `.env`, API keys (`GEMINI_API_KEY`, `FIRECRAWL_API_KEY`, `TINYFISH_API_KEY`, `QDRANT_API_KEY`), `data/`, raw scrapes, `kb.db`, or local Qdrant vectors must never be added to Git.
- **Never Let LLMs Generate Raw URLs**: Citation links and metadata must be constructed server-side from verified retrieved chunk metadata.
- **Never Guess When Retrieval is Weak**: If the relevance score fails the gate (`MIN_RELEVANCE_SCORE`), immediately trigger the polite fallback with `answerable: false`.
- **Never Make Up Products or Catalog Data**: All catalog entries must be verified against actual crawled site pages.
- **Never Ignore Web Politeness**: Always validate `robots.txt` and throttle crawling to a maximum of 1 request per second.

---

## 3. Approved Tech Stack

Only the following libraries and tools are approved for use in this project:
- **Server CLI & Framework**: `fastapi[standard]>=0.110.0` (includes `fastapi-cli` for `fastapi dev`)
- **Orchestration**: `langgraph>=0.2.0`, `langchain-core>=0.3.0`
- **Data Schemas & Settings**: `pydantic>=2.6.0`, `pydantic-settings>=2.2.0`
- **GenAI & Embeddings**: `google-genai>=1.0.0`
- **Vector Storage & Search**: `qdrant-client>=1.8.0`, `fastembed>=0.2.0`
- **Web Scraping & Ingestion**: `firecrawl-py>=0.0.16`, TinyFish AI TinyFetch (`https://www.tinyfish.ai/`)
- **Database**: Python standard library `sqlite3`
- **Frontend**: Zero-build HTML5, vanilla JavaScript, Tailwind CSS (CDN), Marked.js (CDN)
- **Quality & Testing**: `ruff`, `pytest`, `pytest-asyncio`

---

## 4. Coding Standards

- Python 3.11+, formatted and linted with `ruff`.
- Single-responsibility functions (< 40 lines).
- Pure functions for chunking, scoring, and text cleaning to facilitate straightforward unit testing.
- Meaningful variable names reflecting business domain concepts (`reranked_chunks`, not `temp_data`).
- Use Python's built-in `logging` module; do not use raw `print()` statements.

---

## 5. Security & Guardrails

- **Delimited Prompts**: Retrieved content must be clearly delimited with XML/Markdown fences and labeled strictly as passive reference data in prompts.
- **Numeric Grounding**: Numeric values (prices, fees, percentages) must be cross-checked against chunk context before final output.
- **Sandboxed LLM**: The LLM operates without executable tools or external network browsing capabilities.
- **Sanitized Outputs**: Model output is rendered in the frontend as sanitized text or sanitized Markdown, preventing DOM injection.

---

## 6. Git & Commit Protocol

- Remote repository: `https://github.com/PratyushKumar43/Web-Assist.git`.
- Atomic commits matching the convention: `phase-N: description of change`.
- Always inspect `git status` and diffs prior to committing to ensure no credentials or confidential data are tracked.

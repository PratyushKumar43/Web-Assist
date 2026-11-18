# Agent Guidelines & Session Handoff Handbook

> **Audience**: AI Agents (Antigravity sessions, subagents, or switched models).
> **Purpose**: Enables any fresh agent session to resume work immediately with zero token waste, without reading the full codebase or hallucinating context.

---

## 1. Quick Session Bootstrap (Zero Token Thrashing)

When you wake up in a new turn, new conversation, or switched model:
**DO NOT scan the entire directory tree or bulk-read project files.**

Follow this strict bootstrap sequence:
1. **Read `agent.md`** (this file) for operational and communication rules.
2. **Read `memory.md`** to load the active project state, recent decisions, open issues, and session log.
3. **Read `phases.md`** to identify the exact active phase and its required exit check.
4. **Read ONLY the specific files** listed in `memory.md` under "Where things live" that touch the active phase.

---

## 2. Mandatory Pre-Implementation Rule: Context7 MCP

Before writing, editing, or scaffolding code that uses an external library, framework, SDK, or cloud service (e.g., **LangGraph**, **Pydantic**, **FastAPI**, **Qdrant**, **Google GenAI**):
1. **Query Context7 MCP**:
   - `resolve-library-id` with the library name (e.g., `fastapi`, `pydantic`, `langgraph`, `qdrant-client`, `google-genai`).
   - `query-docs` with the resolved ID and the specific API or pattern you need (e.g., `fastapi dev`, `Pydantic BaseSettings`, `StateGraph Send comparison`, `Hybrid search RRF`).
2. **Implement based on current documentation**:
   - Never rely solely on pre-trained memory for dynamic SDK APIs.
   - Enforce Pydantic v2 schemas across all configuration, API contracts, and structured outputs.

---

## 3. Server Execution & Dev Workflow

- **Start Local Dev Server**: `fastapi dev app/main.py`
  - Auto-reload enabled.
  - Interactive docs at `http://127.0.0.1:8000/docs`.
  - Frontend served at `http://127.0.0.1:8000/`.
- **Production Server**: `fastapi run app/main.py --port 8000`

---

## 4. Scope & Multi-Tier Guardrails

1. **Strict Confidentiality**:
   - The target website URL is strictly confidential.
   - It lives ONLY in `.env` (`SITE_URL`).
   - NEVER hardcode, print, log, or commit the real domain or URL anywhere in code, markdown, tests, or commit messages.
2. **Input Guardrails**:
   - Pydantic length validation (1 to 2000 chars).
   - Prompt injection defense: sanitize instruction-like overrides.
3. **Retrieval & Relevance Guardrails**:
   - Out-of-scope intent router redirects non-product queries directly to fallback.
   - RRF score gate (`MIN_RELEVANCE_SCORE = 0.35`) bypasses LLM if relevance is low.
   - Comparison sub-query decomposition prevents context starvation.
4. **Generation & Numeric Guardrails**:
   - Grounded context fence: context labeled as read-only data.
   - Numeric verification: all prices, fees, and figures must appear verbatim in context.
   - LLM prohibited from outputting raw URLs.
5. **Output Guardrails**:
   - Verified source links built server-side from chunk metadata.
   - Frontend markdown sanitized against DOM XSS.
6. **Dual Runtime Parity**:
   - Local: `fastapi dev app/main.py` + local Qdrant / SQLite.
   - Cloud: Vercel Serverless (`vercel.json`) + Qdrant Cloud.
7. **Git Hygiene**:
   - Remote: `https://github.com/PratyushKumar43/Web-Assist.git`.
   - Never commit `.env`, `data/`, `*.db`, or secrets.
   - Commit convention: `phase-N: what changed`.

---

## 5. Phase Execution Protocol

For each phase:
1. Check the active phase in `phases.md`.
2. Implement required features cleanly:
   - Pydantic models for validation and structured typing.
   - Single-responsibility functions (< 40 lines).
   - Structured error handling and logging (no bare `print`).
3. Run the automated and manual exit checks for that phase.
4. DO NOT proceed to the next phase until the current phase exit check passes.

---

## 6. End-of-Session Handoff Checklist

Before ending your turn or when a model quota is nearing completion:
1. **Update `memory.md`**:
   - Update **Current status** (current phase, last exit check passed, next action).
   - Add new entries to **Decisions made** or **Thresholds in use** if any changed.
   - Append an entry to the **Session log** table:
     ```markdown
     | YYYY-MM-DD | Phase N | Exact changes made | Next immediate step |
     ```
2. **Report State**:
   - Give the user a concise summary of what was accomplished and what the next session will execute.

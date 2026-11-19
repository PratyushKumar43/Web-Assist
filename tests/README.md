# Test Suite & Evaluation Dataset

This directory contains the automated test suite and golden evaluation dataset for the **Web-Assist** platform.

---

## Running Tests

### Complete Pytest Suite (90 Tests)
```bash
pytest tests/ -v
```

### Targeted Module Testing
```bash
# Test conversational flows, memory, and routing
pytest tests/test_conversational_flows.py -v

# Test FastAPI endpoints and CORS
pytest tests/test_api.py -v

# Test WhatsApp-style UI view model projections
pytest tests/test_ui_view.py -v

# Test developer testing & diagnostic endpoints
pytest tests/test_diagnostics.py -v

# Test LangGraph state machine execution
pytest tests/test_graph.py -v
```

---

## Test Modules Breakdown

| Test File | Covered Functionality |
| :--- | :--- |
| **`test_conversational_flows.py`** | Multi-turn conversational flows, bare continuations (`"tell me all"`), dual-subject comparison follow-ups (`"what about both of their fees?"`), entity pinning decoupling, noise stripping, and regression tests. |
| **`test_api.py`** | FastAPI integration tests: `GET /api/health`, `GET /api/products`, `POST /api/chat`, `POST /api/chat/ui`, `POST /api/feedback`, and CORS validation. |
| **`test_ui_view.py`** | Validates `app/ui_view.py` projections onto `UIChatResponse`, ensuring typed cards, spec grids, bullet points, and source drawers format accurately without client-side markdown parsing. |
| **`test_diagnostics.py`** | Tests developer diagnostic endpoints: `/api/test/llm`, `/api/test/providers`, `/api/test/retrieval`, and `/api/test/rewrite`. |
| **`test_graph.py`** | LangGraph StateGraph nodes: rewriter, router, parallel comparison retriever, relevance grader, generator, citation builder, and fallback node. |
| **`test_relations.py`** | Hierarchical entity knowledge graph and Key Facts Statement (KFS) policy resolution tests. |
| **`test_pipeline.py`** | Currency normalization (`\uEAEF` -> `AED`), table-to-prose conversion, and product catalog classification. |
| **`test_scraper.py`** | Scraper resilience, `robots.txt` politeness checks, and TinyFish AI failover logic. |
| **`test_scraper_pipeline.py`** | 4-stage ingestion pipeline tests (Discovery, Extraction, Normalization, Audit). |
| **`eval_set.json`** | Golden test dataset containing **15 verified test queries** (3 per category) across Single Product Fact, Product Discovery, Comparison, Multi-Turn Follow-Up, and Out-of-Scope Fallback. |

# Application Source Code Architecture

This directory contains the production application modules for the **Web-Assist** platform.

---

## Architecture Overview

```
app/
├── config.py           # Pydantic BaseSettings & environment validation
├── models.py           # Canonical Pydantic schemas (ChatRequest, ChatResponse, UIChatResponse, Diagnostic schemas)
├── main.py             # FastAPI backend with /api/chat, /api/chat/ui, /api/feedback, /api/products, /api/health
├── diagnostics.py      # Developer testing endpoints (/api/test/llm, /api/test/providers, /api/test/retrieval, /api/test/rewrite)
├── ui_view.py          # Server-side projection of grounded answers onto typed UI view models
├── scraper.py          # Resilient 3-tier crawler (Firecrawl primary, TinyFish AI failover, polite parser)
├── clean.py            # UAE Dirham currency normalizer (\uEAEF -> AED), table converter, and boilerplate cleaner
├── catalog.py          # Product classifier and catalog manifest extractor
├── catalog_chunks.py   # Synthetic catalog overview and directory chunk generator for Qdrant
├── chunk.py            # Heading-aware chunker with contextual breadcrumbs & status metadata
├── indexer.py          # Qdrant Cloud hybrid indexer (Dense BGE-small + Sparse BM25 + RRF + payload filtering)
├── relations.py        # Hierarchical entity graph and Key Facts Statement (KFS) policy resolver
├── db.py               # SQLite offline staging manifest database interface
├── catalog.json        # Precompiled 21-product catalog bundled for serverless deployment
├── graph_ontology.json # Entity relationship mapping (cards, accounts, KFS policies)
├── graph/              # LangGraph Conversational Workflow
│   ├── state.py        # ChatState TypedDict definition
│   ├── nodes.py        # All 7 workflow nodes: rewriter, router, retriever, grader, generator, citation, fallback
│   └── workflow.py     # StateGraph compilation, conditional edge routing, and execution
└── scraper_pipeline/   # Modular 4-stage ingestion pipeline
    ├── discovery.py    # URL and link discovery
    ├── extractor.py    # Clean page extraction
    ├── registry.py     # Crawl registry and state tracking
    └── audit.py        # Scrape quality verification
```

---

## Core Operational Flows

1. **Query Rewriting (`app/graph/nodes.py`)**:
   - Resolves pronouns (*"its annual fee"*, *"both of them"*) using chat history.
   - Binds bare continuations (*"tell me all"*, *"yes please"*) to the active banking category.
   - Reframes dual-subject inquiries (*"what about both of their fees?"*) into structured comparison queries.

2. **Intent Classification & Routing (`app/graph/nodes.py`)**:
   - Detects prompt injection attempts (`ignore instructions`, `DAN`) and routes to immediate fallback.
   - Classifies queries into `FACT`, `DISCOVERY`, `COMPARISON`, `ABOUT`, or `OUT_OF_SCOPE`.

3. **Hybrid Retrieval (`app/indexer.py`)**:
   - Dual vectors: FastEmbed dense (`BAAI/bge-small-en-v1.5`, 384 dims) and sparse (`Qdrant/bm25`).
   - Fused via native Qdrant Reciprocal Rank Fusion (RRF).
   - Injects hierarchical KFS policy chunks for fee/balance inquiries.

4. **Grounded Generation & Guardrails (`app/graph/nodes.py`)**:
   - Cascading LLM generation: OpenRouter -> xAI Grok -> Google Gemini Flash -> Offline Deterministic Synthesis.
   - Tier 4 numerical fact verification: Verifies all numbers and currency figures exist verbatim in context chunks before delivering responses.
   - Server-constructed citations built strictly from chunk payloads.

5. **WhatsApp-Style UI View Projection (`app/ui_view.py`)**:
   - Projects server answers into structured UI blocks: `intro`, `specs`, `cards`, `bullets`, `sources`, and `next_chips`.
   - The browser parses zero markdown and renders verified figures directly.

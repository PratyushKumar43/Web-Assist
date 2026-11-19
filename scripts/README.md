# Automation & CLI Utilities

This directory contains standalone execution scripts and command-line automation tools for crawling, cleaning, indexing, and evaluating the **Web-Assist** platform.

---

## Utility Scripts

| Script | Purpose & Usage |
| :--- | :--- |
| **`build_kb.py`** | **Master Knowledge Base Builder**<br>Executes the entire ingestion pipeline in one command: discovers URLs via Firecrawl/sitemap, scrapes markdown, normalizes UAE Dirham Unicode (`\uEAEF` -> `AED`), extracts product catalog, generates heading-aware chunks, creates the hybrid `site_kb` collection in Qdrant, and runs automated recall probes.<br>```bash\npython -m scripts.build_kb --max-pages 8\n``` |
| **`run_eval.py`** | **15-Question Golden Benchmark Runner**<br>Evaluates the conversational RAG assistant against `tests/eval_set.json` covering Single Product Facts, Product Discovery, Comparisons, Multi-Turn Follow-Ups, and Out-of-Scope Fallbacks. Measures response accuracy, latency, and hallucination prevention.<br>```bash\npython -m scripts.run_eval\n``` |
| **`run_crawl.py`** | **Standalone Crawler Runner**<br>Runs the 3-tier crawler (Firecrawl primary, TinyFish AI failover, local polite DOM parser) and caches raw snapshots.<br>```bash\npython -m scripts.run_crawl --max-pages 5\n``` |
| **`deep_crawl_and_index.py`** | **Deep Multi-Hub Crawler**<br>Specifically crawls deep product category hubs (Current Accounts, Savings Accounts, Credit Cards, Wealth, and Key Facts Statements) and upserts contextual chunks to Qdrant.<br>```bash\npython -m scripts.deep_crawl_and_index\n``` |
| **`run_pipeline.py`** | **4-Stage Scraper Pipeline Execution**<br>Runs the modular scraper pipeline (`app/scraper_pipeline/`) across Discovery, Extraction, Normalization, and Audit stages.<br>```bash\npython -m scripts.run_pipeline\n``` |

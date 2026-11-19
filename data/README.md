# Data & Evaluation Artifacts

This directory stores verified product catalog manifests, automated evaluation results, and coverage audit reports for the **Web-Assist** platform.

---

## Tracked Artifacts

| File | Format | Description |
| :--- | :--- | :--- |
| **[products_catalog.json](file:///d:/PORTFOLIO%20PROJECTS/Web-Assist/data/products_catalog.json)** | JSON | Canonical manifest of the **21 verified products** across Credit Cards, Debit Cards, Commercial Cards, Savings Accounts, Current Accounts, Wealth & Investments, Banking Services, and Regulatory Disclosures. |
| **[eval_report.md](file:///d:/PORTFOLIO%20PROJECTS/Web-Assist/data/eval_report.md)** | Markdown | Benchmark report showing the **100% pass rate (15/15)** across all 5 core question categories (Single Fact, Discovery, Comparison, Multi-Turn Follow-Up, and Out-of-Scope Fallback). |
| **[eval_results.json](file:///d:/PORTFOLIO%20PROJECTS/Web-Assist/data/eval_results.json)** | JSON | Raw automated benchmark execution log with per-question latency, classification intent, and verification statuses. |
| **[coverage_report.md](file:///d:/PORTFOLIO%20PROJECTS/Web-Assist/data/coverage_report.md)** | Markdown | Audit report verifying that 100% of discovered product pages on the target site are indexed with zero hallucinated offerings. |
| **[scraper_audit_report.md](file:///d:/PORTFOLIO%20PROJECTS/Web-Assist/data/scraper_audit_report.md)** | Markdown | Crawl quality audit report detailing page counts, content status, and table extraction integrity. |

---

## Ignored Dynamic Data (Excluded via `.gitignore`)

The following files are generated dynamically during local crawler execution and testing, and are strictly excluded from source control:
- `data/raw/`: Cached raw HTML and markdown page snapshots from crawlers.
- `data/*.db` (`kb.db`, `registry.db`): Offline SQLite staging manifests (at runtime, Qdrant Cloud vector payloads are 100% stateless).
- `data/*.jsonl` (`feedback.jsonl`): Live user thumbs-up/down interaction ratings recorded from the browser UI.
- `data/qdrant_data/`: Local embedded Qdrant data files when not connected to Qdrant Cloud.

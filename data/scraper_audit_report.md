# Stateful Scraper Pipeline Audit Report

> **Generated:** 2026-11-18 06:27:55 UTC  
> **Target Domain:** https://www.emiratesnbd.com/en  
> **Registry DB:** `./data/registry.db`

---

## 1. Pipeline Summary Metrics

| Metric | Count | Notes |
|---|---|---|
| **Total Discovered URLs** | 471 | De-duplicated in persistent registry |
| **Successfully SCRAPED** | 4 | Quality-verified & cached |
| **PENDING Remaining** | 466 | Ready for next resume batch |
| **EMPTY / Thin (<200 chars)** | 0 | Blocked or no main content |
| **FAILED** | 1 | Errors recorded with retry counters |
| **New Links Discovered (Recursive)** | 0 | Captured via recursive link loop |

---

## 2. Discovery Sources Breakdown

| Discovery Source | URLs Discovered |
|---|---|
| Firecrawl /map | 0 |
| Robots.txt & XML Sitemaps | 0 |
| Navigation-Linked Crawl | 0 |
| Recursive Extraction Loop | 0 |

---

## 3. Extractor Performance Breakdown

| Extractor Engine | Pages Processed |
|---|---|
| Tier 1: Firecrawl API | 4 |
| Tier 2: TinyFish AI Browser | 0 |
| Tier 3: Local Parser Fallback | 1 |

---

## 4. Zero Silent Drop Guarantee Status

- ✅ **Persistent Statefulness:** All discovered URLs are saved to SQLite before extraction starts.
- ✅ **Atomic State Machine:** Every URL transitions to `SCRAPED`, `EMPTY`, or `FAILED` with explicit error logging.
- ✅ **Resumption Ready:** Next execution can resume directly from existing `PENDING` and `FAILED` rows.
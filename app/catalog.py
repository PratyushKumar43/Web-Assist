"""Product catalog extraction and verification module."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.clean import clean_page_content

logger = logging.getLogger(__name__)


def classify_category(url: str, title: str) -> str:
    """Classify product category based on URL path and title."""
    url_lower = url.lower()
    title_lower = title.lower()

    if "commercial-card" in url_lower or "business" in url_lower:
        return "Commercial Cards"
    elif "prepaid-card" in url_lower:
        return "Prepaid Cards"
    elif "credit-card" in url_lower or "credit card" in title_lower or "card" in url_lower or "card" in title_lower:
        return "Credit Cards"
    elif "savings-account" in url_lower or "savings" in title_lower:
        return "Savings Accounts"
    elif "current-account" in url_lower or "current" in title_lower:
        return "Current Accounts"
    elif "deposit" in url_lower or "fixed-deposit" in url_lower:
        return "Deposit Accounts"
    elif "islamic" in url_lower or "mudaraba" in url_lower:
        return "Islamic Banking"
    elif "auto-loan" in url_lower or "vehicle" in url_lower:
        return "Auto Loans"
    elif "home-loan" in url_lower or "mortgage" in url_lower:
        return "Home Loans"
    elif "personal-loan" in url_lower or "personal loan" in title_lower:
        return "Personal Loans"
    elif "loan" in url_lower:
        return "Loans & Financing"
    elif "rates-and-charges" in url_lower or "fees" in url_lower:
        return "Rates & Fees"
    return "Banking Services"


def extract_product_from_page(page_url: str, title: str, markdown: str) -> Optional[Dict[str, Any]]:
    """Extract product metadata, key figures, and summary from cleaned page text."""
    clean_md = clean_page_content(markdown)
    if not clean_md or len(clean_md) < 40:
        return None

    # Derive product name from first H1 or title
    h1_match = re.search(r"^#\s+(.+)$", clean_md, re.MULTILINE)
    if h1_match:
        product_name = h1_match.group(1).strip()
    else:
        # Clean title (strip ' | Emirates NBD')
        product_name = title.split("|")[0].strip()

    # Skip generic error, support, contact, or career landing pages without a specific product
    url_lower = page_url.lower()
    name_lower = product_name.lower()
    excluded_keywords = [
        "contact", "career", "life-at", "employee engagement", "would you like to talk",
        "something went wrong", "personal banking", "terms-and-conditions", "privacy",
        "help-and-support/contact-us", "feedback", "complaints",
    ]
    if any(k in url_lower or k in name_lower for k in excluded_keywords):
        return None

    category = classify_category(page_url, product_name)

    # Extract key figures: Annual Fee, Joining Fee, Minimum Balance / Salary
    annual_fee: Optional[str] = None
    joining_fee: Optional[str] = None
    min_requirement: Optional[str] = None

    af_match = re.search(r"Annual fees?:\s*(AED\s*[\d,]+(?:\.\d+)?)", clean_md, re.IGNORECASE)
    if af_match:
        annual_fee = af_match.group(1)

    jf_match = re.search(r"Joining fees?:\s*(AED\s*[\d,]+(?:\.\d+)?)", clean_md, re.IGNORECASE)
    if jf_match:
        joining_fee = jf_match.group(1)

    sal_match = re.search(r"Minimum salary(?:\s*required)?:\s*(AED\s*[\d,]+(?:\.\d+)?)", clean_md, re.IGNORECASE)
    if sal_match:
        min_requirement = f"Minimum Salary: {sal_match.group(1)}"
    else:
        bal_match = re.search(r"Minimum of\s*(AED\s*[\d,]+(?:\.\d+)?)", clean_md, re.IGNORECASE)
        if bal_match:
            min_requirement = f"Minimum Balance: {bal_match.group(1)}"

    # Extract 1-2 sentence description
    summary = ""
    lines = [line.strip() for line in clean_md.splitlines() if line.strip() and not line.startswith("#") and not line.startswith("!")]
    if lines:
        summary = lines[0][:250]

    product_id = re.sub(r"[^a-zA-Z0-9]+", "-", product_name.lower()).strip("-")

    return {
        "product_id": product_id,
        "name": product_name,
        "category": category,
        "url": page_url,
        "summary": summary,
        "annual_fee": annual_fee,
        "joining_fee": joining_fee,
        "min_requirement": min_requirement,
    }


def compile_and_save_catalog(
    pages: List[Dict[str, Any]],
    output_path: str = "./data/products_catalog.json",
) -> List[Dict[str, Any]]:
    """Compile distinct products across scraped pages and write catalog JSON files."""
    catalog: List[Dict[str, Any]] = []
    seen_ids = set()

    for page in pages:
        product = extract_product_from_page(
            page_url=page["url"],
            title=page["title"],
            markdown=page["markdown"],
        )
        if product and product["product_id"] not in seen_ids:
            seen_ids.add(product["product_id"])
            catalog.append(product)

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")

    # Also bundle into app/catalog.json for instant Vercel packaging (unless running in test tmp dir)
    if "tmp" not in str(output_path).lower() and "temp" not in str(output_path).lower():
        app_catalog = Path(__file__).resolve().parent / "catalog.json"
        app_catalog.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("Compiled %d products into catalog: %s", len(catalog), out_file)
    return catalog

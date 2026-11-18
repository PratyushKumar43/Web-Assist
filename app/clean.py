"""Cleaning and text normalization module for scraped bank content."""

import re
from typing import Optional


def normalize_currency(text: str) -> str:
    """Normalize private-use unicode UAE Dirham symbol to standard AED."""
    # Target site uses private-use Unicode character \uEAEF () for the AED symbol
    normalized = re.sub(r"[\uEAEF\uE000-\uF8FF]", "AED ", text)
    # Normalize non-breaking and zero-width spaces
    normalized = normalized.replace("\u00a0", " ").replace("\u200b", "")
    # Clean up redundant spaces around AED
    normalized = re.sub(r"AED\s+", "AED ", normalized)
    return normalized


def strip_boilerplate(markdown_text: str) -> str:
    """Strip website navigation artifacts, feedback widgets, and footer noise."""
    text = normalize_currency(markdown_text)

    # 1. Remove accessibility banner and skip-to-content links
    text = re.sub(r"(?i)skip to main content\s*", "", text)
    text = re.sub(r"(?i)enable accessibility for low vision\s*", "", text)
    text = re.sub(r"(?i)open the accessibility menu\s*", "", text)

    # 2. Remove Userway / accessibility spinners and decorative images
    text = re.sub(r"!\[(?:Spinner|Wheel)[^\]]*\]\([^)]+\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"!\[\]\([^)]+\)", "", text)

    # 3. Cut off trailing website footer and feedback surveys
    footer_markers = [
        "#### How was your experience?",
        "##### You are currently browsing",
        "## Emirates NBD on Social",
        "Website Settings",
        "#### Download our Apps",
        "Copyright 2026 Bank",
    ]
    for marker in footer_markers:
        pos = text.find(marker)
        if pos != -1:
            text = text[:pos]

    # 4. Clean excessive whitespace and empty lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def clean_page_content(raw_markdown: str) -> str:
    """Perform full sanitization pipeline on scraped page content."""
    if not raw_markdown:
        return ""
    cleaned = strip_boilerplate(raw_markdown)
    return cleaned


# Alias for backwards compatibility and readability
clean_markdown = clean_page_content

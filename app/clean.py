"""Cleaning and text normalization module for scraped bank content."""

import re
from typing import List, Optional


def normalize_currency(text: str) -> str:
    """Normalize private-use unicode UAE Dirham symbol to standard AED."""
    # Target site uses private-use Unicode character \uEAEF () for the AED symbol
    normalized = re.sub(r"[\uEAEF\uE000-\uF8FF]", "AED ", text)
    # Normalize non-breaking and zero-width spaces
    normalized = normalized.replace("\u00a0", " ").replace("\u200b", "")
    # Clean up redundant spaces around AED
    normalized = re.sub(r"AED\s+", "AED ", normalized)
    return normalized


def strip_ui_noise_and_counters(text: str) -> str:
    """Strip UI counters, interactive button labels, and navigation noise."""
    # Strip counters like "All accounts (10)", "All cards (7)", etc.
    text = re.sub(r"(?i)\bAll\s+(?:accounts|cards|products|loans|services)\s*\(\d+\)", "", text)
    # Strip standalone UI action buttons
    text = re.sub(r"(?i)^\s*(?:Apply\s+Now|Compare|Back\s+to\s+top|View\s+more|Read\s+more|Learn\s+more)\s*$", "", text, flags=re.MULTILINE)
    # Strip cookie and privacy banners
    text = re.sub(r"(?i)this website uses cookies.*?(?:accept|agree|got it|continue)", "", text, flags=re.DOTALL)
    return text


def strip_empty_table_pipes(text: str) -> str:
    r"""Strip empty or malformed Markdown table rows matching ^\|\s*(\|\s*)+$."""
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Remove lines that contain only pipes and whitespace
        if re.match(r"^\|\s*(\|\s*)+$", stripped):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def convert_tables_to_prose(text: str) -> str:
    """Convert complex Markdown tables into self-contained row-level natural language sentences.

    Ensures that when chunking occurs, row context (headers and specifications) is never
    lost across arbitrary chunk boundaries.
    """
    lines = text.splitlines()
    output_lines: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Detect table header row followed by delimiter row
        if (
            line.strip().startswith("|")
            and line.strip().endswith("|")
            and i + 1 < len(lines)
            and re.match(r"^\|\s*(?::?-+:?\s*\|)+\s*$", lines[i + 1].strip())
        ):
            header_raw = line.strip().split("|")[1:-1]
            headers = [h.strip() for h in header_raw]
            i += 2  # skip header and delimiter

            table_rows: List[str] = []
            while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                row_line = lines[i].strip()
                if not re.match(r"^\|\s*(\|\s*)+$", row_line):
                    cells = [c.strip() for c in row_line.split("|")[1:-1]]
                    if len(cells) == len(headers) and any(cells):
                        row_parts = [f"{h}: {c}" for h, c in zip(headers, cells) if c and c != "---"]
                        if row_parts:
                            table_rows.append(" | ".join(row_parts) + ".")
                i += 1

            if table_rows:
                output_lines.extend(table_rows)
            continue

        output_lines.append(line)
        i += 1

    return "\n".join(output_lines)


def strip_boilerplate(markdown_text: str) -> str:
    """Strip website navigation artifacts, feedback widgets, and footer noise."""
    text = normalize_currency(markdown_text)

    # 1. Remove accessibility banner, skip-to-content links, and enable-accessibility noise
    text = re.sub(r"(?i)skip to main content\s*", "", text)
    text = re.sub(r"(?i)enable accessibility(?:\s+for low vision)?\s*", "", text)
    text = re.sub(r"(?i)open the accessibility menu\s*", "", text)

    # 2. Remove feedback widgets, survey prompts, and conversational noise
    text = re.sub(r"(?i)would you like to talk to us\??\s*", "", text)
    text = re.sub(r"(?i)we'?d like to hear from you\.?\s*", "", text)
    text = re.sub(r"(?i)thank you for your feedback!?\s*", "", text)
    text = re.sub(r"(?i)was this information helpful\??\s*", "", text)
    text = re.sub(r"(?i)^(?:yes|no)(?:\s+(?:yes|no))*\s*$", "", text, flags=re.MULTILINE)

    # 3. Remove Userway / accessibility spinners and decorative images
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

    # 4. Strip UI noise and navigation counters
    text = strip_ui_noise_and_counters(text)

    # 5. Clean empty table pipe rows
    text = strip_empty_table_pipes(text)

    # 6. Clean excessive whitespace and empty lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def clean_scraped_markdown(raw_markdown: str, convert_tables: bool = False) -> str:
    """Perform full sanitization pipeline on scraped page content."""
    if not raw_markdown:
        return ""
    cleaned = strip_boilerplate(raw_markdown)
    if convert_tables:
        cleaned = convert_tables_to_prose(cleaned)
    return cleaned


# Aliases for backwards compatibility and readability
clean_page_content = clean_scraped_markdown
clean_markdown = clean_scraped_markdown

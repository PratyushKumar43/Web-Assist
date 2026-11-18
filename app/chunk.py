"""Heading-aware contextual text chunker for RAG pipeline."""

import hashlib
import re
from typing import Any, Dict, List, Optional
from app.clean import clean_page_content


def estimate_tokens(text: str) -> int:
    """Fast approximation of token count based on whitespace and punctuation."""
    return max(1, len(re.findall(r"\w+|[^\w\s]", text)))


def split_into_heading_sections(markdown: str) -> List[Dict[str, str]]:
    """Split markdown document into logical sections defined by ATX headings."""
    lines = markdown.splitlines()
    sections: List[Dict[str, str]] = []
    current_heading = "Overview"
    current_lines: List[str] = []

    for line in lines:
        match = re.match(r"^(#{1,4})\s+(.+)$", line)
        if match:
            # If we already have lines accumulated, close the section
            if current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append({"section": current_heading, "content": content})
                current_lines = []
            current_heading = match.group(2).strip()
        else:
            current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append({"section": current_heading, "content": content})

    return sections


def chunk_document(
    page: Dict[str, Any],
    product_meta: Optional[Dict[str, Any]] = None,
    max_tokens: int = 500,
    overlap_tokens: int = 50,
) -> List[Dict[str, Any]]:
    """Generate heading-aware chunks with prepended product context breadcrumbs."""
    raw_markdown = page.get("markdown", "")
    clean_md = clean_page_content(raw_markdown)
    if not clean_md:
        return []

    url = page.get("url", "")
    title = page.get("title", "")
    crawled_at = page.get("crawled_at", "")

    product_name = product_meta.get("name", title.split("|")[0].strip()) if product_meta else title.split("|")[0].strip()
    product_id = product_meta.get("product_id", "") if product_meta else ""
    category = product_meta.get("category", "General") if product_meta else "General"
    entity_id = product_meta.get("entity_id", product_id) if product_meta else product_id
    parent_id = product_meta.get("parent_id", "") if product_meta else ""
    governing_kfs = product_meta.get("governing_kfs", "") if product_meta else ""
    relations = product_meta.get("relations", {}) if product_meta else {}

    sections = split_into_heading_sections(clean_md)
    chunks: List[Dict[str, Any]] = []
    chunk_idx = 0

    for sec in sections:
        sec_title = sec["section"]
        sec_content = sec["content"]

        # If section is small, keep it as a single chunk
        if estimate_tokens(sec_content) <= max_tokens:
            chunk_text = f"Product: {product_name} > {sec_title}\n\n{sec_content}"
            chunk_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()[:16]
            chunk_id = f"{product_id or 'doc'}-{chunk_idx}"
            chunks.append({
                "chunk_id": chunk_id,
                "chunk_index": chunk_idx,
                "product_id": product_id,
                "product_name": product_name,
                "entity_id": entity_id,
                "parent_id": parent_id,
                "governing_kfs": governing_kfs,
                "relations": relations,
                "category": category,
                "section_path": sec_title,
                "url": url,
                "title": title,
                "crawled_at": crawled_at,
                "content_hash": chunk_hash,
                "text": chunk_text,
            })
            chunk_idx += 1
        else:
            # Check if section contains a table; keep tables intact
            paragraphs = re.split(r"\n\n+", sec_content)
            accumulated: List[str] = []
            curr_tokens = 0

            for p in paragraphs:
                p_tokens = estimate_tokens(p)
                if curr_tokens + p_tokens > max_tokens and accumulated:
                    combined = "\n\n".join(accumulated).strip()
                    chunk_text = f"Product: {product_name} > {sec_title}\n\n{combined}"
                    chunk_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()[:16]
                    chunk_id = f"{product_id or 'doc'}-{chunk_idx}"
                    chunks.append({
                        "chunk_id": chunk_id,
                        "chunk_index": chunk_idx,
                        "product_id": product_id,
                        "product_name": product_name,
                        "entity_id": entity_id,
                        "parent_id": parent_id,
                        "governing_kfs": governing_kfs,
                        "relations": relations,
                        "category": category,
                        "section_path": sec_title,
                        "url": url,
                        "title": title,
                        "crawled_at": crawled_at,
                        "content_hash": chunk_hash,
                        "text": chunk_text,
                    })
                    chunk_idx += 1
                    accumulated = [p]
                    curr_tokens = p_tokens
                else:
                    accumulated.append(p)
                    curr_tokens += p_tokens

            if accumulated:
                combined = "\n\n".join(accumulated).strip()
                chunk_text = f"Product: {product_name} > {sec_title}\n\n{combined}"
                chunk_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()[:16]
                chunk_id = f"{product_id or 'doc'}-{chunk_idx}"
                chunks.append({
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_idx,
                    "product_id": product_id,
                    "product_name": product_name,
                    "entity_id": entity_id,
                    "parent_id": parent_id,
                    "governing_kfs": governing_kfs,
                    "relations": relations,
                    "category": category,
                    "section_path": sec_title,
                    "url": url,
                    "title": title,
                    "crawled_at": crawled_at,
                    "content_hash": chunk_hash,
                    "text": chunk_text,
                })
                chunk_idx += 1

    return chunks

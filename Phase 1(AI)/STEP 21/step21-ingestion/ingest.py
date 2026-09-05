"""Document ingestion: raw file -> clean, deduplicated, metadata-carrying chunks.

The reusable logic is the pipeline (clean, dedupe, parse, reingest). Extraction
itself is delegated to an `extractor` callable so you can plug in Docling for
layout-aware parsing without the rest of the pipeline caring which backend runs.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# The structured record. Metadata rides alongside text, never as a bare string.
# ---------------------------------------------------------------------------

@dataclass
class DocumentChunk:
    text: str
    source: str
    page: int
    section: str | None = None
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = hash_text(self.text)


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Cleaning: normalize so text becomes comparable, THEN dedupe.
# ---------------------------------------------------------------------------

def clean(text: str) -> str:
    """Normalize whitespace and strip invisible characters that break dedupe."""
    text = text.replace("\u00a0", " ")              # non-breaking space
    text = re.sub(r"[\u200b\u200c\u200d]", "", text)  # zero-width chars
    text = re.sub(r"\x00", "", text)                 # null bytes from bad PDFs
    text = re.sub(r"\s+", " ", text)                 # collapse all whitespace
    return text.strip()


# ---------------------------------------------------------------------------
# Deduplication: exact-hash first; MinHash is the upgrade when you see
# redundant retrieval results.
# ---------------------------------------------------------------------------

def dedupe(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
    """Drop byte-identical chunks by content_hash, keeping first occurrence."""
    seen: set[str] = set()
    out: list[DocumentChunk] = []
    for chunk in chunks:
        if chunk.content_hash in seen:
            continue
        seen.add(chunk.content_hash)
        out.append(chunk)
    return out


# ---------------------------------------------------------------------------
# Extraction. `extractor(path) -> list[PageText]` where PageText is
# (page_number, markdown_text). Default is PyMuPDF; swap in Docling for
# layout-aware parsing in production.
# ---------------------------------------------------------------------------

def extract_pymupdf(path: str) -> list[tuple[int, str]]:
    """Default extractor: text layer per page using PyMuPDF.

    Fine for single-column born-digital PDFs. For multi-column/table-heavy
    documents, replace this with Docling's DocumentConverter and export to
    Markdown so layout and table structure survive.
    """
    import fitz  # PyMuPDF

    pages = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            pages.append((i, page.get_text()))
    return pages


def parse(path: str, extractor=None) -> list[DocumentChunk]:
    """Extract, clean, and attach metadata to each page's text."""
    extractor = extractor or extract_pymupdf
    source = path.split("/")[-1].split("\\")[-1]
    chunks: list[DocumentChunk] = []

    for page_num, raw in extractor(path):
        text = clean(raw)
        if not text:
            continue
        chunks.append(
            DocumentChunk(
                text=text,
                source=source,
                page=page_num,
                section=None,  # set from heading structure in the Docling path
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# Incremental re-ingestion: content hash decides what to re-process.
# ---------------------------------------------------------------------------

def file_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def reingest(
    path: str,
    state: dict[str, str],
    extractor=None,
) -> tuple[int, int, str | None]:
    """Process one file idempotently.

    Returns (added, skipped, old_hash_to_delete):
      - added: chunks produced because the file is new or changed
      - skipped: 0 or 1, whether the file was unchanged and left alone
      - old_hash: the previous hash to delete old chunks by, if it changed
    """
    new_hash = file_hash(path)
    old_hash = state.get(path)

    if old_hash == new_hash:
        return 0, 1, None

    chunks = parse(path, extractor=extractor)
    chunks = dedupe(chunks)
    state[path] = new_hash
    return len(chunks), 0, old_hash

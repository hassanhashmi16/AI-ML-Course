"""Split documents into stable, source-mapped chunks.

Chunks are the retrieval unit; the stored ``SourceRecord`` stays the
authority. Every chunk keeps its source's identity plus an exact position in
the original text (character offsets and line numbers), and a ``chunk_id``
derived from ``(source_id, start, end)`` -- so re-splitting a record yields
the same IDs and indexing stays idempotent.

Files whose extension says what they are get the language-aware splitter
(Python definitions/classes stay near their boundaries); discussions,
commits, and everything else use the generic recursive splitter.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

# ~1200 characters per chunk with mild overlap. These live here (and get
# recorded in the index manifest at Step 7) rather than in config: changing
# them changes every chunk ID, so it must be a deliberate index rebuild.
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150

_LANGUAGE_BY_SUFFIX = {
    ".py": Language.PYTHON,
    ".md": Language.MARKDOWN,
}


def _splitter_for(metadata: dict) -> RecursiveCharacterTextSplitter:
    """Language-aware splitter for known file types, generic otherwise."""
    if metadata.get("kind") == "file":
        suffix = Path(str(metadata.get("title", ""))).suffix.lower()
        language = _LANGUAGE_BY_SUFFIX.get(suffix)
        if language is not None:
            return RecursiveCharacterTextSplitter.from_language(
                language=language,
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP,
                add_start_index=True,
            )
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        add_start_index=True,
    )


def _line_number(line_starts: list[int], offset: int) -> int:
    """1-based line number of a character offset in the original text."""
    return bisect_right(line_starts, offset)


def split_document(document: Document) -> list[Document]:
    """One full-text document -> chunks, each with exact position metadata."""
    text = document.page_content
    # add_start_index makes the splitter record each piece's character offset
    # in the source, which is what lets a chunk be checked against the record.
    pieces = _splitter_for(document.metadata).create_documents([text], metadatas=[{}])
    # Precompute where every line begins so offsets convert to line numbers
    # in O(log n) instead of rescanning the text per chunk.
    line_starts = [0] + [index + 1 for index, char in enumerate(text) if char == "\n"]

    chunks: list[Document] = []
    for position, piece in enumerate(pieces):
        start = int(piece.metadata.get("start_index", 0))
        content = piece.page_content
        end = start + len(content)
        chunk_metadata = {
            **document.metadata,  # the source identity travels with every chunk
            "chunk_id": f"{document.metadata['source_id']}#{start}-{end}",
            "chunk_index": position,
            "start_index": start,
            "end_index": end,
            "start_line": _line_number(line_starts, start),
            "end_line": _line_number(line_starts, max(start, end - 1)),
        }
        chunks.append(Document(page_content=content, metadata=chunk_metadata))
    return chunks


def split_documents(documents: Iterable[Document]) -> list[Document]:
    """Split many documents, preserving input order."""
    chunks: list[Document] = []
    for document in documents:
        chunks.extend(split_document(document))
    return chunks

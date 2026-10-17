"""Source records -> LangChain Documents.

A ``Document`` is the interchange format the retrieval stack speaks
(splitters, embeddings, Qdrant). One retained ``SourceRecord`` becomes one
Document: the text is the full source, and the metadata carries the identity
that lets any retrieved passage be traced back -- source_id, kind,
repository, snapshot, URL, and whatever else the record retained.

Metadata values stay JSON-friendly (strings, ints) because the vector store
will hold them as payload later.
"""

from __future__ import annotations

from collections.abc import Iterable

from langchain_core.documents import Document

from models import SourceRecord


def record_metadata(record: SourceRecord) -> dict[str, str | int | bool]:
    """The traceable identity of a record, flattened for document metadata."""
    metadata: dict[str, str | int | bool] = {
        "source_id": record.source_id,
        "kind": record.kind.value,
        "repository": record.repository,
        "snapshot_sha": record.snapshot_sha,
        "url": record.url,
    }
    # Optional fields are included only when present: a missing author is
    # absent, not the text "None".
    if record.title:
        metadata["title"] = record.title
    if record.author:
        metadata["author"] = record.author
    if record.state:
        metadata["state"] = record.state
    if record.source_date is not None:
        metadata["source_date"] = record.source_date.isoformat()
    if record.content_revision:
        metadata["content_revision"] = record.content_revision
    return metadata


def to_document(record: SourceRecord) -> Document:
    """One retained record -> one full-text document."""
    return Document(page_content=record.content, metadata=record_metadata(record))


def to_documents(records: Iterable[SourceRecord]) -> list[Document]:
    """Many records -> many documents, preserving input order."""
    return [to_document(record) for record in records]

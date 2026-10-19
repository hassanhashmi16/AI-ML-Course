"""Evidence search over the local index: dense or hybrid, always scope-filtered.

The scope filter (repository + snapshot SHA) is applied in **every** mode.
Collection naming already separates snapshots, and the filter makes it
impossible for a stray point from another repository or revision to surface
even if one were indexed into the wrong collection.

Retrieval is deliberately wide (``RETRIEVE_K`` candidates); narrowing is the
reranker's job (``retrieval/rerank.py``), mirroring Project 2's
"retrieve wide, rerank narrow".
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from config import settings
from models import RepoSnapshot
from retrieval.clients import build_vector_store, collection_name


def scope_filter(snapshot: RepoSnapshot, source_ids: list[str] | None = None) -> Filter:
    """Restrict any search to this repository@snapshot.

    ``source_ids`` narrows it further to the evidence this investigation has
    actually inspected -- so an answer can never cite a chunk from an earlier
    run that this run never collected, even though the index is shared.
    """
    conditions = [
        FieldCondition(
            key="metadata.repository", match=MatchValue(value=snapshot.repository)
        ),
        FieldCondition(key="metadata.snapshot_sha", match=MatchValue(value=snapshot.sha)),
    ]
    if source_ids:
        conditions.append(
            FieldCondition(
                key="metadata.source_id", match=MatchAny(any=list(source_ids))
            )
        )
    return Filter(must=conditions)


def search_evidence(
    client: QdrantClient,
    embeddings: Embeddings,
    sparse_embedding,
    snapshot: RepoSnapshot,
    query: str,
    *,
    mode: str = "hybrid",
    k: int | None = None,
    source_ids: list[str] | None = None,
) -> tuple[list[Document], str | None]:
    """Top-k candidate chunks for a query, with scores attached; warns if unrunnable.

    A missing collection is a *visible* condition, not an empty result: the
    caller gets a warning explaining how to build the index.
    """
    cap = k if k is not None else settings.retrieve_k
    collection = collection_name(snapshot)
    if not client.collection_exists(collection):
        return [], (
            f"collection not found for {snapshot.sha[:7]}; "
            "run: python -m ingest.index --repo <url> --ref <ref>"
        )
    store = build_vector_store(
        client,
        embeddings,
        collection,
        sparse_embedding=sparse_embedding if mode == "hybrid" else None,
        mode=mode,
    )
    results = store.similarity_search_with_score(
        query, k=cap, filter=scope_filter(snapshot, source_ids)
    )
    documents: list[Document] = []
    for document, score in results:
        # Cheap provenance for debugging: how strongly this candidate scored.
        document.metadata["retrieval_score"] = round(float(score), 4)
        documents.append(document)
    return documents, None

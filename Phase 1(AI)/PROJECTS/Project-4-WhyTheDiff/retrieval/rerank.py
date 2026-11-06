"""Candidate reranking: local cross-encoder by default, Cohere optional.

Reranking is a *labelled* step. When it is disabled or fails, the retrieval
order is kept and the reason travels back with the result -- an unranked list
must never look like a ranked one.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.documents import Document

from config import settings
from retrieval.clients import FASTEMBED_CACHE


@lru_cache(maxsize=1)
def _cross_encoder():
    """The local reranker, loaded once (weights download on first use)."""
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(
        model_name=settings.fastembed_rerank_model,
        cache_dir=str(FASTEMBED_CACHE),
    )


def rerank_documents(
    query: str,
    documents: list[Document],
    *,
    top_k: int | None = None,
    provider: str | None = None,
) -> tuple[list[Document], str | None]:
    """Reorder candidates by relevance; returns (kept, warning).

    ``provider`` overrides ``RERANK_PROVIDER`` for this call (used by the
    check to exercise the disabled and failed paths).
    """
    cap = top_k if top_k is not None else settings.rerank_k
    if not documents:
        return [], None

    chosen = provider if provider is not None else settings.rerank_provider
    if chosen == "none":
        return documents[:cap], "reranking disabled (RERANK_PROVIDER=none); retrieval order kept"

    try:
        if chosen == "cohere":
            from langchain_cohere import CohereRerank

            api_key = settings.cohere_api_key.get_secret_value()
            if not api_key:
                raise ValueError("COHERE_API_KEY is empty")
            compressor = CohereRerank(
                model=settings.rerank_model, cohere_api_key=api_key, top_n=cap
            )
            return list(compressor.compress_documents(documents, query)), None

        encoder = _cross_encoder()
        scores = [
            float(score)
            for score in encoder.rerank(query, [doc.page_content for doc in documents])
        ]
        ranked = sorted(zip(documents, scores), key=lambda pair: pair[1], reverse=True)
        kept: list[Document] = []
        for document, score in ranked[:cap]:
            document.metadata["rerank_score"] = round(score, 4)
            kept.append(document)
        return kept, None
    except Exception as exc:  # reranking must fail softly and visibly
        return documents[:cap], f"reranking failed ({exc}); retrieval order kept"

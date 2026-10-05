"""Step 11 deliverable (part 1): the cross-encoder reranker.

Input:  the user's question + a list of candidate chunks (from fusion).
Output: the SAME chunks, reordered by true relevance, trimmed to the best few.

Why a second scoring pass exists at all:

  * A retriever's embedding is a **bi-encoder**: it embeds the query and each
    passage SEPARATELY, then compares the vectors. That is what makes it fast
    enough to search 252 chunks, but it never actually reads the query and the
    passage together, so it is coarse.
  * A **cross-encoder** reads the query and the passage TOGETHER and outputs a
    single relevance score. Far more accurate, far too slow to run over the whole
    corpus. So we run it only on the handful of candidates the retriever already
    surfaced.

That is the "retrieve wide, rerank narrow" split, and it is the single biggest
quality lever in the pipeline.

This file does not embed anything; it delegates to a hosted cross-encoder
(Cohere Rerank). Keep this function's signature stable - the rest of the codebase
only cares that it takes (query, candidates, top_k) and returns reordered chunks.
"""
from __future__ import annotations

import time

import cohere

from config import COHERE_API_KEY, COHERE_RERANK_MODEL, RERANK_K
from retrieval.results import Retrieved

# The .env.example template value. Treated as "not configured" so the error
# message is helpful instead of a confusing 401 from the API.
_PLACEHOLDER = "your_cohere_key_here"

# The trial key allows only 10 rerank calls a minute, so a 429 here means "wait a
# moment", not "give up". Four attempts with a doubling delay ride that out.
_MAX_ATTEMPTS = 4


def rerank(
    query: str,
    candidates: list[Retrieved],
    top_k: int = RERANK_K,
) -> list[Retrieved]:
    """Reorder `candidates` by how well each answers `query`, keep the best top_k.

    `query` is the user's ORIGINAL question, not a rewritten one: rewriting is for
    recall during retrieval; the final ordering should match what the user meant.
    """
    if not candidates:
        return []

    if not COHERE_API_KEY or COHERE_API_KEY == _PLACEHOLDER:
        raise RuntimeError(
            "COHERE_API_KEY is not set. Get a free key at cohere.com, add it to .env, "
            "then re-run."
        )

    client = cohere.ClientV2(api_key=COHERE_API_KEY)
    delay = 6.0
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = client.rerank(
                model=COHERE_RERANK_MODEL,
                query=query,
                documents=[candidate.content for candidate in candidates],
                top_n=top_k,
            )
            break
        except Exception as exc:  # noqa: BLE001 - re-raised unless rate limited
            if attempt == _MAX_ATTEMPTS or getattr(exc, "status_code", None) != 429:
                raise
            time.sleep(delay)
            delay *= 2

    # `result.index` points back into the ORIGINAL candidate list, so we map it to
    # the Retrieved object and overwrite its score with the cross-encoder's
    # relevance score (now a real 0..1 relevance, not the retriever's score).
    reranked: list[Retrieved] = []
    for result in response.results:
        item = candidates[result.index]
        item.score = float(result.relevance_score)
        reranked.append(item)
    return reranked

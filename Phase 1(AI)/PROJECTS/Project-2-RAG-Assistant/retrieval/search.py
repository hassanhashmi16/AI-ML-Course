"""Step 11 deliverable (part 2): hybrid search - the full retrieval pipeline.

    question
      -> rewrite (Step 10)              : the original question + 1-2 rewrites
      -> dense + sparse for each query  : many ranked lists of chunk ids
      -> reciprocal rank fusion         : one fused ranking
      -> rerank (rerank.py)             : the final, best few
      -> top-k chunks

Input:  the user's question.
Output: the k chunks that should be handed to the model (Step 13).

The key idea is in the fusion step. Dense and sparse produce scores on completely
incomparable scales (cosine similarity ~0.7, text rank ~0.02), so adding them
together would let one retriever always drown out the other. **Reciprocal Rank
Fusion uses only the RANK, never the score.** A chunk that is 1st in either list
gets a big contribution; a chunk that appears high in BOTH lists wins outright.
That is what makes two very different retrievers combinable.
"""
from __future__ import annotations

from config import RERANK_K, RETRIEVE_K
from ingest.store import connect
from retrieval.dense import dense_search
from retrieval.rerank import rerank
from retrieval.results import Retrieved
from retrieval.rewrite import rewrite_query
from retrieval.sparse import sparse_search

# The RRF constant from the original paper. It damps the influence of top ranks so
# one retriever's #1 does not totally dominate; 60 is the standard default.
RRF_K = 60


def reciprocal_rank_fusion(ranked_lists: list[list[int]], k: int = RRF_K) -> list[int]:
    """Fuse several ranked lists of chunk ids into one ranking.

    Each list contributes 1/(k + rank) to every id it contains. Ids on multiple
    lists accumulate more, so agreement between retrievers is rewarded.
    """
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda chunk_id: -scores[chunk_id])


def hybrid_search(
    question: str,
    k: int = RERANK_K,
    peak: str | None = None,
    use_rerank: bool = True,
) -> list[Retrieved]:
    """Full retrieval: rewrite -> hybrid retrieve -> fuse -> (rerank) -> top k."""
    queries = rewrite_query(question)

    conn = connect()
    ranked_lists: list[list[int]] = []
    by_id: dict[int, Retrieved] = {}
    try:
        for query in queries:
            for retriever in (dense_search, sparse_search):
                results = retriever(query, k=RETRIEVE_K, peak=peak, conn=conn)
                ranked_lists.append([result.chunk_id for result in results])
                for result in results:
                    # Keep the first version of a chunk we see (dense or sparse);
                    # fusion only uses ids, so the stored score is irrelevant here.
                    by_id.setdefault(result.chunk_id, result)
    finally:
        conn.close()

    fused = reciprocal_rank_fusion(ranked_lists)
    # Retrieve wide, rerank narrow: cap the candidates before the (slower) rerank.
    candidates = [by_id[chunk_id] for chunk_id in fused[:RETRIEVE_K]]

    if use_rerank:
        return rerank(question, candidates, top_k=k)
    return candidates[:k]


def main() -> None:
    """Compare naive dense search against hybrid (RRF) retrieval."""
    from console import make_stdout_safe

    make_stdout_safe()

    questions = [
        "how difficult is K2 compared to Everest?",
        "is Savage Mountain harder than Everest?",
        "who first climbed the killer mountain?",
    ]

    for question in questions:
        print(f"\nquestion: {question}")

        print("  naive (dense only, top 5):")
        for result in dense_search(question, k=5):
            print(f"    {result.label()}")

        print("  hybrid (rewrite + RRF, top 5):")
        for result in hybrid_search(question, k=5, use_rerank=False):
            print(f"    {result.label()}")

        print("  hybrid + rerank (top 5):")
        for result in hybrid_search(question, k=5, use_rerank=True):
            print(f"    {result.score:.3f}  {result.label()}")


if __name__ == "__main__":
    main()

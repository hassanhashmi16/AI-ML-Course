"""Step 16 deliverable: measure retrieval three ways, on labelled questions.

    python -m eval.run_eval

Output: recall@k, MRR and nDCG for
  1. naive  - dense (embedding) search only
  2. hybrid - dense + keyword, fused with RRF
  3. hybrid + rerank - the same, then reordered by the cross-encoder

Ground truth is a list of (source file, section) pairs per question, taken from the
corpus itself.

Why the rewrite (Step 10) is NOT used here:
  * it is a generation call, and generation has a small daily quota;
  * the model is not perfectly deterministic even at temperature 0, so including it
    would make two runs incomparable.
This measures RETRIEVAL, which needs no LLM at all.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from config import RERANK_K
from console import make_stdout_safe
from ingest.store import connect
from retrieval.dense import dense_search
from retrieval.rerank import rerank
from retrieval.search import reciprocal_rank_fusion
from retrieval.sparse import sparse_search

QUESTIONS = Path(__file__).parent / "questions.jsonl"
K = 5  # cut-off for the metrics
WIDE = 20  # candidates each retriever contributes before fusion / rerank


def recall_at_k(retrieved, relevant, k=K):
    """Fraction of the relevant passages that made it into the top k."""
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def mrr(retrieved, relevant, k=K):
    """1 / rank of the first relevant result (higher = the right thing came first)."""
    for rank, item in enumerate(retrieved[:k], start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def ndcg(retrieved, relevant, k=K):
    """Discounted gain, normalised against the best possible ordering.

    Several chunks share one (source, section), so each relevant pair is counted
    once, at the rank where it first appears. Counting every position would let the
    score climb above 1.
    """
    seen = set()
    dcg = 0.0
    for rank, item in enumerate(retrieved[:k]):
        if item in relevant and item not in seen:
            seen.add(item)
            dcg += 1.0 / math.log2(rank + 2)
    ideal = sum(1.0 / math.log2(rank + 2) for rank in range(min(len(relevant), k)))
    return dcg / ideal if ideal else 0.0


def _fused_candidates(conn, question):
    """Dense + keyword, fused into one ranking (retrieve wide)."""
    dense = dense_search(question, k=WIDE, conn=conn)
    sparse = sparse_search(question, k=WIDE, conn=conn)
    fused_ids = reciprocal_rank_fusion(
        [[result.chunk_id for result in dense], [result.chunk_id for result in sparse]]
    )
    by_id = {result.chunk_id: result for result in dense}
    for result in sparse:
        by_id.setdefault(result.chunk_id, result)
    return [by_id[chunk_id] for chunk_id in fused_ids]


def _hits(results):
    """Turn results into (source, section) pairs, the ground-truth vocabulary."""
    return [(result.source, result.section) for result in results]


def evaluate(name, retrieve, conn, questions):
    recalls, mrrs, ndcgs = [], [], []
    for item in questions:
        relevant = {tuple(pair) for pair in item["relevant"]}
        hits = _hits(retrieve(conn, item["question"]))
        recalls.append(recall_at_k(hits, relevant))
        mrrs.append(mrr(hits, relevant))
        ndcgs.append(ndcg(hits, relevant))
    n = len(questions)
    print(
        f"{name:<20} recall@{K}={sum(recalls) / n:.2f}   "
        f"MRR={sum(mrrs) / n:.2f}   nDCG={sum(ndcgs) / n:.2f}"
    )


def main() -> None:
    make_stdout_safe()

    questions = [
        json.loads(line)
        for line in QUESTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    conn = connect()
    try:
        # Sanity-check the hand-written labels against the real corpus, so a typo
        # shows up as a warning instead of quietly deflating every score.
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.source, c.section FROM chunks c "
                "JOIN documents d ON d.id = c.document_id"
            )
            known = {(source, section) for source, section in cur.fetchall()}
        for item in questions:
            for pair in item["relevant"]:
                if tuple(pair) not in known:
                    print(f"WARNING: label not in corpus: {pair}  ({item['question']})")

        print(f"\n{len(questions)} questions, K={K}\n")
        evaluate("naive (dense)", lambda c, q: dense_search(q, k=K, conn=c), conn, questions)
        evaluate("hybrid (RRF)", lambda c, q: _fused_candidates(c, q)[:K], conn, questions)
        evaluate(
            "hybrid + rerank",
            lambda c, q: rerank(q, _fused_candidates(c, q)[:WIDE], top_k=K),
            conn,
            questions,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()

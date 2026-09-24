"""Step 25 deliverable: measure the recall/latency trade of ANN vs exact search.

Run it with:

    pip install numpy hnswlib
    python ann_bench.py

What it shows (the core idea of Step 25.1): exact search returns the *true*
nearest neighbors but costs O(n); an HNSW index returns them fast but sometimes
misses. We quantify the miss as recall@10, and watch recall go UP while
latency also goes UP as we raise `ef_search` — the recall/latency dial.
"""
import time

import numpy as np  # for generating vectors and doing the brute-force search

try:
    import hnswlib  # the HNSW ANN library we benchmark against
except ImportError:
    raise SystemExit("hnswlib not installed. Run: pip install hnswlib")


# Experiment size. N = corpus size, DIM = vector dimensions, K = top-k.
N, DIM, K = 20000, 64, 10
NQ = 100  # number of queries to average over

# Random vectors in [0,1). Real embeddings are never random like this, but for
# measuring the *index* (not the embedding model), random data is a fine,
# dependency-free stand-in.
rng = np.random.default_rng(0)  # fixed seed → reproducible results
data = rng.random((N, DIM), dtype=np.float32)
queries = rng.random((NQ, DIM), dtype=np.float32)


def exact_topk(q):
    """Brute-force exact search: distance to EVERY vector, then sort.

    This is our ground truth. It has 100% recall because it literally
    compares q against the whole corpus — the thing ANN is trying to avoid.
    """
    # L2 distance of q to every row, computed in one vectorized numpy op.
    dist = np.linalg.norm(data - q, axis=1)
    return np.argsort(dist)[:K]  # indices of the K smallest distances


def build_index(ef_construction=200, M=16):
    """Build an HNSW index over the corpus.

    - `M` = edges per node (build-time knob; more = better recall, more memory).
    - `ef_construction` = how thorough the graph build is (more = better
      recall, slower build). These are baked in at build time.
    """
    idx = hnswlib.Index(space="l2", dim=DIM)  # we search by L2 distance here
    idx.init_index(max_elements=N, ef_construction=ef_construction, M=M)
    idx.add_items(data)  # insert every vector into the graph
    return idx


def main():
    # --- Ground truth: exact brute-force search over all 100 queries ---
    t0 = time.perf_counter()  # start the stopwatch
    truth = np.stack([exact_topk(q) for q in queries])  # true top-K per query
    exact_ms = (time.perf_counter() - t0) / NQ * 1000  # average ms per query
    print(f"exact (brute force):      {exact_ms:.2f} ms/query, recall 100%")

    # --- Approximate: same HNSW index, but raise ef_search each round ---
    idx = build_index()
    for ef in (10, 40, 100, 200):
        idx.set_ef(ef)  # QUERY-TIME knob: how hard each search looks
        t0 = time.perf_counter()
        labels, _ = idx.knn_query(queries, k=K)  # run the ANN search
        approx_ms = (time.perf_counter() - t0) / NQ * 1000

        # recall@K: for each query, how many of the TRUE top-K did we return?
        # set(a) & set(b) = overlap between approximate and exact result sets.
        recall = np.mean([len(set(a) & set(b)) / K for a, b in zip(labels, truth)])
        print(f"HNSW ef_search={ef:>3}:  {approx_ms:6.2f} ms/query, recall@{K} = {recall:.3f}")


if __name__ == "__main__":
    main()

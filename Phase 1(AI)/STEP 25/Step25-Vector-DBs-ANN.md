# Step 25: Vector Databases & ANN Indexing

> **Covers:** exact vs approximate nearest-neighbor search, how HNSW / IVF / quantized indexes work, the tuning knobs, metadata filtering and multi-tenancy, store selection, and scaling. This generalizes pgvector (Step 24) into the full field of vector search.

---

## The Problem

Step 24's exact search compares your query against *every* vector — correct, but O(n). At ten million vectors that's too slow to serve a live request. Approximate indexes fix this by visiting only a *fraction* of the data, getting sub-10ms responses — but they do it by occasionally *missing* a correct result. So the real skill isn't "make search fast," it's understanding exactly what you traded away (recall) and how to tune that trade. If you don't, you end up with a fast vector store that silently returns the wrong things.

---

## Foundational Concepts

### Nearest-neighbor search is the whole game

Given a query vector `q`, nearest-neighbor search (NNS) means "return the vectors closest to `q` under some distance." The two families:

- **Exact search** = brute force. Compute the distance to *every* vector, sort, take the top-k. Perfect recall, but O(n·d) per query — the cost grows with every vector you store.
- **Approximate NNS (ANN)** = use an index to look at only a *promising subset*. Sub-linear, but recall drops below 100%.

### Recall@k is the number that matters

**Recall@k** = "of the true top-k nearest neighbors, what fraction did my approximate search actually return?" If brute force finds neighbors {A, B, C} and your ANN returns {A, B, D}, recall@3 is 2/3. This single number is how you judge an ANN index: *fast* is meaningless until you know the recall next to it. Every ANN benchmark measures recall against brute-force ground truth.

---

## 25.1 — Exact vs approximate: the recall/latency trade

| | Exact (brute force) | Approximate (indexed) |
|---|---|---|
| Recall | 100% | 90–99%+ (tunable) |
| Query cost | O(n·d) | roughly O(log n) |
| Memory | just the vectors | vectors + index structure |
| When | small corpora, offline, ground truth | production search |

**The trade, stated plainly:** you are *choosing* to miss some correct results in exchange for speed. The tuning knobs in 25.3 are just dials that move you along that line — more recall costs more time or memory. There's no free lunch; there's only deciding where on the line you want to sit, and measuring that you're actually there.

---

## 25.2 — How the indexes work

### HNSW (Hierarchical Navigable Small World)

HNSW is a **multi-layer graph**. Each vector is a node, and edges connect a node to its nearest neighbors. The clever part is the layers:

```
layer 2:  ●────●              sparse, few long-range links
layer 1:  ●──●──●──●          denser
layer 0:  ●─●─●─●─●─●─●      dense, short-range links (all nodes live here)
```

- **Build:** each vector is inserted and linked to its `M` nearest neighbors; a fraction of nodes also get promoted to upper layers, giving a "highway system" of long jumps.
- **Search:** start at a random entry point in the *top* layer, greedily step toward whichever neighbor is closest to the query, then drop down a layer and repeat. By the bottom layer you've zoomed into the right neighborhood and only need to check locally.

The intuition: it's like searching a city. Upper layers are the highway map (get to the right district fast), bottom layer is the street map (find the exact house). You never inspect the whole city.

**Why HNSW dominates:** it has the best speed/recall tradeoff in practice and needs no training step (unlike IVF). Its costs are memory (all those edges) and slow-ish build time. It's the default in pgvector, Qdrant, Weaviate, and most engines — "how does my vector DB search" almost always means HNSW.

### IVF (Inverted File)

IVF takes a different approach: **divide first, then search a subset.**

- **Build:** run k-means to cluster all vectors into `nlist` groups, each with a centroid. Every vector is assigned to its nearest centroid.
- **Search:** compute the distance from the query to all `nlist` centroids, then only look inside the `nprobe` closest clusters, brute-forcing within them.

The intuition: you're skipping most of the corpus by checking only the clusters whose centers are near your query. Recall depends on `nprobe` — probe more clusters, find more of the true neighbors, spend more time.

**Why IVF matters:** it uses far less memory than HNSW (no dense graph) and scales to billions of vectors, but at equal recall it's usually slower. It's the classic choice in Faiss for very large indexes.

### Quantized indexes (PQ / binary)

Quantization answers a different question: **how do I shrink the vectors themselves so a huge index fits in RAM?** Floating-point vectors are 4 bytes per dimension, which adds up fast.

- **Product Quantization (PQ):** split each vector into sub-vectors, and replace each with the ID of its nearest "codebook" centroid. You store small *codes* instead of floats — a 8–32× memory reduction, at some recall cost (the codes are lossy).
- **Binary quantization:** keep only the *sign* of each dimension (`+`/`-` becomes one bit). Extremely small and fast (compare with Hamming distance), but very lossy — so it's usually a *first pass* to fetch candidates, followed by re-ranking with the full-precision vectors.

**Why this matters:** memory, not CPU, is usually the wall for vector search. Quantization is how you keep a 10M-vector index resident in RAM. (`halfvec` from Step 24 is the mild version; PQ and binary are the aggressive versions.)

---

## 25.3 — Tuning knobs and what they cost

| Knob | What it does | Raise it → | Lower it → |
|---|---|---|---|
| HNSW `M` | edges per node | better recall, more memory | less memory, lower recall |
| HNSW `ef_construction` | thoroughness at build time | better recall, slower build | faster build |
| HNSW `ef_search` | thoroughness at query time | better recall, slower query | faster query |
| IVF `nlist` | number of clusters | finer partitions (needs more probes) | coarser partitions |
| IVF `nprobe` | clusters scanned per query | better recall, slower query | faster query |

**The key distinction — when you can change them:**

- **Query-time knobs** (`ef_search`, `nprobe`) are cheap and reversible: you can raise them per-query to buy back recall without touching the index.
- **Build-time knobs** (`M`, `ef_construction`, `nlist`) are baked into the index; changing them means rebuilding, which is expensive on big data.

Rules of thumb to start from:

- IVF: `nlist ≈ sqrt(n)`, and `nprobe ≈ sqrt(nlist)`.
- Tune the query-time knob first; only rebuild when that isn't enough.
- If your recall is 80% and you don't know why, it's almost always an `ef_search`/`nprobe` problem.

---

## 25.4 — Metadata filtering, namespaces & multi-tenancy

Real search almost always mixes "semantically similar" with "but only these rows." That combination is where ANN indexes break down.

**The core problem:** an ANN index returns its approximate top-k *first*; the metadata filter is applied *after*. Two failure modes:

- **Pre-filter** (filter, then search the survivors) can miss results if the filter is strict — the true neighbors might have been filtered out.
- **Post-filter** (search, then filter) can under-return — the index's top-k may contain almost nothing that passes the filter.

Engines solve this in different ways: pgvector has **iterative index scans** (keep scanning until enough pass the filter), and Qdrant has a **filterable HNSW** (extra graph edges keyed on indexed payload values). The point isn't to memorize each — it's to know *filtered recall is a separate thing you must test*, not assume.

**Namespaces and tenants:**

- **Namespaces / collections / partitions** = logical walls that divide vectors so a search only touches one subset.
- **Multi-tenancy** = many customers sharing one index. The danger: one tenant's dense cluster of vectors can change which neighbors the graph connects, degrading *other* tenants' recall. Options: one index per tenant (cleanest, more memory), partition by tenant (pgvector), or a tenant field + filterable HNSW (Qdrant).

---

## 25.5 — Choosing a store

| | pgvector | Dedicated vector DB (Qdrant, Pinecone, Weaviate, Milvus) | Search engine (Elastic/OpenSearch) |
|---|---|---|---|
| Best for | You already use Postgres | Standalone vector search at scale | Hybrid text + vector over documents |
| Setup | One extension | A separate service to run and scale | A separate service |
| Strengths | One datastore, ACID, JOINs, filters | Best ANN, quantization, multi-tenancy, scale | BM25 (sparse) + dense in one query |
| Weaknesses | Recall/scale ceilings vs dedicated | A second system to operate | Vector ANN less mature |

Rules of thumb:

- **Start with pgvector** if you already run Postgres and have under ~10M vectors — the operational simplicity usually beats the benchmark-table gains.
- **Move to a dedicated vector DB** when you hit a *measured* limit in recall-at-scale, quantization, or distributed indexing.
- **Use a search engine** when BM25 / sparse retrieval matters as much as dense embeddings (which sets up Step 26's hybrid search).

The deeper point: **this is mostly an operational decision, not an accuracy one.** Don't add a second system until the one you have shows a concrete limit. The `store_decision.md` deliverable captures this as a checklist.

---

## 25.6 — Scale: sharding, memory, index rebuild

- **Memory is the binding constraint.** A vector index wants to live in RAM. `halfvec`, PQ, and binary quantization are how you shrink it before buying more machines.
- **Sharding** = splitting vectors across nodes (by key or hash). A search fans out to all shards and merges results; recall can drop if a query's true neighbors are spread across shards.
- **Index rebuild is expensive.** Building or rebuilding HNSW/IVF on a big corpus takes minutes to hours. Reindex offline, then swap the index in — never rebuild in place under live traffic.
- **Heavy churn degrades graph quality.** ANN indexes tolerate inserts, but constant deletes/updates fray the graph over time, so plan periodic rebuilds.

The takeaway: scaling a vector store is a *memory and rebuild-time* problem before it's a CPU problem.

---

## Pitfalls

1. **Tuning recall without measuring it.** "Fast" at 70% recall is worse than "slower" at 95%. Always benchmark ANN against brute-force ground truth.
2. **Assuming filtered search is exact.** Pre/post-filtering on an ANN index can silently drop valid matches. Test filtered recall separately.
3. **Mismatched `nlist`/`nprobe`.** Too many clusters with too few probes = terrible IVF recall.
4. **Building IVF on an empty table.** k-means has nothing to cluster; build it after data exists. (HNSW is exempt — it has no training step.)
5. **One shared index across tenants.** Tenant bleed degrades everyone's recall. Isolate tenants.
6. **Treating scale as "just more rows."** Memory and rebuild time grow super-linearly; plan quantization and sharding *before* you hit the wall.

---

## Quick Reference

| Concept | One-liner |
|---|---|
| Exact search | Brute force, 100% recall, O(n·d) |
| ANN | Index-guided, tunable recall, sub-linear |
| HNSW | Multi-layer proximity graph; the default |
| IVF | k-means clusters + probe nearest lists |
| PQ / binary quantization | Compress vectors to fit memory |
| `ef_search` / `nprobe` | Query-time recall dial (cheap) |
| `M` / `ef_construction` / `nlist` | Build-time recall/memory dial (needs rebuild) |
| Filterable HNSW | Extra edges so filters don't kill recall |
| Recall@k | Fraction of true top-k you actually returned |

---

## Theory Summary

- **ANN is a controlled recall trade, not free speed.** You are choosing to miss some results; the discipline is knowing how many and why.
- **Every index is a dial** between recall, latency, memory, and build time — and the dials split into *query-time* (cheap, reversible) and *build-time* (expensive, needs rebuild).
- **The store is usually an operational decision.** Start simple (pgvector) and escalate only on a measured limit.
- **Filtering + approximation is the hard part.** Most vector-search failures aren't "wrong vector" — they're "the filter silently dropped the right one."

---

## Deliverable

**`Phase 1(AI)/STEP 25/step25-ann/`**

- **`ann_bench.py`** — benchmarks exact (numpy brute force) against approximate (hnswlib HNSW) search on random vectors, printing recall@10 and query latency for several `ef_search` values. Demonstrates 25.1's trade and 25.3's tuning knobs in one runnable script.
- **`store_decision.md`** — the 25.5 decision table as a standalone checklist for choosing a vector store.

**Run it:** `pip install numpy hnswlib`, then `python ann_bench.py`.

# Step 24: Postgres + pgvector

> **Covers:** the `vector` column type, distance operators (L2 / cosine / inner product), HNSW indexing, retrieval SQL, and filtered search. This is where your embeddings from Step 20 finally get stored and searched inside Postgres.

---

## The Problem

Step 20 gave you embeddings — lists of numbers that represent meaning — but a pile of numbers isn't useful until you can answer one question fast: *"which stored vectors are closest to my query?"* You could do that in Python by loading everything into memory and comparing one by one, and that works for a thousand vectors. It collapses at a million, because every query has to scan every vector. pgvector solves this by teaching Postgres to store vectors and search them efficiently, so your data and your search live in one place under the same transactions, JOINs, and filters you already use.

---

## Foundational Concepts

### An embedding is a point in space

An embedding model turns text into a **fixed-length list of floats** (e.g. 1536 numbers). Think of it as a coordinate: "puppy" and "kitten" land near each other in that space, while "car" lands far away. **Similarity = closeness = small distance.** The entire job of vector search is "find the points nearest to my query point," which is why it's called *nearest-neighbor search*.

### Distance is the similarity primitive

"Nearest" only means something once you pick a **distance function**. pgvector gives you a few (24.2 below), and which one you pick changes what "similar" means. This is a *semantic* choice, not syntax — pick the wrong one and your rankings are silently wrong.

### pgvector is a column type, not a separate database

pgvector is a **Postgres extension**: it adds a `vector` type, distance operators, and indexes to Postgres you already run. Your vectors become just another column in a normal table, sitting beside metadata (`source`, `category`) with all the normal guarantees. That's the whole appeal — no second system to sync.

---

## 24.1 — The `vector` column type

You enable the extension once per database, then declare a column with a fixed number of dimensions:

```sql
CREATE EXTENSION vector;              -- once per database

CREATE TABLE items (
  id        bigserial PRIMARY KEY,
  content   text,
  embedding vector(3)                 -- holds a 3-number list
);

INSERT INTO items (content, embedding)
VALUES ('hello world', '[0.1, 0.2, 0.3]');   -- a float array literal
```

**Why the dimension count matters:** `vector(3)` tells Postgres every row stores exactly 3 numbers, which is what lets it do distance math and build indexes on the column. The count must match your embedding model's output — you can't put a 1536-dim embedding in a `vector(3)` column.

A few facts worth knowing:

- `vector` stores single-precision floats (4 bytes each), so a row costs `4 × dims + 8` bytes.
- `halfvec` is a half-precision variant (half the memory), `bit` stores binary vectors, `sparsevec` stores mostly-zero vectors.
- If you need different dimensions per row (e.g. multiple models in one table), use untyped `vector` and index per-dimension with an expression index — but for a normal RAG pipeline, one fixed-dimension column is the right call.

---

## 24.2 — Distance operators

Each operator computes a different notion of "how far apart two vectors are." The three you'll actually use:

| Operator | Name | What it measures | Reads as |
|---|---|---|---|
| `<->` | L2 (Euclidean) | Straight-line distance between points | smaller = closer |
| `<=>` | Cosine distance | The *angle* between vectors, ignoring their length | smaller = closer |
| `<#>` | Negative inner product | How much the vectors point the same way | larger = more similar |

**Why there are three, and when each one wins:**

- **L2** cares about *magnitude* — a long vector and a short vector pointing the same direction are still "far" under L2.
- **Cosine** cares only about *direction* — it asks "do these point the same way?" regardless of length. `cosine distance = 1 - cosine similarity`, so a cosine similarity of 0.95 is a distance of 0.05.
- **Inner product** measures overlap. Here's the key fact: **if your vectors are normalized to length 1 (most embedding models, including OpenAI's, do this), inner product and cosine similarity become the same thing** — and inner product is the fastest to compute.

The rule of thumb: **match the distance to your model's training objective, and use inner product if your embeddings are normalized.**

```sql
-- nearest neighbors by L2 distance
SELECT content FROM items ORDER BY embedding <-> '[0,0,0]' LIMIT 5;

-- cosine similarity (1 - distance) on one row
SELECT 1 - (embedding <=> '[0,0,0]') AS similarity FROM items WHERE id = 1;
```

One subtlety: `<#>` returns the *negative* inner product (because Postgres only sorts ascending on operators), so to get the actual inner product you multiply by −1.

---

## 24.3 — HNSW indexing

Without an index, every search is a **sequential scan**: Postgres computes the distance to *every single row*, sorts, and returns the top-k. That's exact (100% recall) but O(n) — fine at 1,000 rows, painful at 10M.

An **index** is the database equivalent of a book's index: instead of reading every page, you look up where the relevant entries are and jump straight to them. For vectors, pgvector offers the **HNSW** index, which builds a graph connecting each vector to its nearest neighbors so a search can walk toward the query instead of checking everything.

```sql
CREATE INDEX ON items USING hnsw (embedding vector_cosine_ops);
```

Three parameters control the trade-off between speed, recall, and memory:

- **`m`** (default 16) — how many neighbors each node connects to. More = better recall, more memory.
- **`ef_construction`** (default 64) — how thorough the graph *build* is. More = better recall, slower build.
- **`hnsw.ef_search`** (default 40) — how thorough each *query* is. More = better recall, slower query. This one you can change per query without rebuilding:

```sql
SET hnsw.ef_search = 100;
```

**Important:** an HNSW index is *approximate* — it can miss a few true neighbors to go fast. That's the recall/latency trade, and it's the subject of Step 25. For now the takeaway is: add the index to go fast, and know that "fast" costs a little accuracy.

> There's a second index type, **IVFFlat**, which clusters vectors and searches only nearby clusters. It uses less memory but usually lower recall than HNSW — details in Step 25. HNSW is the better default.

---

## 24.4 — Basic retrieval SQL

The pattern for any vector search is exactly one line of shape: **order by distance, take the top k.**

```sql
SELECT id, content, embedding <=> '[0,0,0]' AS distance
FROM items
ORDER BY embedding <=> '[0,0,0]'
LIMIT 5;
```

The same idea finds "items similar to *this* item" (item-to-item search):

```sql
SELECT * FROM items WHERE id != 1
ORDER BY embedding <-> (SELECT embedding FROM items WHERE id = 1)
LIMIT 5;
```

**The gotcha that bites everyone:** the index only kicks in when the `ORDER BY` uses the *raw distance operator directly* with a `LIMIT`. If you wrap the operator in an expression — like `ORDER BY 1 - (embedding <=> q)` — Postgres can't use the index and silently falls back to a full scan. Keep the operator bare in the `ORDER BY` clause.

---

## 24.5 — Vector search + metadata filters

Real retrieval is rarely "find the nearest vectors." It's "find the nearest vectors **from this source**, **newer than this date**." So you combine a normal `WHERE` with vector search:

```sql
SELECT * FROM items
WHERE category_id = 123
ORDER BY embedding <-> '[0,0,0]'
LIMIT 5;
```

**Why this is harder than it looks:** an approximate index returns its top-k *first*, and the `WHERE` filter is applied *after*. If the filter matches a tiny slice of your data, the index's top-k might contain almost nothing that passes the filter — so you get few or wrong results. The approaches, in order of preference:

| Approach | When it works | Cost |
|---|---|---|
| B-tree index on the filter column | Filter matches a small % of rows | Exact, fast |
| HNSW + post-filter (iterative scan) | Filter matches many rows | Scans more of the index |
| Partial HNSW index `WHERE (category_id = 123)` | A few distinct filter values | One index per value |
| Partitioning `PARTITION BY LIST(category_id)` | Many tenants / values | Scales horizontally |

**Multi-tenancy** is the same problem at the data-model level: if every tenant shares one HNSW index, one tenant's vectors can degrade another's recall. Isolate tenants with list partitioning or separate tables.

---

## Pitfalls

1. **Mismatched operator and index.** Build the index with `vector_l2_ops`, query with `<=>` — the index is ignored and you get a silent full scan. The operator you query must match the one you indexed.
2. **Wrapping the distance in an expression.** `ORDER BY 1 - (a <=> b)` disables the index. Keep the raw operator in `ORDER BY`.
3. **No `LIMIT`.** Without `LIMIT`, Postgres won't use the index.
4. **Too-low `ef_search`.** The default 40 can miss results, especially on filtered queries; raise it (or enable iterative scans).
5. **L2 on normalized embeddings.** If vectors are unit length, L2 and cosine disagree, and inner product is the correct *and* fastest choice.
6. **Building the index before bulk load.** Load data first, then `CREATE INDEX` (use `CREATE INDEX CONCURRENTLY` in production to avoid blocking writes).

---

## Quick Reference

| Goal | SQL |
|---|---|
| Enable extension | `CREATE EXTENSION vector;` |
| Vector column | `embedding vector(1536)` |
| Insert a vector | `'[0.1, 0.2, 0.3]'` |
| L2 / cosine / inner product | `<->` / `<=>` / `<#>` |
| Cosine similarity | `1 - (a <=> b)` |
| HNSW index | `USING hnsw (embedding vector_cosine_ops)` |
| Tune recall at query time | `SET hnsw.ef_search = 100;` |
| Filtered search | `WHERE x = 1 ORDER BY e <-> q LIMIT 5` |
| Debug a slow query | `EXPLAIN (ANALYZE, BUFFERS) ...` |

---

## Theory Summary

- **Your vector store is a table, not a black box.** pgvector's entire value is that vectors live beside metadata under normal Postgres guarantees — ACID, JOINs, replication, one query language.
- **Distance is a semantic decision.** Pick the function that matches your model's training objective, index it consistently, and you can't accidentally rank wrong.
- **An index trades recall for speed.** Exact search is 100% accurate but linear; HNSW is near-constant but approximate. Knowing that "fast" has a cost — and which knob controls it — is the foundation Step 25 builds on.

---

## Deliverable

**`Phase 1(AI)/STEP 24/step24-pgvector/`**

- **`schema.sql`** — `items` table with a `vector(3)` column plus an HNSW cosine index.
- **`demo.py`** — psycopg 3 script that creates the schema, inserts a handful of vectors (parameterized), then runs three queries: L2 top-3, cosine similarity, and a metadata-filtered search.

**Run it:** start Postgres, then `python demo.py "postgresql://user:pass@localhost/db"`. (Requires `pip install "psycopg[binary]"` and `CREATE EXTENSION vector`.)

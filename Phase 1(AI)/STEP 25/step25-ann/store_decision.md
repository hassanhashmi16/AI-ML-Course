# Vector store decision checklist (Step 25 deliverable)

Answer top-to-bottom; stop at the first rule that applies.

| Question | If yes |
|---|---|
| Already on Postgres, < ~10M vectors? | Use **pgvector** — one datastore, ACID, JOINs, filters. |
| Need recall-at-scale, quantization, or distributed ANN? | Use a **dedicated vector DB** (Qdrant, Pinecone, Weaviate, Milvus). |
| BM25/sparse retrieval matters as much as dense? | Use a **search engine** (Elastic/OpenSearch) — hybrid text + vector. |
| Multi-tenant, and tenants must not bleed recall into each other? | Prefer per-tenant indexes/partitions (pgvector partitions, Qdrant tenant index). |

## What to confirm before switching stores

1. Is the current store actually the bottleneck? (profile latency + recall, don't guess)
2. What recall@k do you need, and what are you getting? (benchmark vs brute force)
3. Can quantization (`halfvec`, PQ, binary) fix memory instead of a new system?
4. Is the cost of a second system (ops, sync, monitoring) worth the measured gain?

## The default

Start with **pgvector**. Escalate only when a measured limit (recall, memory, or
latency) forces it — not because a benchmark blog said dedicated DBs are faster.

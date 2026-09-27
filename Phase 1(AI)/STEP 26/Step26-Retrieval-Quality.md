# Step 26: Retrieval Quality — Hybrid Search & Reranking

> **Covers:** hybrid search + reciprocal rank fusion, cross-encoder reranking, query transformation (rewriting, expansion, HyDE, decomposition), contextual retrieval & chunk enrichment, retrieval metrics (recall@k, MRR, nDCG), and graph-augmented retrieval (GraphRAG). This is the single biggest quality lever in RAG.

---

## The Problem

Steps 24–25 gave you vector search, and the naive version is "embed the query, return the top-k nearest chunks." That works for simple questions and fails silently on real ones: a query about "revenue last quarter" returns chunks about *revenue strategy* instead of the one containing the actual number; a query for "error code E-4021" may return nothing because the embedder treats the code as noise; a vague query returns vague results no matter how good the index is. The root issue is that **vector similarity is not relevance** — a chunk can be close to the query in embedding space and still be useless for answering it. This step is the fix: the 2026 production pattern is *rewrite → hybrid retrieve (dense + BM25, RRF-fused) → cross-encoder rerank → top 5*.

---

## Foundational Concepts

### Vector similarity is not relevance

- **Similarity** = "do these two texts mean similar things?" (what an embedding measures).
- **Relevance** = "does this text help answer the question?" (what you actually want).

The two diverge constantly. "How do I cancel my subscription?" is *similar* to "steps to terminate your plan" (great, semantically), but a chunk reading "subscription pricing went up 20% this year" is also similar while being useless for the query. Retrieval quality work is, at its core, closing the gap between "similar" and "relevant."

### The pipeline is "retrieve wide, then rerank narrow"

Two-stage retrieval is the core pattern this whole step builds on:

1. **Retrieve** — get a *wide* candidate set (say, top 50–100) using something fast and cheap.
2. **Rerank** — re-score just those candidates with something slow and accurate, keep the top 5.

The key insight is that fast and accurate pull in opposite directions, so you use *two different models*: a cheap one to narrow from millions → 100, and an expensive one to narrow 100 → 5.

### Bi-encoders vs cross-encoders (the two model families)

- A **bi-encoder** embeds the query and each document *separately*, then compares their vectors. Because document embeddings are precomputed once and cached, bi-encoder retrieval scales to millions of documents. Cost: the query and document never "see" each other, so fine-grained relevance is lost.
- A **cross-encoder** feeds the query and a document *together* into one model that outputs a relevance score. It sees both texts at once and catches connections a bi-encoder misses. Cost: it must process every query–document *pair* jointly, so it's 100–1000× slower and can't be precomputed.

Retrieval uses bi-encoders; reranking uses cross-encoders. That division of labor is the entire reason hybrid+rerank works.

---

## 26.1 — Hybrid retrieval & Reciprocal Rank Fusion (RRF)

### Why one retriever isn't enough

Two retrieval signals capture different kinds of relevance, and each is blind to what the other sees:

- **Dense (embeddings)** catches *meaning* — "cancel my subscription" matches "terminate your plan" despite zero shared words. But it misses *exact terms*: "E-4021" often embeds as noise and matches nothing.
- **Sparse (BM25)** catches *exact keywords*. BM25 is the classic search-engine scoring formula — it rewards documents containing rare query terms, with diminishing returns for repetition. "E-4021" matches perfectly; but "cancel my subscription" returns nothing if the doc says "terminate your plan."

**Hybrid search** runs both retrievers and merges their results, so exact-match and semantic signals both get a vote.

### How BM25 works (one paragraph)

BM25 scores a document by summing, over each query term: `IDF(term) × [tf × (k1+1)] / [tf + k1 × (1 − b + b × |d|/avgdl)]`. In plain words: a document scores higher when it contains query terms, *especially rare ones* (that's IDF — a word like "revenue" that appears everywhere tells you little, while "E-4021" is highly distinctive). Repeated occurrences help but with diminishing returns (a word 50× is not 50× more relevant than once), and long documents are normalized down so length alone doesn't win. You don't need to memorize the formula — you need to know BM25 is *the* standard for exact, keyword-driven relevance.

### Reciprocal Rank Fusion (RRF): combining the two ranked lists

You now have two ranked lists — one from dense, one from BM25 — and their *raw scores aren't comparable* (cosine similarity is bounded 0–1; BM25 scores are unbounded and shift per query). RRF sidesteps this by ignoring scores entirely and using **only ranks**:

```
RRF_score(d) = Σ  1 / (k + rank(d))
```

where `k` is a constant (often 60) that keeps the top result from dominating. A document ranked #1 in dense and #5 in BM25 scores `1/(60+1) + 1/(60+5) = 0.0164 + 0.0154 = 0.0318`. A document ranked #3 and #2 scores `1/63 + 1/62 = 0.0320` — slightly better, because it's *consistently high in both*.

**Why RRF is the default:** it's robust — a doc that's #1 in one list and absent from the other still gets a moderate score, while a doc that's top-3 in *both* wins. And because it uses ranks, the wildly different score distributions of the two systems don't matter.

> Qdrant also offers **weighted RRF** (tune each retriever's weight on an eval set) and **DBSF** (normalize each retriever's score distribution, then sum). RRF is the safe default when you don't have an eval set; the others only help if you measure.

---

## 26.2 — Cross-encoder reranking

### The "retrieve wide, rerank narrow" pattern

Reranking fixes the core weakness of bi-encoder retrieval. Recall the trade: bi-encoders are fast but coarse, cross-encoders are slow but precise. The solution is to let each do what it's good at:

```
query → hybrid search → top 50 candidates → cross-encoder rerank → top 5 → build prompt → generate
```

The cross-encoder re-scores each candidate *against the query*, catching things the independent embeddings missed — like "Q3 earnings were $47.2M" being highly relevant to "what was revenue last quarter?" even though the words barely overlap.

### Why you can't just cross-encode everything

A cross-encoder must process the query and each document *as a pair*, so scoring a million documents means a million joint forward passes. That's why reranking only touches the ~50–100 candidates retrieval already surfaced. This two-stage split is what makes the whole thing affordable.

### Models to know (as of September 2026)

- **Cohere Rerank** (`rerank-v3.5`) — managed API, multilingual, strong quality.
- **Voyage rerank-2.5** — managed, lowest latency of the hosted options.
- **bge-reranker-v2-m3** — open-weight, strong baseline.
- **cross-encoder/ms-marco-MiniLM-L-6-v2** — open-weight, small enough for CPU prototyping.
- **ColBERT / Jina-ColBERT** — "late-interaction" multi-vector rerankers (more accurate, heavier).

The rule of thumb: **use a cross-encoder reranker as a default once you're past the prototype stage** — it's usually the cheapest large quality win available.

---

## 26.3 — Query transformation

Sometimes the query itself is the problem, not the retrieval. "What was that thing about the new policy?" contains almost no signal to search with. Query transformation fixes the query *before* it hits retrieval.

| Technique | What it does | When |
|---|---|---|
| **Rewriting** | Have an LLM rephrase the query into a better search query | Vague, context-dependent queries |
| **Expansion** | Add related terms to broaden recall | Overly terse queries |
| **HyDE** | Generate a *hypothetical answer*, embed that, search for docs similar to it | Retrieval quality is poor on raw queries |
| **Decomposition / multi-query** | Break one complex question into sub-questions, retrieve each, merge | Multi-hop questions |

**HyDE (Hypothetical Document Embeddings)** deserves a closer look because it's counterintuitive: instead of embedding the question, you ask the LLM to *write what the answer would look like*, embed that fake answer, and search for real chunks similar to it. The intuition: questions and answers live in different regions of embedding space ("how do I...?" vs "the process is..."), so a hypothetical answer sits closer to the real answer than the question does. The cost is one extra LLM call (and ~0.5–2s latency), so HyDE is worth it only when retrieval is measurably failing on raw queries.

---

## 26.4 — Contextual retrieval & chunk enrichment

### The problem chunking creates

Chunking (Step 22) splits documents into pieces, and each piece loses its surrounding context. A chunk reading "it increased 15% last quarter" is meaningless unless you know *what* "it" is — but the chunk doesn't tell you, and neither its embedding nor BM25 can recover that.

### Contextual retrieval (the fix)

For each chunk, ask an LLM to write a **50–100 token context** that explains the chunk's place in the document (what document it's from, what section, what it's about), then **prepend that context to the chunk** before you embed *and* BM25-index it. Now the chunk embeds as "…this is from the Q3 earnings report, in the revenue section, and states that revenue increased 15% last quarter" — and retrieval can find it.

The measured effect (Anthropic, September 2024):

- Contextual embeddings alone: **35%** reduction in retrieval failures.
- Contextual embeddings + contextual BM25: **49%**.
- All of that + reranking: **67%**.

**Chunk enrichment** is the broader idea: prepend section headers, document titles, or metadata to each chunk so it stays self-describing. Contextual retrieval is the LLM-powered version of it. The rule of thumb: **if chunks are losing context at the boundaries, contextual retrieval is the highest-leverage single fix — but it adds an LLM call per chunk at indexing time.**

---

## 26.5 — Retrieval metrics (measure retrieval *separately* from generation)

Before you can improve retrieval, you have to measure it — and measure it apart from generation, so you know *which stage* is failing.

| Metric | What it asks | Formula (intuition) |
|---|---|---|
| **Recall@k** | Did the relevant doc appear in top-k? | relevant ∩ top-k / relevant |
| **Precision@k** | How many of top-k were relevant? | relevant ∩ top-k / k |
| **MRR** | How high was the *first* relevant result? | mean of 1 / rank(first relevant) |
| **nDCG** | Are relevant docs ranked in a good order (graded)? | DCG / ideal DCG, position-discounted |
| **Hit rate** | Any relevant in top-k, per query? | fraction of queries with a hit |

The one-sentence meanings:

- **Recall@k** = "did I fetch the thing at all?" Use it when missing a doc is the worst failure.
- **Precision@k** = "did I avoid fetching junk?" Use it when extra junk pollutes the prompt.
- **MRR** = "did I get the right answer *first*?" Great for "one correct answer" tasks.
- **nDCG** = "is my ranking *order* good, with graded relevance?" The most nuanced of the four.

**Why separate from generation:** an end-to-end "answer was wrong" score conflates *bad retrieval* (wrong context) with *bad generation* (right context, wrong answer). The two need different fixes. Retrieval is judged by these metrics; generation is judged separately by **faithfulness** (is the answer grounded in the retrieved chunks?) and **answer correctness** (does it match the expected answer?). You can't debug a pipeline if you only look at the final output.

---

## 26.6 — Graph-augmented retrieval (GraphRAG)

### When similarity isn't enough

Vector search finds *similar* chunks, but some questions need *relationships* across chunks: "which team had the biggest satisfaction-score improvement?" requires finding each team's score, comparing them, and identifying the max — no single chunk contains the answer, and similarity search won't assemble it. Similar problem for "what are the main themes across this entire corpus?" — that's a *global* question, not a local similarity match.

### How GraphRAG works (Microsoft, 2024)

GraphRAG adds a knowledge-graph layer on top of the corpus:

1. **Extract** — an LLM pulls out *entities* (people, products, concepts) and *relationships* ("Team A reports to Team B", "X caused Y") from the documents.
2. **Build** — entities become nodes, relationships become edges, forming a knowledge graph.
3. **Cluster** — run community detection (Leiden/Louvain) to group closely-related entities.
4. **Summarize** — an LLM writes a summary of each community.

Then two query modes:

- **Local search** — start from entities semantically related to the query, and walk their neighborhoods in the graph (for specific "what is X, how does X relate to Y" questions).
- **Global search** — use the *community summaries* to answer "summarize the themes of this corpus" questions that no single chunk can answer.

**When to use it:** relationships or global structure matter more than raw similarity — multi-hop reasoning, cross-document themes, "how do these things connect." **When not to:** simple factoid lookup, where the cost (LLM extraction + graph indexing at build time, and graph traversal at query time) buys nothing. GraphRAG is a *specialized tool* for a specific failure mode, not a default.

---

## Pitfalls

1. **Assuming similar = relevant.** This is the one failure that underlies every other pitfall here. A chunk can be close in embedding space and useless for the answer.
2. **Fusing raw scores instead of ranks.** Dense and BM25 scores live on incomparable scales; a fixed `alpha` blend gets dominated by whichever retriever has bigger raw numbers on that query. Use RRF (ranks) or DBSF (normalized distributions).
3. **Reranking the whole corpus.** Cross-encoders can't precompute; trying to cross-encode everything is 100–1000× too slow. Rerank only the candidate set.
4. **Measuring only the end-to-end answer.** A wrong answer doesn't tell you if retrieval or generation failed. Measure retrieval (recall@k/MRR/nDCG) separately from generation (faithfulness/correctness).
5. **Using HyDE everywhere.** It adds an LLM call per query; only worth it when raw-query retrieval is measurably failing.
6. **Skipping contextual retrieval when chunks lose context.** If chunks read "it increased 15%" without saying what "it" is, no retrieval trick can recover it — enrich the chunk.
7. **Reaching for GraphRAG for factoid lookups.** GraphRAG is for relationships and global questions, not "find the paragraph that says X." It costs a lot at indexing time.

---

## Quick Reference

| Concept | One-liner |
|---|---|
| Hybrid search | Dense (meaning) + BM25 (keywords), merged |
| BM25 | Keyword relevance: rare terms weighted, repetition saturated |
| RRF | Fuse ranked lists via `Σ 1/(k + rank)`; uses ranks, not scores |
| Bi-encoder | Embeds query/doc separately — fast, coarse (retrieval) |
| Cross-encoder | Scores query+doc jointly — slow, precise (reranking) |
| Retrieve wide, rerank narrow | Fetch ~50–100, cross-encode to top 5 |
| HyDE | Embed a hypothetical answer instead of the query |
| Contextual retrieval | Prepend an LLM-written context to each chunk before indexing |
| Recall@k / MRR / nDCG | Did I fetch it / get it first / rank it well |
| GraphRAG | Entity-relation graph + community summaries; local vs global search |

---

## Theory Summary

- **Similarity is a proxy for relevance, not a guarantee.** Every technique in this step is a way to close the gap between "semantically close" and "actually useful."
- **Two-stage retrieval is the master pattern.** Use cheap bi-encoders to cut the space down, then an expensive cross-encoder to order what's left. Speed and accuracy are separated, not traded away blindly.
- **Complementary signals beat any single signal.** Dense catches meaning, sparse catches exact terms, and fusion (RRF) combines them without needing comparable scores.
- **Measure retrieval and generation separately.** You can't improve a pipeline you can't attribute failures in — recall@k/MRR/nDCG for the retriever, faithfulness/correctness for the generator.
- **Reach for the heavy tools only on a measured need.** Reranking, HyDE, contextual retrieval, and GraphRAG each add cost; the discipline is applying them to the specific failure mode they fix, not layering them on speculatively.

---

## Deliverable

**`Phase 1(AI)/STEP 26/step26-retrieval/`**

- **`retrieval_pipeline.py`** — a self-contained (stdlib-only) implementation of the whole pipeline on a small labeled corpus: BM25 (sparse), TF-IDF cosine (a commented stand-in for dense embeddings), RRF fusion, a simple reranker, and recall@k / MRR / nDCG. Runs each retriever (sparse, dense, hybrid, hybrid+rerank) and prints the metrics side by side, so you can *see* hybrid+rerank beat either retriever alone.

**Run it:** `python retrieval_pipeline.py` (no dependencies).

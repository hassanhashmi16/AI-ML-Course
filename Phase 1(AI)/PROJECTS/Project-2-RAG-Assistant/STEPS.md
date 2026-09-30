# Project 2: Eight-Thousanders RAG Assistant — Steps

## Overview

A retrieval-augmented knowledge assistant over the 14 eight-thousanders — the mountains above 8,000 m. You ask a question in plain English, it retrieves the relevant passages and answers with citations.

The point of this project is **not** "chat with documents." It is the thing the roadmap milestone calls for: **hybrid retrieval + reranking, not naive top-k**. You will build each layer by hand (no LangChain) so you understand every piece, measure it honestly, and can show the numbers.

**How we work through this** (same as Project 1, per `project-workflow.md`):

- Each step below is tiny and produces **one named artifact**.
- We execute **one step at a time**; you tell me when to proceed.
- After each step I explain the folder structure and how it fits the system.

---

## The corpus (why the 8000ers)

The corpus must be stuff you care about and can **grade yourself**. The 8000ers are ideal:

- **Dense, checkable facts** — height, country, first-ascent year and team, fatality counts, routes. You know this domain, so you can judge every answer as right or wrong.
- **It exercises both retrievers for real.** Half the questions are exact-match (peak names, heights, years) where **BM25/FTS wins**; the other half are thematic ("which 8000er has the worst fatality ratio?", "oxygen vs. fair means") where **dense retrieval wins**. That is exactly the case hybrid + rerank exists for.
- **Real ambiguity** — peaks have multiple names ("Savage Mountain" = K2, "Chomolungma" = Everest), disputed ascents (Manaslu 1972, Shishapangma's summit definition), and contested "all 14" lists. Ambiguity is where RAG gets interesting and where your best posts come from.
- **Naturally bounded** — 14 peaks, ~20-40 articles, a few hundred chunks. Small on purpose: fast to re-index, easy to eyeball, quick to evaluate.

The 14 peaks the corpus covers:

| # | Peak | Height (m) | Country / range |
|---|---|---|---|
| 1 | Everest | 8,848.86 | Nepal / China (Himalaya) |
| 2 | K2 | 8,611 | Pakistan / China (Karakoram) |
| 3 | Kangchenjunga | 8,586 | Nepal / India (Himalaya) |
| 4 | Lhotse | 8,516 | Nepal / China (Himalaya) |
| 5 | Makalu | 8,485 | Nepal / China (Himalaya) |
| 6 | Cho Oyu | 8,188 | Nepal / China (Himalaya) |
| 7 | Dhaulagiri I | 8,167 | Nepal (Himalaya) |
| 8 | Manaslu | 8,163 | Nepal (Himalaya) |
| 9 | Nanga Parbat | 8,126 | Pakistan (Himalaya) |
| 10 | Annapurna I | 8,091 | Nepal (Himalaya) |
| 11 | Gasherbrum I | 8,080 | Pakistan / China (Karakoram) |
| 12 | Broad Peak | 8,051 | Pakistan / China (Karakoram) |
| 13 | Gasherbrum II | 8,035 | Pakistan / China (Karakoram) |
| 14 | Shishapangma | 8,027 | China / Tibet (Himalaya) |

**Sources:** English Wikipedia articles for each peak + the "eight-thousander" list page (free, clean, citable). A hand-built `peaks.json` adds the structured facts. Everything is fetched by a script, so the corpus is reproducible.

---

## Stack & decisions

| Layer | Choice | Why / trade-off |
|---|---|---|
| Generation | Gemini `gemini-2.0-flash` | Same provider as Project 1 — you already have the key and the pattern (`response_schema`). |
| Embeddings | Gemini embedding model (768-dim) **or** local `sentence-transformers` | Gemini = one API key, no torch. Local = free/offline but needs a torch install and changes `EMBED_DIM`. **Default: Gemini.** |
| Dense store | Postgres + **pgvector** (HNSW, cosine) | Step 24-25. One system for vectors *and* metadata filtering. |
| Sparse retriever | Postgres **full-text search** (`tsvector`, GIN, `ts_rank_cd`) | The BM25 half, with zero extra infrastructure. |
| Fusion | **Reciprocal Rank Fusion** | Step 26. Fuses ranked lists without comparing score scales. |
| Reranker | **Cohere Rerank** (default) or local cross-encoder | Step 26's production pattern. Cohere = no torch; local = offline. **Default: Cohere.** |
| Backend | FastAPI + `psycopg` 3 | Step 28. |
| Frontend | React (Vite) + `fetch`/`ReadableStream` | Step 29. You already know React. |
| DB runtime | Docker `pgvector/pgvector` | Avoids a native Postgres+pgvector install on Windows. |

**Deliberately no LangChain.** Steps 26-27 taught the framework; this project builds the same pipeline by hand so you can defend every line in an interview and swap any component. Framework comprehension is a later step's exercise.

---

## System architecture

```
                    ┌─────────────────────────────────────────────┐
                    │  INGEST (offline, run once / on change)      │
                    │                                             │
  data/peaks.json ──┤  fetch_corpus → parse → chunk → embed → store│──► Postgres
  Wikipedia (web) ──┤                                             │    (pgvector)
                    └─────────────────────────────────────────────┘
                                        │
                                        ▼
  user question ──► rewrite ──► ┌───────────────┐
                                │ hybrid search │
                   dense (pgvector) + sparse (FTS)  →  RRF fuse  →  rerank  → top-k
                                └───────────────┘
                                        │
                                        ▼
                              generate (grounded + cited) ──► FastAPI ──► React UI
```

Data flow in words: raw sources become **documents**, documents are split into **chunks**, each chunk gets an **embedding** and a **full-text vector**, both stored in one Postgres row. A question is rewritten, run through **both** retrievers, fused, reranked, and only the top few chunks reach the LLM, which answers **with citations** back to those chunks.

---

## Directory structure (target)

```
Project-2-RAG-Assistant/
├── STEPS.md                  # this file
├── README.md                 # how to run it
├── requirements.txt
├── .env.example              # GEMINI_API_KEY, COHERE_API_KEY, DATABASE_URL
├── .gitignore
├── config.py                 # one source of truth: DB url, model names, k values
├── docker-compose.yml        # Postgres + pgvector
├── data/
│   ├── peaks.json            # structured facts for the 14
│   └── raw/                  # cached article text, one file per peak
├── db/
│   └── schema.sql            # documents, chunks, peaks + indexes
├── ingest/
│   ├── fetch_corpus.py       # download + cache Wikipedia text
│   ├── parse.py              # clean + dedupe (reuse Step 21)
│   ├── chunk.py              # structure-aware chunking (Step 22)
│   ├── embed.py              # batch embeddings
│   ├── store.py              # idempotent DB upserts
│   └── run_ingest.py         # CLI: wiring of the whole pipeline
├── retrieval/
│   ├── dense.py              # pgvector cosine top-k
│   ├── sparse.py             # Postgres FTS top-k
│   ├── rewrite.py            # LLM query rewrite / alias expansion
│   ├── rerank.py             # cross-encoder rerank
│   ├── structured.py         # exact-fact lookup over peaks table
│   └── search.py             # the full retrieve → fuse → rerank → top-k
├── generation/
│   └── answer.py             # grounded answer + citations (Pydantic)
├── api/
│   └── main.py               # FastAPI: /ask, /ask-stream, /health, /peaks
├── frontend/
│   └── Chat.jsx              # streaming UI + sources panel
└── eval/
    ├── questions.jsonl       # 30-50 graded questions
    └── run_eval.py           # recall@k, MRR, nDCG per retriever
```

---

## Phases & steps

Each step: **What** (one line), **Why** (engineering reasoning), **How** (approach), **Artifact** (the named deliverable).

### Phase A — Foundation

#### Step 1: Project skeleton, config, requirements

**What:** Create the folder, `requirements.txt`, `.env.example`, `.gitignore`, and `config.py`.
**Why:** One source of truth for model names, the DB URL, and the `k` values. Step 29's pitfall list ("hardcoding the backend URL") generalizes: never scatter constants across files.
**How:** `config.py` loads env via `dotenv` and exposes `DATABASE_URL`, `EMBED_MODEL`, `EMBED_DIM`, `GEN_MODEL`, `RETRIEVE_K`, `FUSE_K`, `RERANK_K`.
**Artifact:** `config.py`, `requirements.txt`, `.env.example`.

#### Step 2: Build the corpus (structured facts + raw articles)

**What:** `data/peaks.json` with structured facts for the 14 peaks, and `ingest/fetch_corpus.py` that downloads and caches the Wikipedia article text for each peak plus the list page.
**Why:** The corpus must be clean, citable, and reproducible. Structured facts enable the later "is RAG even the right tool?" comparison. Caching raw text means you never re-hit the network while iterating.
**How:** Fetch plain-text extracts via the Wikipedia API; write one `.txt` per peak into `data/raw/` with the source URL recorded. `peaks.json` holds `{name, aliases, height_m, country, range, first_ascent_year, first_ascenters}` (first-ascent fields sourced from the articles, not from memory).
**Artifact:** `data/peaks.json`, `ingest/fetch_corpus.py`, `data/raw/*.txt`.

### Phase B — Ingestion → storage

#### Step 3: Parse + clean (reuse Step 21)

**What:** `ingest/parse.py` turns each raw file into `DocumentChunk` records with `source`, `section`, and `content_hash`.
**Why:** Garbage extraction breaks RAG before chunking ever runs. The Step 21 deliverable already wrote clean/dedupe/hash logic — reuse it instead of re-deriving it.
**How:** Adapt Step 21's `clean()` (whitespace + zero-width normalization) and `dedupe()` (content hash). Detect sections from the article's heading lines.
**Artifact:** `ingest/parse.py`.

#### Step 4: Chunking

**What:** `ingest/chunk.py` splits parsed text into ~500-token chunks with ~15% overlap, keeping a heading "breadcrumb" prepended to each chunk.
**Why:** Bad chunking silently breaks retrieval (Step 22). Structure-aware splitting beats fixed-size for a factual corpus, because a chunk that straddles two sections answers neither cleanly. The breadcrumb keeps context ("Everest > Climbing routes > South Col") so a retrieved chunk is self-describing when shown to the user.
**How:** Split on headings first, then recursively by paragraph/sentence to the target size; carry `peak` and `section` metadata onto every chunk.
**Artifact:** `ingest/chunk.py`.

#### Step 5: Database schema + Docker

**What:** `db/schema.sql` (tables `documents`, `chunks`, `peaks`; HNSW index on the vector, GIN index on the generated `tsvector`) and `docker-compose.yml` running `pgvector/pgvector`.
**Why:** Schema design from Step 23; ANN indexing from Step 25. The key move is a **generated `tsvector` column** on `chunks` so one row serves both retrievers, and an HNSW index matching the cosine operator (Step 24's pitfall: a mismatched operator silently ignores the index).
**How:** `CREATE EXTENSION vector;` then `chunks.embedding vector(768)`, `chunks.tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED`, HNSW `vector_cosine_ops`, GIN on `tsv`. `chunks.content_hash` is unique for idempotent upserts.
**Artifact:** `db/schema.sql`, `docker-compose.yml`.

#### Step 6: Embedding module

**What:** `ingest/embed.py` — batch-embed chunk texts and return vectors, with retry/backoff.
**Why:** The dense backbone. Batching and backoff are what keep an ingest run from dying halfway through on a rate limit (a real failure mode, not a hypothetical).
**How:** Send N texts per call; exponential backoff on 429/timeout. Dimension returned must match `EMBED_DIM` in `config.py`.
**Artifact:** `ingest/embed.py`.

#### Step 7: Ingest pipeline + idempotent store + CLI

**What:** `ingest/store.py` upserts documents and chunks keyed on `content_hash`, and `ingest/run_ingest.py` wires `fetch → parse → chunk → embed → store` into one command.
**Why:** Idempotent re-ingestion (Step 21's hashing lesson): re-running must not duplicate chunks, and changed files must replace their old chunks. One command to rebuild the index means you can iterate on chunking without fear.
**How:** Upsert on `content_hash`; when a file's hash changes, delete its stale chunks first. Print added/skipped/updated counts.
**Artifact:** `ingest/store.py`, `ingest/run_ingest.py`.

### Phase C — Retrieval (the core of the project)

#### Step 8: Dense retrieval

**What:** `retrieval/dense.py` — embed the query and return top-k chunks by pgvector cosine distance, with an optional metadata filter (e.g. restrict to one peak).
**Why:** The semantic half of hybrid: it finds passages that mean the same thing even when the words differ ("how deadly is Annapurna" ↔ "Annapurna I has the highest fatality ratio").
**How:** The Step 24 pattern — `ORDER BY embedding <=> %s LIMIT k`, parameterized (never f-string the vector in).
**Artifact:** `retrieval/dense.py`.

#### Step 9: Sparse retrieval (Postgres FTS)

**What:** `retrieval/sparse.py` — top-k chunks by `ts_rank_cd` over the `tsv` column, using `websearch_to_tsquery`.
**Why:** The exact-match half. Numbers, years, and rare names ("Gasherbrum IV", "8,611", "1954") are where dense retrieval is weakest and lexical matching wins. Keeping this in Postgres means one datastore, one connection, no second service.
**How:** GIN index on `tsv`; `websearch_to_tsquery('english', %s)` handles quoted phrases and `OR` safely.
**Artifact:** `retrieval/sparse.py`.

#### Step 10: Query rewriting

**What:** `retrieval/rewrite.py` — an LLM call that rewrites the user question into 2-3 search queries and expands known aliases.
**Why:** The 2026 production pattern is **rewrite → hybrid retrieve**, and the 8000ers make the reason obvious: a user types "Savage Mountain" or "Chomolungma" and neither retriever has ever seen those strings next to K2/Everest in the index. Rewriting maps the user's vocabulary onto the corpus's.
**How:** A small Gemini call returning JSON `{"queries": [...]}` built from the alias map in `peaks.json`; on any error, fall back to the original question (never let rewrite break a query).
**Artifact:** `retrieval/rewrite.py`.

#### Step 11: Hybrid fusion + reranking

**What:** `retrieval/search.py` — run dense and sparse for each rewritten query, fuse the ranked lists with RRF, rerank the top ~25 candidates with a cross-encoder, return the top-k with scores. `retrieval/rerank.py` holds the reranker.
**Why:** This is the whole point of the project. RRF fuses ranked lists using only ranks, so BM25's score scale and cosine's score scale never have to be compared. Reranking then fixes ordering, because a bi-encoder (retriever) is fast-but-coarse while a cross-encoder reads query and passage *together* and is slow-but-accurate. Retrieve wide, rerank narrow.
**How:** Reuse the RRF function from Step 26. `rerank.py` calls Cohere Rerank (or a local `sentence-transformers` cross-encoder behind the same function signature).
**Artifact:** `retrieval/search.py`, `retrieval/rerank.py`.

#### Step 12: Structured lookup (optional, but flagged)

**What:** `retrieval/structured.py` — detect exact-fact questions about the 14 (height, country, first ascent) and answer them from the `peaks` table with a parameterized query.
**Why:** Demonstrates the judgment that **RAG is not always the answer**. "How tall is K2?" is a table lookup, not a retrieval problem. Showing when to bypass retrieval is a senior signal, and it ties back to Step 23.
**How:** Keyword route (height / country / first ascent) → pre-written parameterized SQL. **No free-form SQL execution.**
**Artifact:** `retrieval/structured.py`.

### Phase D — Generation

#### Step 13: Grounded generation with citations

**What:** `generation/answer.py` — build a context block from the top-k chunks (numbered), have Gemini answer **only from that context**, and return a Pydantic model `{answer, citations: [chunk_id...], confidence}`.
**Why:** Citations are what make the answer trustworthy and verifiable (Step 29's product judgment: show sources when accuracy matters). Reusing Project 1's `response_schema` pattern means the citation list is validated structure, not parsed prose.
**How:** Prompt instructs "answer only from the numbered sources; if the sources don't contain the answer, say so." Map returned chunk ids back to their `source`/`peak`/`section` metadata for display.
**Artifact:** `generation/answer.py`.

### Phase E — Serving & UI

#### Step 14: FastAPI service

**What:** `api/main.py` — CORS config, `POST /ask` (blocking: answer + sources), `POST /ask-stream` (SSE token stream), `GET /health`, `GET /peaks`.
**Why:** Step 28. An API is the surface everything else attaches to (the React UI now, the agent in Project 4 later).
**How:** `search()` → `answer()`; `StreamingResponse` for tokens; explicit CORS origin list (not `*`). Log every query (query, retrieved ids, latency, token cost) to a `query_log` table now — this is the hook Project 8's monitoring will attach to later.
**Artifact:** `api/main.py`.

#### Step 15: React UI

**What:** `frontend/Chat.jsx` — a chat component that streams the answer, shows a collapsible **Sources** panel, and handles all four states (idle / loading / error / success).
**Why:** Step 29's deliverable and the thing that makes this postable. A stranger can click it.
**How:** Step 29's `fetch` + `ReadableStream` loop for streaming; sources rendered from the `citations` payload; a retry button on error. Backend URL from an env var, never hardcoded.
**Artifact:** `frontend/Chat.jsx`.

### Phase F — Evaluation seed

#### Step 16: Build the eval set + harness (seeds Steps 30-31)

**What:** `eval/questions.jsonl` — 30-50 hand-written questions with ground-truth `peak`/`section` labels — and `eval/run_eval.py`, which reports recall@k, MRR, and nDCG for **naive dense** vs **hybrid** vs **hybrid + rerank**.
**Why:** Without a number, "improved retrieval" is a vibe. This step produces the measurable claim the whole project is built to make — and it is exactly what Step 30 (RAGAS) and Step 31 (eval suite) formalize later. Also: label each question as **exact-match** or **thematic** so you can show *where* hybrid helps.
**How:** Reuse Step 26's metrics verbatim. Run all three configurations on the same set and print the comparison table.
**Artifact:** `eval/questions.jsonl`, `eval/run_eval.py`.

---

## Definition of done

- `python -m ingest.run_ingest` builds the full index from scratch in one command, idempotently.
- `retrieval/search.py` returns hybrid + reranked top-k, and `eval/run_eval.py` shows hybrid + rerank **beating** naive dense on the same questions.
- `POST /ask-stream` streams a cited answer; `Chat.jsx` renders it with a working Sources panel.
- The eval table (naive vs hybrid vs hybrid+rerank) is committed as a result, not just a claim.

## How this extends into later projects

This is the foundation of the **flagship line**, so the architecture is chosen to make those layers additive:

- **Project 4 (flagship):** the agentic, evaluated version. `retrieval/search.py` and `generation/answer.py` are pure functions with stable signatures precisely so an agent can call them as **tools**. Memory/sessions slot in at the API layer.
- **Project 8 (monitoring):** the `query_log` table written in Step 14 is where latency/token/cost monitoring and drift detection attach. Nothing to retrofit.
- **Project 9 (safety + cost routing):** the retriever already separates retrieve from generate, so swapping the generation model by query difficulty (cost routing) is a config change, not a rewrite.

## LinkedIn angle

The post is **not** "I built a RAG app." It's the number from Step 16:

> "I built a search assistant over the 14 eight-thousanders. Naive embedding search got N/10 of my test questions right. Adding hybrid retrieval and a reranker got M/10. Here's the exact thing that changed."

One honest before/after on a corpus you know cold is worth more than any feature list.

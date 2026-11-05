# CodeTrail â€” Architecture

**Trace the decisions behind the code.** CodeTrail accepts a public GitHub
repository link and a question, follows the relevant code, history, and
discussions, and returns a cited explanation with a timeline and an explicit
unknown list. Findings are labelled **documented**, **inferred**, or treated as
**unknown** within a recorded scope.

This document explains how the system is put together, which parts are ours
versus libraries, what the evaluation actually measured, and where the limits
are.

---

## The pipeline

```
GitHub repo + question (+ optional path/ref)
   â”‚
   â–¼  github_source/         validate repo, resolve ref â†’ SHA, collect evidence (cached)
   â–¼  ingest/                records â†’ LangChain Documents â†’ chunks â†’ vectors in Qdrant
   â–¼  retrieval/             hybrid search (dense + sparse) + cross-encoder rerank
   â–¼  agent/                 investigate â†’ tools â†’ grade â†’ investigate|synthesize
   â–¼  generation/ + reporting/  structured claims â†’ citation validation â†’ grounding
   â–¼  Report                  summary, claims, timeline, unresolved, coverage
   â–¼  api/ + frontend/        FastAPI service, SSE stage events, React workspace
```

Everything before generation answers one question: **which five pieces of
evidence best explain this change, and where exactly did each come from?**

---

## Components

| Module | Responsibility |
|---|---|
| `config.py` | one validated settings boundary (keys, limits, providers); env > `.env` > defaults |
| `models.py` | shared contracts: request, snapshot, source record, excerpt, claim, timeline, coverage, report; label rules enforced by validators |
| `agent/state.py` | the typed LangGraph state (messages, sources, counters, control fields) with merge reducers |
| `github_source/` | PyGithub readers (files, history, changes, PRs/issues/comments/reviews) + diskcache collector; every read bounded and visibly warned |
| `ingest/` | Documents, language-aware chunking with exact offsets/lines, embedding + Qdrant indexing with stable IDs, per-source replacement, manifest/rebuild guard |
| `retrieval/` | local embedders, Qdrant clients, hybrid/dense search with scope filters, local cross-encoder reranking |
| `agent/tools.py` | five LangChain tools bound to a trusted run context; each read indexes what it fetched |
| `agent/nodes.py` | investigation strategy: tool-driven loop, evidence grading, budgets, synthesis, grounding with one revision |
| `agent/graph.py` | LangGraph wiring: `investigate â†’ tools â†’ grade â†’ investigate | synthesize` |
| `agent/policy.py` | tool/source/token/time budgets and repeated-action detection, each returning a reason |
| `agent/persistence.py` + `cli.py` | SQLite checkpointing, thread IDs, resume, the command line |
| `agent/memory.py` | findings saved after reports; recall filtered by repo + base SHA; revalidation (supported/stale/unverified) |
| `agent/observability.py` + `api/events.py` | JSONL stage logs, public progress events, opt-in content-hidden LangSmith |
| `eval/` | labelled cases and the baseline-vs-investigation runner |
| `tests/` | focused pytest suite for contracts, citations, budgets, persistence |
| `api/` | FastAPI service: health, investigate, status, SSE events, resume, saved reports |
| `frontend/` | React/Vite workspace: prepared cases, progress, report, timeline, evidence drawer |

---

## Invariants that keep answers honest

1. **One identity per source.** `make_source_id` is deterministic; re-collection
   and re-indexing replace instead of duplicating (idempotent replay).
2. **Scope filters on every retrieval.** Every search is restricted to the
   repository and pinned SHA â€” and, since Step 19, to the **source IDs this
   investigation actually inspected**. A shared index can therefore never leak
   an earlier run's chunks into a new answer.
3. **Verbatim citations.** A claim cites a `source_id` plus a quote that must
   match the stored record exactly (markdown/whitespace differences are located
   tolerantly, but the stored quote is always the exact source span).
4. **Semantic grounding is separate.** After citation validation, a judge asks
   whether each quote actually supports its statement. One revision is allowed;
   claims still unsupported are removed and recorded as unresolved.
5. **Every limit is visible.** Truncation, failed reads, budget exhaustion, and
   grounding downgrades all surface (warnings, coverage notes, trace events,
   `unresolved`), never disappear.
6. **Settings changes force explicit rebuilds.** The index manifest records
   provider/model/dimension/splitter; changing any of them refuses indexing
   until `--rebuild`. A rebuild is *provably* empty: points are cleared
   explicitly (local-mode Qdrant was observed resurrecting segment files after
   a delete-and-recreate), and `check_search` asserts collection count equals
   indexed chunk count.

---

## What the libraries do, and what stays ours

| Concern | Library | What remains ours |
|---|---|---|
| Data exchange | LangChain `Document`, `Embeddings`, tool schemas | what a source/claim/report is |
| Chunking | `RecursiveCharacterTextSplitter` (language-aware) | chunk IDs, offsets, line numbers |
| Vectors + search | Qdrant (dense+sparse hybrid, payload filters) | scope policy, wide-then-narrow retrieval, labels |
| Embeddings + rerank | FastEmbed local models (bge-small, bm25, ms-marco cross-encoder) | when to rerank, disabled/failed labelling |
| Model calls | `ChatGroq` + structured output (Google optional) | prompts, claim schema, validation, revision policy |
| Execution | LangGraph `StateGraph`, `ToolNode`, SQLite checkpointer | nodes, routes, budgets, stopping rules |
| Events | LangSmith (optional) | the public event contract; content stays local |

Compare with the hand-built Projects 2 and 3: hybrid fusion, pgvector SQL,
BM25, retry wrappers, the agent loop, and checkpointing were written by hand
there. Here the **math and plumbing** moved into libraries; the **policy**
(what to retrieve, what to trust, what to label) stayed in this repository.

---

## Stores on disk

| Store | Location | Contents |
|---|---|---|
| Source cache | `data/cache/` | every fetched `SourceRecord`, keyed by stable ID (diskcache) |
| Vector index | `data/qdrant/` | one collection per repository@SHA (dense + sparse) |
| Findings | `data/qdrant/` (`codetrail_findings`) | validated claims + source refs, repo/SHA-scoped |
| Checkpoints | `data/checkpoints.sqlite` | LangGraph state per thread (resume) |
| Traces | `data/traces/<thread>.jsonl` | public progress events per run |
| Reports | `reports/` | finished `Report` JSON files |

All of these live under gitignored paths.

---

## Evaluation (as recorded, 16 October 2026)

Three labelled cases, both workflows, same snapshot/model/report contract:

| case | flow | status | claims | cites | rationale | unknown | calls | tokens | ms |
|---|---|---|---|---|---|---|---|---|---|
| ct-001 | baseline | complete | 2 | ok | ok | â€“ | 1 | 0 | 8567 |
| ct-001 | investigation | partial | 1 | ok | ok | â€“ | 12 | 2721 | 58473 |
| ct-002 | baseline | partial | 3 | FAIL | ok | â€“ | 1 | 0 | 20951 |
| ct-002 | investigation | complete | 2 | ok | ok | â€“ | 7 | 2599 | 74097 |
| ct-003 | baseline | partial | 0 | ok | ok | ok | 1 | 0 | 17498 |
| ct-003 | investigation | partial | 0 | ok | ok | ok | 10 | 10460 | 133703 |

Reading honestly:

- The investigation **fixed** a citation failure on ct-002 that the baseline
  hit, and both handled the unknown case (ct-003) by refusing to invent a
  number.
- The investigation cost **7â€“12Ã— the calls and 3â€“8Ã— the latency**. On ct-001 it
  needed the full tool budget and still ended `partial`.
- Tokens are provider-reported and undercount for structured calls (they often
  report none); calls are exact.
- One failed check (ct-002 baseline citation) is printed and saved, not averaged.

After this run, a fourth case (**CT-004, conflicting history**: "removed or kept
for compatibility?") was added and smoke-tested live. The agent produced a
documented claim quoting PR #4682's compatibility paragraph and honestly
downgraded one overreaching claim (status `partial`). The baseline could not
answer it before the Step 19 scope fix; the case is now part of the harness.

The original run did not include Ragas scoring. The 5 November follow-up now
scores those saved reports without regenerating answers; see
[faithfulness results and context limitations](faithfulness-results.md).

---

## Running the checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q                       # contracts, citations, budgets, persistence
.\.venv\Scripts\python.exe scripts\check_setup.py             # environment + integrations
.\.venv\Scripts\python.exe scripts\check_models.py            # shared contracts
.\.venv\Scripts\python.exe scripts\check_github.py            # readers against the pinned Flask snapshot
.\.venv\Scripts\python.exe scripts\check_collect.py           # cached collector + bundle
.\.venv\Scripts\python.exe scripts\check_chunks.py            # chunk â†’ source offsets
.\.venv\Scripts\python.exe scripts\check_index.py             # embeddings + Qdrant manifest
.\.venv\Scripts\python.exe scripts\check_search.py            # hybrid retrieval + reranking
.\.venv\Scripts\python.exe scripts\check_answer.py            # baseline cited answer
.\.venv\Scripts\python.exe scripts\check_tools.py             # investigator tools
.\.venv\Scripts\python.exe scripts\check_graph.py             # live investigation workflow
.\.venv\Scripts\python.exe scripts\check_policy.py            # budgets + grounding fixtures
.\.venv\Scripts\python.exe scripts\check_resume.py            # crash â†’ checkpoint â†’ resume
.\.venv\Scripts\python.exe scripts\check_memory.py            # findings save/recall/revalidate
.\.venv\Scripts\python.exe scripts\check_traces.py            # event stream + JSONL log
.\.venv\Scripts\python.exe scripts\check_api.py               # FastAPI service (fixtures)
.\.venv\Scripts\python.exe eval\run_eval.py                   # baseline vs investigation (live)
```

Frontend:

```powershell
cd frontend
npm install
npm run build
npm run lint
npm run dev
```

---

## Current limits (5 November 2026)

- Public mode now has GitHub identity, private account workspaces, a durable
  queue, and live event streaming. It remains a **single-server, single-active-
  investigation** deployment, with a supervised process per job and persistent
  SQLite/local Qdrant. See [public deployment](deployment.md).
- Findings are now recalled by normal CLI/API investigations as untrusted
  leads, filtered by repository and SHA, and revalidated against this run's
  evidence. Public accounts have separate stores for the complete pipeline.
- The verified evaluation set is still four cases from Flask. The legacy
  Ragas scores use reconstructed cited-source contexts; they do not measure
  broad generalization or the quality of newly generated reports.
- Token accounting remains incomplete. Admission quotas and process deadlines
  bound usage; configure provider billing limits separately.
- The sign-in screen was checked in a browser; OAuth/PKCE and live events are
  covered by tests. Real GitHub sign-in, a complete browser investigation,
  HTTPS/proxy behavior, backups, and retention must be checked on the chosen
  production host before announcing a public URL.
- Public repositories only. Private/internal repos are explicitly rejected.
  Non-Python-heavy repositories and very large histories remain less tested.

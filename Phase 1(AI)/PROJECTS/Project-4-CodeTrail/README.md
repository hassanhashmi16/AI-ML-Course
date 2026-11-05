---
title: CodeTrail
emoji: 🔎
colorFrom: green
colorTo: gray
sdk: docker
app_port: 8000
---

# CodeTrail

**Trace the decisions behind the code.**

Deployment: [public app operations](docs/deployment.md) ·
[zero-budget Hugging Face setup](docs/huggingface.md).

CodeTrail accepts a public GitHub repository link and a question, follows the
relevant code, history, and discussions, and returns a cited explanation with a
timeline. Every claim is labelled **documented**, **inferred**, or left
**unresolved**, and every cited quote is checked against its stored source.

Reading code shows *what* it does. CodeTrail reconstructs *why* it changed.

## Status

The original local milestone is implemented. Public-app preparation now adds
GitHub sign-in, account-isolated storage and findings, a durable bounded queue,
live progress, public-repository enforcement, request/quota limits, and Docker
packaging. Hosting and real OAuth configuration are still required.

See [public deployment](docs/deployment.md) for the single-server architecture,
setup, operational limits, and checks before announcing a public URL.
See [Ragas results](docs/faithfulness-results.md) for measured scores and limits.

## Quickstart (Windows / PowerShell)

Tested with CPython 3.14 on Windows x86-64.

```powershell
# one isolated environment; packages are not installed into global Python
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary :all: --cache-dir .cache\pip -r requirements.lock

# create local configuration without overwriting an existing credential file
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

# import the integrations and validate settings without calling model APIs
.\.venv\Scripts\python.exe scripts\check_setup.py --with-eval
```

Add keys to `.env` as needed; all are optional for offline checks:

| Setting | Used for |
|---|---|
| `GROQ_API_KEY` | generation (default provider) |
| `GITHUB_TOKEN` | higher GitHub rate limits |
| `GEMINI_API_KEY` | generation when `GEN_PROVIDER=google`; embeddings when `EMBED_PROVIDER=google` |
| `COHERE_API_KEY` | hosted reranking when `RERANK_PROVIDER=cohere` |
| `LANGSMITH_API_KEY` | optional traces (inputs/outputs hidden) |

Embeddings, sparse search, and reranking run locally by default, so indexing
and retrieval need no provider credentials.

## Run the workspace

```powershell
# terminal 1 — the API
.\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000

# terminal 2 — the interface (proxies API paths to :8000)
cd frontend
npm install
npm run dev
```

Open the Vite URL (usually http://localhost:5173), pick a prepared case, or
paste any public repository link and question. Saved reports are listed in the
sidebar; an interrupted run can be resumed by its thread id.

Command-line equivalents:

```powershell
# full agent investigation (checkpointed; prints the thread id)
.\.venv\Scripts\python.exe cli.py investigate --repo https://github.com/pallets/flask --ref 2.2.0 --path src/flask/ctx.py --pull 4682 --question "Why did Flask replace LocalStack?"

# one-pass baseline answer
.\.venv\Scripts\python.exe -m generation.answer --repo https://github.com/pallets/flask --ref 2.2.0 --path src/flask/ctx.py --pull 4682 --question "Why did Flask replace LocalStack?"

# build or refresh the local index for files
.\.venv\Scripts\python.exe -m ingest.index --repo https://github.com/pallets/flask --ref 2.2.0 --path src/flask/ctx.py

# resume an interrupted run
.\.venv\Scripts\python.exe cli.py resume --thread <thread-id>
```

## Workspace

Use **New investigation** to write a brief or load a prepared case. Selecting a
case fills the form; it does not start a paid run. **History** shows your own
questions, repositories, status, dates, and completed durations, with search and
one-click reopening or recovery actions. Opening a report makes no model call.

While an investigation runs, the workspace shows elapsed time from submission,
the latest completed stage, and expandable activity. Investigations can take a
few minutes; repeated model and evidence-grading calls usually dominate latency.
Report labels distinguish supported findings from partial/unknown results.

## Demo cases

`docs/demo-cases.md` holds the hand-verified reference cases:

| Case | Question | Expected behavior |
|---|---|---|
| **CT-001** | Why direct ContextVar handling? | documented reason, cites PR #4682 |
| **CT-002** | Why the JSONProvider interface? | documented reason, cites PR #4692 |
| **CT-003** | Exact % throughput improvement? | scoped unknown, no invented number |
| **CT-004** | Removed entirely, or kept for compatibility? | both halves: internals replaced, deprecated shim kept |

The UI ships these as one-click prepared cases.

## Evaluation

`eval/run_eval.py` runs the baseline and the investigation over labelled cases
with the same snapshot, model settings, and output contract, and saves every
report under `reports/eval/<run>/`. Recorded results and an honest reading are
in [docs/architecture.md](docs/architecture.md#evaluation-as-recorded-16-october-2026).

Short version: the investigation fixed a baseline citation failure and matched
it on the unknown case, at 7–12× the calls and 3–8× the latency. Failures are
printed per case, never averaged away.

## How it is built

- Step-by-step build notes and recorded checks: [STEPS.md](STEPS.md)
- Architecture, invariants, framework comparison, limits: [docs/architecture.md](docs/architecture.md)
- The larger AI/ML roadmap: [AI_Engineer_StepByStep.html](https://github.com/hassanhashmi16/AI-ML-Course/blob/main/AI_Engineer_StepByStep.html)

Everything is checkable:

```powershell
.\.venv\Scripts\python.exe -m pytest -q          # contracts, citations, budgets, persistence
.\.venv\Scripts\python.exe scripts\check_api.py  # FastAPI service (fixtures)
.\.venv\Scripts\python.exe eval\run_eval.py      # baseline vs investigation (live model calls)
```

The full list of check scripts is in
[docs/architecture.md](docs/architecture.md#running-the-checks).

## Known limits

In local mode: single active investigation with synchronous API requests; local on-disk
Qdrant and CPU embedding/reranking models; a small (4-case) verified evaluation
set; no Ragas pass yet; token counts are lower bounds; browser verification is
manual. Public mode queues work, isolates accounts, and streams progress; it is
limited to one server/worker with persistent SQLite and local Qdrant. Real OAuth
and HTTPS rollout checks, retention policy, and operational monitoring remain.
Details: [deployment](docs/deployment.md).

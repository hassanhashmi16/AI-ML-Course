# CodeTrail

**Trace the decisions behind the code.**

CodeTrail will accept a public GitHub repository link and a question, follow the
relevant code/history/discussions, and produce a cited explanation and timeline.
The [Flask examples](docs/demo-cases.md) are development cases; the application
will take its repository from each request.

## Current progress

Steps 1-10 are complete: reference cases, environment and configuration, the
shared request/evidence/report contracts with the investigation state, the
bounded GitHub readers, the cached evidence collector, source-mapped chunks,
the local vector index, hybrid retrieval with reranking, the cited baseline
answer, and the investigator tools.
Next is Step 11, building the LangGraph investigation workflow.
The collector, investigation workflow, API, and interface are
implemented in the remaining [build steps](STEPS.md).

## Setup on Windows / PowerShell

Run these commands inside `Phase 1(AI)/PROJECTS/Project-4-CodeTrail`.
The tested interpreter is **CPython 3.14 on Windows x86-64**; the manifest
deliberately targets this Python minor version. Compatibility on other Python
versions/platforms has not been established by this setup check.

```powershell
# One isolated environment; packages are not installed into global Python.
py -3.14 -m venv .venv

# Install exact versions whose downloaded files match the recorded hashes.
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary :all: --cache-dir .cache\pip -r requirements.lock

# Create local configuration without overwriting an existing credential file.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

# Import the integrations and validate settings without calling model APIs.
.\.venv\Scripts\python.exe scripts\check_setup.py --with-eval
.\.venv\Scripts\python.exe -m pip check
```

Activation is optional because every command explicitly selects `.venv`'s Python.
The lock currently includes runtime, development, and evaluation dependencies.
No sparse-model weights are downloaded by the setup check; FastEmbed's first
model use will need its configured weights in the later retrieval step.

## What Step 2 puts in place

| File | Responsibility |
|---|---|
| `pyproject.toml` | Direct libraries and their roles, Python requirement, optional dev/eval groups |
| `requirements.lock` | Exact resolved direct/transitive versions and file hashes |
| `config.py` | Typed, validated settings loaded from environment / `.env` / defaults |
| `.env.example` | Safe template showing supported configuration names |
| `.gitignore` | Excludes credentials, environment, caches, and generated results |
| `scripts/check_setup.py` | A repeatable import/settings check with no model construction |

A **direct dependency** is one we choose, such as LangGraph. A **transitive
dependency** is something that library needs. The manifest explains our choices;
the generated lock records the entire resolved set so another setup can install
the same versions. Hashes check that downloaded package files match that lock.

The **virtual environment** keeps these versions separate from Projects 2 and 3.
Only the manifest, lock, code, and documentation belong in Git; the environment
and generated caches can be rebuilt.

## Configuration and data flow

```text
process environment → project .env → defaults in Settings
                           ↓
                type conversion + validation
                           ↓
                settings imported by app modules
```

Environment variables take precedence over `.env`, and `.env` takes precedence
over the defaults. The file path is anchored to `config.py`, so running Python
from a different working directory does not select another project's `.env`.

Pydantic Settings converts values such as `MAX_FILES=40` into an integer and
rejects invalid limits. It also rejects `RERANK_K > RETRIEVE_K`: reranking cannot
select more evidence than retrieval supplied. A misspelled name inside `.env`
fails validation rather than silently doing nothing.

Credentials use `SecretStr` and are omitted from the settings object's
representation. That reduces accidental logging; it does not encrypt `.env`.
Provider integrations will explicitly read the required secret at their boundary.

### Credentials and model defaults

| Setting | Purpose | Needed now? |
|---|---|---|
| `GITHUB_TOKEN` | Public GitHub API reads with appropriate access | No; introduced with GitHub readers |
| `GEMINI_API_KEY` | Generation when `GEN_PROVIDER=google`; dense embeddings when `EMBED_PROVIDER=google` | No; checked with the provider integration |
| `GROQ_API_KEY` | Generation (default provider, Steps 9+) | Yes, for live answers |
| `COHERE_API_KEY` | Hosted reranking when `RERANK_PROVIDER=cohere` | No; checked with reranking |
| `LANGSMITH_API_KEY` | Optional cloud traces | No; tracing is off by default |

The configured defaults were checked against official documentation on
16 October 2026: [Gemini 3.7 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash),
[Gemini Embedding](https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001),
and [Cohere Rerank](https://docs.cohere.com/docs/rerank-overview).
They are explicit, overridable model choices; setup does not prove availability
for a particular account. Dense embeddings run locally (FastEmbed) by default, so
indexing needs no provider credentials; `EMBED_PROVIDER=google` switches to the
configured 768-dimension Gemini embeddings, whose output size is verified
against `EMBED_DIM`.

Changing an embedding model or dimension later requires an explicit index
rebuild or a separate collection. It must not silently reuse incompatible vectors.

`LANGSMITH_TRACING=false` is the application setting. The later tracing step
will deliberately connect it to the integration; importing config does not
enable cloud tracing. Keys stay empty during offline setup checks.

### Paths and budgets

Runtime paths default to this project's `data/` and `reports/`. Relative overrides
in `.env` resolve against the project directory. Importing settings creates neither
directory; the component owning a file opens it when needed.

Collection defaults match the plan: 40 files, 60 commits, 10 discussions, and 20
comments per discussion. Investigation defaults include 12 tool calls, two
retrieval-refinement rounds, one answer revision, and 120 seconds. These fields
only define validated configuration now; the relevant later steps enforce them.

## Verified environment, 16 October 2026

| Component | Tested version |
|---|---|
| CPython / platform | 3.14.6 / Windows x86-64 |
| uv | 0.13.1 |
| Pydantic / Pydantic Settings | 2.14.1 / 2.16.0 |
| LangChain Core / Google integration | 1.6.11 / 3.2.0 |
| LangGraph / SQLite checkpointer | 1.2.15 / 3.1.2 |
| Qdrant client / FastEmbed | 1.19.1 / 0.9.0 |
| Ragas / LangChain Community | 0.4.3 / 0.4.1 |
| FastAPI | 0.143.2 |

All 17 runtime import checks plus Ragas passed, including the actual reranker,
vector-store, sparse embedding, checkpoint, and tool-executor entry points.
`pip check` found no broken requirements. Configuration checks covered the
template, invalid limits, environment precedence, secret masking, and paths after
a working-directory change. Git ignore rules keep generated files and `.env`
out while allowing `.env.example` to be tracked.

**Compatibility decision:** Ragas 0.4.3 imports a Vertex AI module that LangChain
Community 0.4.2 removed. The initial install therefore passed dependency
resolution but failed `import ragas`. The eval dependency group now bounds
Community to 0.4.1, and the full setup check passes. This is recorded in the
manifest and lock rather than patched inside the installed library. See the
[upstream report](https://github.com/vibrantlabsai/ragas/issues/2745).

The resolver checks declared version requirements; importing actual entry points
checks an additional compatibility boundary that package metadata can miss.

## Updating the dependency lock

After deliberately changing the manifest, regenerate the lock with the installed
uv version, then reinstall and rerun the setup check:

```powershell
.\.venv\Scripts\uv.exe --cache-dir .cache\uv pip compile pyproject.toml --extra dev --extra eval --python .venv\Scripts\python.exe --generate-hashes --only-binary :all: --output-file requirements.lock
.\.venv\Scripts\uv.exe --cache-dir .cache\uv pip install --python .venv\Scripts\python.exe --require-hashes --only-binary :all: --requirements requirements.lock
.\.venv\Scripts\python.exe scripts\check_setup.py --with-eval
.\.venv\Scripts\python.exe -m pip check
```

Use the existing lock for normal installation. Regeneration is a deliberate
dependency change; inspect its version changes and record the check results.
See [uv's locking guide](https://docs.astral.sh/uv/pip/compile/) and
[Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
for the library mechanisms used here.

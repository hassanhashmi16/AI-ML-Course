# Project 4: CodeTrail — Build Plan

> **Trace the decisions behind the code.**
>
> **Status:** Steps 1-13 complete; reference cases, tested environment, shared contracts, GitHub readers, the cached collector, source-mapped chunks, the local vector index, hybrid retrieval with labelled reranking, the cited baseline answer, the investigator tools, the investigation graph, budgets/corrective grading/grounding, and durable checkpoints with CLI resume ready.
> **Next:** Step 14.
> **Updated:** 16 October 2026. Consolidated into **19 steps** following the user's request to match Projects 2 and 3.

## The project

Reading code shows its current behavior. Explaining why a design exists often requires tracing a change through commits, pull requests, and issues. CodeTrail follows that evidence and produces a cited explanation with an interactive timeline.

**Input:** a user-supplied public GitHub repository URL, a question, and optional file path and ref. The intended interface accepts different public repositories within the supported scope. We develop against file-scoped examples in one reference Python repository, while keeping the readers and agent repository-independent.

**Output:** an explanation, chronological timeline, inspectable source excerpts, alternatives where documented, unresolved questions, and the scope actually searched. Findings are labelled **documented**, **inferred**, or **unknown**.

**Example:** "Why does this function keep a second cache?" The app finds relevant changes, follows their discussions, checks the evidence, and explains what the record supports.

## How we work

Follow the teaching approach of [Project 2](../Project-2-RAG-Assistant/STEPS.md) and [Project 3](../Project-3-Research-Agent/STEPS.md).

- One numbered step is one meaningful piece of the system, with a result we can run or inspect.
- Execute **one step at a time**, when the user asks. No mandatory lettered substeps or extra approval turns for individual files.
- The user's 16 October instruction sets this project's granularity: group related setup, wiring, and checks together. Keep implementation focused and understandable; the earlier approximate 30-line guideline does not impose separate steps here.
- Explain new concepts before code: what problem they solve, how they work, a small example, and the relevant trade-off.
- Explain the resulting files and data flow afterward. Comment non-obvious code generously, as in the earlier projects.
- Every step below has **What / Why / How / Artifact / Check / Structure**. Verification is part of completing that step.
- Mark completed steps and record their actual checks here. Implementation begins at Step 1; this document does not count as a completed build step.

## Familiar concepts, new tools

| What we built earlier | CodeTrail approach |
|---|---|
| Custom parsing and chunking | LangChain Documents and language-aware text splitters |
| Direct embedding calls and vector SQL | Google embedding integration and Qdrant vector-store integration |
| Sparse search and handwritten rank fusion | FastEmbed sparse embeddings and Qdrant hybrid retrieval |
| Direct reranking SDK wrapper | CohereRerank through langchain-cohere |
| Provider-specific tool/message wiring | LangChain model integration, structured output, and typed tools |
| Custom agent loop and dispatcher | LangGraph StateGraph and ToolNode |
| Custom checkpoint table | LangGraph persistent SQLite checkpointer |
| Custom cross-session memory table | Separate Qdrant collection of verified findings |
| Homemade tracing | Optional LangSmith integration and local stage logs |
| Custom evaluation plumbing | pytest behavior checks and Ragas metrics |

We still design the evidence relationships, investigation strategy, scope, citation checks, and interface. Library use is explained against the mechanism it replaces.

**Supporting stack:** Pydantic/pydantic-settings, PyGithub, diskcache, FastAPI, and React/Vite. Keep existing provider credentials where possible. Select explicit model IDs and install, smoke-test, and lock compatible dependency versions during setup. Library choices were researched on 16 October 2026; no untested version numbers are presented as established.

## Concepts that matter for this project

A **commit SHA** identifies the snapshot of code being explained. Resolve a branch/tag once and use that SHA consistently; historical evidence has its own commit/date.

An **evidence record** retains source text, identity, URL, date, and relationships. A **chunk** is a smaller passage prepared for search. **Provenance** is the trail from that passage back to its original source.

**Hybrid retrieval** combines semantic matching with exact-word matching. **Reranking** improves candidate order. Exact commit/PR/issue relationships establish the historical trail; similarity helps locate relevant passages within it.

A **LangGraph node** performs an operation, **state** carries the investigation, and **edges** select the next operation. A corrective branch searches again only when it has a specific missing piece to investigate.

A **checkpoint** resumes one investigation. A **saved finding** helps a later investigation and must retain verified source references. An **idempotent write** can repeat after a crash without duplicating evidence.

## Data flow and scope

```text
GitHub URL + question + optional file/ref
  → validate and resolve snapshot
  → collect bounded code/history/discussions and cache sources
  → LangChain Documents → split → embed → Qdrant
  → retrieve → investigate through tools → grade evidence
                  ↑ retry/follow leads when needed ↓
  → synthesize → check citations and support → finalize
  → cited report + timeline → FastAPI → React
```

Start development with one reference corpus and three verified examples. This is a repeatable development fixture, not a restriction to that repository. Each user's repository/ref determines its own collected evidence, cache/index namespace, and retrieval filters. The agent can fetch and index additional evidence through the same bounded readers. Exact known IDs use direct lookups; retrieval helps find relevant text. Add another repository to evaluation to check generalization.

### Evidence rules

- Retain source IDs, content revisions, canonical URLs, source dates, repository/SHA scope, and valid code line ranges.
- Every factual explanation cites inspected evidence and an exact supporting excerpt. Quote matching and semantic support are checked separately.
- Distinguish proposals from merged changes, original intent from later commentary, and documented reasons from inference.
- Unknown means "not established within the searched scope." Missing patches, inaccessible material, pagination cutoffs, and failed calls stay visible.
- Cache source records separately from the retrieval index, graph checkpoints, and saved findings. Repeating collection/indexing/finalization must preserve stable identities.
- Enforce repository/ref filters, supported GitHub inputs, and read-only tools in application code. Treat repository text as data and keep it unexecuted.

### Operating decisions

Use configurable starting limits: 40 text files, 60 commits across selected paths, 10 PRs/issues, and 20 comments per discussion. Record what was inspected and where collection stopped; adjust these starting limits based on real runs.

Start with at most 12 tool executions, two retrieval-refinement rounds, and one answer-revision attempt, alongside wall-time and model-usage limits. Bound individual requests too; usage accounting can stop the next call but cannot undo a completed call's spend.

Use local on-disk Qdrant and SQLite checkpoints initially. One process owns the local store and one investigation runs at a time. Index manifests record model/dimension/chunking configuration. Service-backed storage and concurrent public usage are revisited at deployment.

Reranking or cloud tracing that is unavailable must be labelled accordingly. Save the actual pipeline configuration with evaluation results.

## Target structure

Files appear when their corresponding step is implemented.

```text
Project-4-CodeTrail/
  STEPS.md
  README.md
  config.py
  models.py
  cli.py
  pyproject.toml
  requirements.lock
  .env.example
  .gitignore
  github_source/       # SDK readers, normalized evidence, cache
  ingest/              # Documents, splitting, indexing
  retrieval/           # provider/store clients, search, reranking
  generation/          # structured grounded answers
  reporting/           # citation validation and report rendering
  agent/               # tools, state, graph, policy, persistence, memory, traces
  api/                 # FastAPI and public progress events
  frontend/            # React investigation workspace
  eval/                # reference cases and comparison runner
  tests/               # focused behavior checks and fixtures
  docs/                # demo cases and architecture write-up
  data/                # generated caches, indexes, checkpoints; ignored
  reports/             # generated results; ignored
```

## Build steps

### Phase A — Foundation

#### Step 1: Pick the demo repository and evidence cases [done]

**What:** Choose one public Python repository and verify three investigation questions.

**Why:** The project depends on useful recorded history. Establishing reference answers first gives us examples to build against and evaluate.

**How:** Inspect candidate repositories, then trace two documented decisions from code through commits and PRs/issues. Add one question where the available evidence is insufficient. Record the selected commit SHA, file paths, sources, expected findings, and search limitations.

**Artifact:** docs/demo-cases.md.

**Check:** The two supported explanations can be checked against real sources, and the unknown case states what was searched.

**Structure:** This is our initial development corpus and reference set. The product still accepts a user-supplied repository link and question; the chosen repository supplies repeatable demos rather than a hardcoded runtime corpus.

**Completed:** 16 October 2026. [Reference cases](docs/demo-cases.md) select `pallets/flask` at `b17bb9ed563ab2857c0db9a07ec4e6407404c7be`. Two cases trace documented context-storage and JSON-provider decisions; a third checks an unsubstantiated throughput measurement. Verified the tag-to-SHA metadata, inspected the cited sources, and recorded unavailable leads. No application code or later build step was executed.

#### Step 2: Create the project skeleton, configuration, and environment [done]

**What:** Set up the project, dependencies, secrets template, and centralized settings.

**Why:** This follows the first step of both earlier projects: make the environment and configuration predictable before adding features.

**How:** Create the package/dependency manifest, ignore rules, .env.example, and config.py. Use pydantic-settings for model IDs, paths, credentials, and budgets. Install compatible library versions in a local environment, run small import probes, and save a resolved lockfile.

**Artifact:** Project skeleton, config.py, dependency manifest/lock, and .env.example.

**Check:** The selected libraries import, settings validate, and generated data and credentials are ignored.

**Structure:** The rest of the application reads settings from one place; each library's responsibility is explained here.

**Completed:** 16 October 2026. Created `pyproject.toml`, `requirements.lock`, `.gitignore`, `.env.example`, `config.py`, `scripts/check_setup.py`, and the setup README. Built a local CPython 3.14.6 environment and installed hash-locked runtime/dev/eval dependencies using uv 0.13.1. All 17 runtime integrations and Ragas imported; actual framework entry points and a Document construction probe passed. `pip check` passed, as did configuration validation, template loading, environment precedence, secret masking, path anchoring, Python syntax, and ignore-rule checks. Resolved Ragas 0.4.3's import failure by bounding LangChain Community to 0.4.1 and regenerating the lock. No provider requests, model-weight downloads, or Step 3 implementation were part of this step.

#### Step 3: Define requests, evidence, and investigation state [done]

**What:** Describe the information passed between the collector, retriever, graph, and report.

**Why:** Shared contracts prevent each component from inventing its own incompatible representation of a source or claim.

**How:** Use Pydantic for the input and report models and typed state for LangGraph. Include repository/ref/path/question, stable source IDs, URLs, source dates, excerpts, claims, timeline events, coverage, and status. Give claims documented/inferred/unknown labels.

**Artifact:** models.py and agent/state.py.

**Check:** The manually verified example fits the schemas; an unknown finding stays distinguishable from a supported claim.

**Structure:** This combines Project 2's document/answer contracts with Project 3's explicit agent state.

**Completed:** 16 October 2026. Added `models.py` (request, snapshot, source record, supporting excerpt, claim, timeline event, coverage, and report models; the `make_source_id` helper; validators that enforce the honesty rules) and `agent/state.py` (typed LangGraph state with reducers for accumulating collections, budget counters, and a `new_state` factory), plus `scripts/check_models.py` as the repeatable check. Check: the CT-001 demo case passes through the schemas end to end; a documented claim carries its excerpt while the CT-003-style unknown stays structurally distinct; and the schemas reject a documented claim with no excerpt, an unknown claim carrying excerpts, a non-GitHub URL, a `..` path, a partial report with no stated limitation, and a misspelled field. No provider calls or later-step implementation.

### Phase B — GitHub evidence

#### Step 4: Read repository code and file history [done]

**What:** Build bounded GitHub readers for files, commits, and relevant changes.

**Why:** The app needs exact code-history relationships before semantic retrieval can help explain them.

**How:** Use PyGithub to validate a public GitHub repository, resolve the selected ref to a SHA, read a file, list its bounded history, and inspect changed-file metadata. Discover a small file set when no path is supplied. Preserve canonical URLs, code line ranges, associated PR leads, and missing-patch/rename warnings.

**Artifact:** github_source/code.py and github_source/client.py.

**Check:** A selected file and its introducing change are inspectable; file/commit limits produce a visible coverage warning.

**Structure:** These readers are the code-history equivalents of Project 3's fetch tool, implemented through an SDK.

**Completed:** 16 October 2026. Added `github_source/client.py` (authenticated PyGithub client, repository validation, ref-to-SHA resolution returning a `RepoSnapshot`) and `github_source/code.py` (`read_file`, `list_file_history`, `inspect_change`, `discover_files`; every reader is SHA-addressed and reports truncation as a visible warning), plus `scripts/check_github.py` as the live check. Check: against the pinned Flask 2.2.0 snapshot, the ref resolved to the documented SHA; `src/flask/ctx.py` was read with its canonical URL and retained blob revision (438 lines); a three-commit history bound reported "showing 3 of 34" as a warning; the newest change to the file was inspected with changed-file metadata; discovery returned a bounded deterministic file set with a warning; a missing repository and a missing ref produced clear errors. Finding during the check: slicing a PyGithub `PaginatedList` raised `IndexError` past its length, so the PR-lead lookup iterates with a manual cap instead. GitHub API reads only; no model calls. Ran on the anonymous rate limit, so a `GITHUB_TOKEN` in `.env` remains recommended before building the collector.

#### Step 5: Collect discussions and cache the evidence [done]

**What:** Follow PR and issue relationships and save a reusable evidence bundle.

**Why:** The reason for a change may be in its description, a review, or a linked issue; fetching the same material repeatedly wastes quota.

**How:** Use SDK readers for PRs, issues, conversation comments, and reviews with shared limits. Normalize the results into source records, cache with diskcache, and retain relationships, state, author/date, content revision, and fetch coverage. Collect one demo trail through these readers.

**Artifact:** github_source/discussions.py and github_source/collect.py.

**Check:** The bundle contains the expected discussion evidence, a repeat collection uses the cache, and truncated or failed reads remain visible.

**Structure:** This is our source ingestion layer. It also supplies the live readers that the agent will later use to expand an investigation.

**Completed:** 16 October 2026. Added `github_source/discussions.py` (`read_pull`, `read_issue`, `read_comments`, `read_reviews`; PR state and edit markers retained, comments keep their parent thread) and `github_source/collect.py` (diskcache-backed `Collector`: cache-first single reads and listings keyed by stable IDs, visible truncation/failure warnings, computed `Coverage`, JSON bundle export), plus `scripts/check_collect.py`. Also added the `state` field to `SourceRecord` and fixed a latent PyGithub `PaginatedList` slicing bug in `list_file_history` (islice, not `[:cap]`). Check: one demo trail collected (ctx.py + bounded history + PR #4682 with state=merged and its merge-commit lead converted to `cbebdae`, matching docs/demo-cases.md, plus 2 reviews); the repeat collection replayed with 5 hits / 0 misses and identical sources; a deliberately missing PR produced a visible warning; coverage reported incomplete with notes; the saved bundle reloaded and matched. Live GitHub reads only; no model calls.

### Phase C — Retrieval and a working RAG baseline

#### Step 6: Turn evidence into searchable documents [done]

**What:** Convert source records into LangChain Documents and split them into chunks.

**Why:** This practices Project 2's parsing and chunking concepts through standard library interfaces.

**How:** Use langchain-core Documents and language-aware splitters for Python/Markdown. Retain source IDs, repository/SHA, source kind, URL, and original text positions. Derive stable chunk identities so retrieved passages can be mapped back to exact evidence.

**Artifact:** ingest/documents.py and ingest/split.py.

**Check:** Each sample chunk maps to its original source excerpt and valid location.

**Structure:** The full evidence record supports inspection; its chunks support retrieval.

**Completed:** 16 October 2026. Added `ingest/documents.py` (`SourceRecord` to LangChain `Document`, carrying traceable identity metadata) and `ingest/split.py` (language-aware splitters for Python/Markdown, generic otherwise; character offsets plus line numbers per chunk; stable `chunk_id` from `(source_id, start, end)`), plus `scripts/check_chunks.py`. Check: 4 records (ctx.py, PR #4682, 2 reviews) produced 22 chunks (file=18, pull_request=2, review=2); every chunk is an exact substring of its record at its recorded offsets with in-bounds line numbers; re-splitting produced an identical `chunk_id` sequence; the sample chunk ctx.py L229-L256 carries "AppContext". GitHub reads replayed from the Step 5 cache; no model calls.

#### Step 7: Embed and index with Qdrant [done]

**What:** Build a persistent searchable index through the provider and vector-store integrations.

**Why:** This replaces Project 2's direct embedding calls and vector SQL with reusable interfaces.

**How:** Configure the Google embedding integration and local on-disk Qdrant through langchain-qdrant. Record model/dimension/splitter metadata, batch indexing, use stable IDs, and replace stale chunks when a cached source changes. Expose a simple ingestion command.

**Artifact:** ingest/index.py, retrieval/clients.py, and the ingest CLI command.

**Check:** The index survives restart; indexing unchanged data twice preserves counts; incompatible embedding settings require an explicit rebuild.

**Structure:** The index is the bridge from the collected corpus to retrieval. One process owns the local store.

**Completed:** 16 October 2026. Added `retrieval/clients.py` (local FastEmbed embedder behind the LangChain interface with Google selectable via `EMBED_PROVIDER`; on-disk Qdrant client; per-snapshot collection naming) and `ingest/index.py` (uuid5 point IDs from the stable chunk IDs, per-source replacement so a changed source leaves no stale chunks, a manifest recording provider/model/dimension/splitter settings, refusal on settings change without `--rebuild`, and the `python -m ingest.index` command), plus `scripts/check_index.py` and the `EMBED_PROVIDER` / `FASTEMBED_EMBED_MODEL` settings. Finding during the check: local-mode Qdrant raises inside the LangChain store's constructor validation, so collections are created explicitly, sized to the embedder's true dimension. Check: a rebuild indexed 22 points from 22 chunks (4 sources); the index survived close/reopen; re-indexing unchanged data kept 22 points; a modified source was replaced cleanly (22 - 18 + 18 points); a settings change was refused with a rebuild hint; the manifest recorded fastembed / BAAI/bge-small-en-v1.5 / dim 384 / chunk 1200-150. No model calls; the local embedding model downloaded once into the ignored `.cache/`.

#### Step 8: Add hybrid retrieval and reranking [done]

**What:** Retrieve with dense and sparse search, then rerank the candidate evidence.

**Why:** This is Project 2's core retrieval pipeline implemented through integrations rather than handwritten search/fusion mechanics.

**How:** Use FastEmbed sparse embeddings and Qdrant hybrid retrieval, then CohereRerank from langchain-cohere. Keep dense-only and hybrid modes selectable for comparison. Apply repository/SHA filters in every mode, preserve IDs, and explicitly record disabled or failed reranking.

**Artifact:** retrieval/search.py and retrieval/rerank.py.

**Check:** Semantic and symbol-heavy questions retrieve inspectable relevant sources; sources from another repository/ref are excluded.

**Structure:** The retriever returns a small ranked evidence set to either the ordinary RAG path or the agent.

**Completed:** 16 October 2026. Added `retrieval/search.py` (dense/hybrid modes, the repository + SHA scope filter applied in every mode, wide `RETRIEVE_K` candidates, retrieval scores attached) and `retrieval/rerank.py` (local fastembed cross-encoder by default, Cohere selectable, and `none`/failures return a labelled warning while keeping retrieval order), plus `scripts/check_search.py`. Collections are now created dense+sparse (hybrid-capable), pre-hybrid collections demand an explicit rebuild, and rebuild deletion moved ahead of store construction. Check: 142 points from 142 chunks (7 sources); a foreign-repository sentinel ranked first unfiltered but never surfaced through `search_evidence`; a semantic question returned ctx.py/globals.py chunks and a symbol-heavy question returned json/provider.py; every returned chunk mapped back to its record at its offsets; 20 candidates narrowed to 5 with scores; disabled and simulated-failure reranking were both labelled and kept retrieval order. No model API calls (local embedder, sparse embedder, and reranker); `check_index` re-ran green against the hybrid collection.

#### Step 9: Produce a cited baseline answer [done]

**What:** Make one retrieval pass produce a structured explanation with source references.

**Why:** A working baseline makes it possible to measure whether investigation improves on ordinary RAG.

**How:** Use the LangChain chat integration, prompt composition, and structured output with our report model. Require claim-level source IDs and excerpts. Validate citation identity, quote matching, and code locations, render the result, and add a baseline CLI command.

**Artifact:** generation/answer.py, reporting/citations.py, and the baseline CLI command.

**Check:** A known question produces a saved cited report; invented source IDs and altered quotations fail validation.

**Structure:** This is the Project 2-shaped end-to-end system that the next phase extends.

**Completed:** 16 October 2026. Added `generation/answer.py` (Groq by default via `GEN_PROVIDER`/`GROQ_GEN_MODEL` with `with_structured_output`; deterministic timeline and coverage assembly around the model's draft; report saving; the baseline CLI command) and `reporting/citations.py` (source-ID identity check, verbatim quote matching, line numbers derived from the quote's position, rejected claims recorded as issues), plus `scripts/check_answer.py`; added `langchain-groq` to the manifest and regenerated the hash-locked requirements. Check: the LocalStack question produced a saved report with a documented claim whose quote exists verbatim in PR #4682 and status=complete; an invented source ID and an altered quote were both rejected with named issues; the saved JSON reloaded as the shared `Report`; the CLI ran end to end and saved a second report. Generation ran on Groq (`openai/gpt-oss-120b`); embeddings, sparse search, and reranking stayed local.

### Phase D — Agentic investigation

#### Step 10: Expose the readers and retriever as tools [done]

**What:** Give the investigator typed tools for searching evidence and following history.

**Why:** An agent needs targeted operations with useful descriptions and compact results.

**How:** Use LangChain tool abstractions for search_evidence, read_code, list_file_history, read_change, and read_discussion. Reuse the readers already built. Inject repository/SHA from trusted run context and index newly fetched evidence before the next retrieval.

**Artifact:** agent/tools.py.

**Check:** A tool can follow a known evidence lead and return searchable, citable results within the original scope.

**Structure:** This replaces Project 3's handwritten tool schemas/dispatch plumbing while preserving familiar plain-function responsibilities.

**Completed:** 16 October 2026. Added `agent/tools.py`: five LangChain tools (`search_evidence`, `read_code`, `list_file_history`, `read_change`, `read_discussion`) closing over a trusted `ToolContext` (repository, pinned SHA, collector, index client) so repository scope is injected, never model-supplied. Read tools index newly fetched records before returning; all outputs are budgeted. Check: search returned three scoped citable source_ids; `read_discussion(4682)` made the PR searchable in the same run (absent before, found by the follow-up query); `list_file_history` to `read_change(095651b)` followed a real commit trail and included ctx.py among changed files; `read_code` returned file text with its source_id; every output stayed within budget (max 3,403 chars). No model calls; GitHub reads replayed from the Step 5 cache.

#### Step 11: Build the LangGraph investigation workflow [done]

**What:** Connect retrieval, model decisions, and tool execution into a stateful investigation.

**Why:** The next useful lookup depends on what earlier evidence reveals, which is where Projects 2 and 3 come together.

**How:** Build a StateGraph with retrieve, investigate, tool execution, evidence grading, and synthesis stages. Use framework model/tool binding and ToolNode. Start with the known question, gather evidence through supported tools, and retain the trail in explicit state.

**Artifact:** agent/graph.py and agent/nodes.py.

**Check:** A demo question follows a real multi-hop trail and produces the shared report format.

**Structure:** LangGraph takes over Project 3's custom loop; our nodes express CodeTrail's investigation strategy.

**Completed:** 16 October 2026. Added `agent/nodes.py` (investigate, tool execution with call counting and state sync, evidence grading, conditional routing, synthesis over gathered evidence) and `agent/graph.py` (StateGraph: investigate, tools, grade, investigate-or-synthesize), extended the state with `messages` (add_messages), `evidence_sufficient`, and `investigation_rounds`, added PR leads to `read_change`, and added `console.py` for Windows-safe output. Findings during the check: Groq rejects a prose reply in tool-choice mode, so the grader prompt now forbids answering and a grader failure degrades to "proceed" with a note; tool results reached the collector but not the graph state, so the tools node now syncs sources into state (the explicit trail); model quotes that drop markdown backticks are located formatting-insensitively while the stored quote is replaced by the exact source span (paraphrases still fail). Check: the LocalStack question followed a two-step trail (search_evidence then read_discussion), graded sufficient, synthesized a complete report (1 documented claim, verbatim citation against 5 inspected sources), saved and reloaded; a Windows cp1252 print crash on model punctuation was fixed by the console helper. Live Groq calls for decisions, grading, and synthesis; embeddings, search, and reranking stayed local.

#### Step 12: Add corrective retrieval, grounding, and budgets [done]

**What:** Make the workflow react to weak evidence and stop predictably.

**Why:** A retrieved passage can be related without explaining the requested decision; additional searching must also have a finite limit.

**How:** Grade relevance, missing facts, contradictions, and direct rationale. Refine the query or follow a new lead when needed. After synthesis, check semantic support separately from citation validity; allow one revision, then downgrade unsupported claims. Enforce source/tool/token/time limits and repeated-action stopping.

**Artifact:** agent/policy.py and corrective branches in agent/graph.py.

**Check:** Fixtures demonstrate a successful retry, an unsupported claim being revised/downgraded, and an exhausted budget returning an honest partial result.

**Structure:** This applies Step 38's closed-loop retrieval around the working investigation, with explicit documented/inferred/unknown outcomes.

**Completed:** 16 October 2026. Added `agent/policy.py` (tool/source/token/time budgets plus repeated-action detection, each returning a reason) and extended `agent/nodes.py`: grading is skipped when a budget is spent and repeats the reason; insufficient grades hand the missing evidence back to the investigator as guidance; `investigate` accumulates provider token usage; synthesis now runs a separate grounding pass (`ClaimSupport`) that judges whether each claim is supported by its quote, attempts one revision with reviewer feedback, and downgrades claims still unsupported into `unresolved` with status=partial. State gained `started_at` and `tokens_used`; `answer_question` accepts revision feedback. Check: fixtures proved budget stops (tool cap, repeated action) with the grader skipped, a failed grade routing back to investigation and a sufficient one routing to synthesis, an exhausted budget producing an honest partial report, and a citation-valid but semantically unsupported claim being revised then downgraded. Findings: the initial grounding judge was too strict (rejected quotes that plainly stated the reasons), so its prompt now judges substance rather than wording. The live graph regression kept one documented claim and downgraded one, status=partial, report saved and reloaded. Fixtures make no model calls; the graph regression used Groq for decisions, grading, grounding, and synthesis.

### Phase E — Persistence and observability

#### Step 13: Add persistent checkpoints and resume [done]

**What:** Save investigation progress with a LangGraph checkpointer and expose recovery.

**Why:** An interrupted investigation should continue from durable state, as Project 3 demonstrated by hand.

**How:** Attach the library SQLite saver, manage its connection lifecycle, and use application-generated thread IDs. Add CLI investigate/resume commands using supported graph invocation. Make source indexing and report finalization safe to repeat, then demonstrate process-restart recovery.

**Artifact:** agent/persistence.py and cli.py.

**Check:** Kill a fixture-driven run after a durable checkpoint and resume the same investigation without duplicated evidence.

**Structure:** The checkpointer owns saved execution state; source IDs and idempotent application writes make replay consistent.

**Completed:** 16 October 2026. Added `agent/persistence.py` (SQLite checkpointer with managed connection lifetime, application-generated thread IDs, a saved-state reader, and explicit msgpack registration for our models) and `cli.py` (`investigate` and `resume` commands; resume rebuilds the run context from the checkpoint and re-invokes the graph with `None`). `build_graph` now accepts an optional checkpointer and injectable llm/grader/judge for fixtures. Check: a fixture-driven run crashed inside the investigate node after its first tool step, leaving a durable checkpoint (tool_calls=1); fresh runtime objects resumed the same thread, finished the cited report, and replayed the trail as exactly search_evidence then read_discussion with every final source indexed exactly once. Findings: the first crash fixture targeted the grader, which is deliberately swallowed, so the crash now happens in a node without that safety net; point totals in the shared demo collection were contaminated by earlier checks, so the idempotency assertion counts per source. Fixtures make no model calls; the CLI speaks the same persistence and graph APIs exercised by the check.

#### Step 14: Add reusable findings across investigations

**What:** Recall supported findings from earlier runs without treating memory as unquestioned evidence.

**Why:** This carries Project 3's cross-session memory concept into the new system through a persistent library-backed store.

**How:** Use a separate Qdrant collection for validated findings with their source references, repository, base SHA, and source revisions. Recall matching findings as leads and revalidate their supporting evidence. Keep this separate from checkpoints.

**Artifact:** agent/memory.py.

**Check:** A second process/run recalls a supported finding; a different repository/ref cannot inherit it as fact.

**Structure:** Checkpoints resume one run. Findings help a later run investigate efficiently.

#### Step 15: Add traces and meaningful progress events

**What:** Expose what the workflow did, where it spent time, and why it stopped.

**Why:** Investigation needs an inspectable trail for debugging and useful progress for the interface.

**How:** Use optional LangSmith tracing with deliberate data-capture settings and local structured stage logs. Record durations, usage, source counts, errors, and termination. Project graph events into a small public event format without exposing hidden model reasoning.

**Artifact:** agent/observability.py and api/events.py.

**Check:** A run has linked retrieval/model/tool stages and readable progress; core operation still works without a tracing account.

**Structure:** This replaces the homemade tracing layer and prepares the event contract the API/UI will consume.

### Phase F — Evaluation and product surface

#### Step 16: Evaluate baseline versus investigation

**What:** Build a small labelled evaluation set and compare the two workflows honestly.

**Why:** The extra investigation should earn its calls and latency through useful evidence and better explanations.

**How:** Grow the verified cases into a bounded development and held-out set, including multi-hop, conflicting-history, misleading-evidence, and unknown cases. Use pytest for scope/citation/recovery/budget failures and Ragas for supported retrieval/faithfulness metrics. Compare identical snapshots, model settings, and output contracts; reset findings between evaluation runs and disclose cache conditions.

**Artifact:** eval/cases.jsonl, eval/run_eval.py, and focused tests/.

**Check:** The report shows per-case evidence retrieval, rationale correctness, unknown handling, citation validity, latency, and calls/usage. Failures remain visible; improvement is measured rather than assumed.

**Structure:** This evaluates both Project 2's retrieval quality and Project 3's agent behavior before UI polish.

#### Step 17: Serve CodeTrail through FastAPI

**What:** Expose the existing investigation runner, saved reports, resume, and progress streaming.

**Why:** The backend should make the proven workflow usable by the interface without duplicating its logic.

**How:** Add health, investigation, report lookup, resume, and a streaming response around the same runner. Manage clients/stores through application lifecycle, keep blocking SDK work off the async event loop, validate inputs, and enforce the initial single-process/single-active-run limits.

**Artifact:** api/main.py.

**Check:** The API returns the CLI's report schema, streams actual stages, retrieves saved results, and can resume an interrupted run.

**Structure:** FastAPI translates requests and events around the existing graph.

#### Step 18: Build the React investigation interface

**What:** Create the form, investigation progress, historical timeline, and evidence drawer.

**Why:** This is the showcase: someone can ask why code changed and inspect how the explanation was established.

**How:** Use React/Vite with small components. Accept repository/question/path/ref, consume the progress events, render the shared report, and open exact evidence on citation clicks. Include three prepared cases, documented/inferred/unknown labels, recoverable errors, saved-report reload/resume, and result export.

**Artifact:** frontend/ — investigation workspace.

**Check:** A visitor can run a prepared case, follow the timeline, inspect sources, and distinguish a partial result from a supported explanation.

**Structure:** The UI presents the validated report and event contracts. Historical events stay separate from the agent's execution progress.

#### Step 19: Finish the demos and project write-up

**What:** Make the finished project reproducible and easy to assess.

**Why:** The resume/showcase value comes from demonstrated behavior and clear explanations of the engineering choices.

**How:** Finalize three demos: a supported multi-hop explanation, conflicting history, and a scoped unknown. Write setup/run instructions, architecture and framework comparisons, actual evaluation findings, and known limits. Run the meaningful checks, frontend build, and bounded live smoke cases, and record the results.

**Artifact:** README.md and docs/architecture.md.

**Check:** A clean setup reaches a working demo and the documented claims match the recorded results.

**Structure:** This completes the local Project 4 milestone; roadmap Steps 39–41 cover the guardrails, packaging, and public deployment work.

## Definition of done

- The CLI and API accept a public repository/question and return a validated report tied to a pinned snapshot.
- A demonstrated investigation follows a real code → change → discussion trail through multiple tool calls.
- Supported explanations cite inspectable sources; inferences and unknowns are explicit, with search limitations.
- Process-restart recovery and reuse of findings across separate runs are demonstrated.
- The evaluation compares ordinary RAG with investigation on the same source snapshots and held-out cases, including costs and failure cases.
- The React UI shows actual progress, a historical timeline, an evidence drawer, and three reproducible examples.
- The README provides working commands, measured results, and honest limitations.

Public hosting follows the roadmap's application guardrails (Step 39), Docker (Step 40), and deployment (Step 41). Revisit service-backed storage, durable volumes, admission/concurrency controls, and provider-cost limits before claiming the app is ready for public use.

## Pitfalls to keep visible

| Pitfall | What CodeTrail should do |
|---|---|
| Related text mistaken for the actual reason | Verify the code/change/discussion relationship and support for the claim |
| Wrong snapshot or stale memory | Filter by repository/SHA and revalidate saved evidence |
| A proposal or later comment mistaken for adopted intent | Retain PR state, implementation evidence, and event dates |
| Missing or truncated history | Show the coverage gap and qualify the result |
| An agent repeats searches without progress | Stop within budgets and return the evidence gathered |
| A plausible explanation has decorative citations | Validate IDs/excerpts and separately grade semantic support |
| A tool failure appears as absence of evidence | Report the failed lookup distinctly |
| A replay duplicates stored data | Use stable identities and idempotent writes |
| A good average hides a failed case | Inspect per-case evaluation results |
| A saved demo looks like a live run | Label replayed examples and their snapshots |

## Theory summary

CodeTrail reconstructs explanations from a verifiable trail. Retrieval discovers passages; historical relationships connect them; the graph decides what to inspect next. More searching earns its cost only when it resolves a real gap. A useful result explains both what the evidence establishes and what remains uncertain.

## Research and implementation references

Reviewed while preparing this plan on 16 October 2026. These links justify tool capabilities and coverage; the project design and step boundaries are our choices. Follow the pinned version's documentation again when implementing each integration.

- [MIT Missing Semester: version control](https://missing.csail.mit.edu/2020/version-control/) — review Git's object/history model before treating commits as a meaningful trail.
- [PyGithub Repository reference](https://pygithub.readthedocs.io/en/stable/github_objects/Repository.html) and [Commit reference](https://pygithub.readthedocs.io/en/stable/github_objects/Commit.html) — supported file/history/commit-to-PR access.
- [GitHub REST API limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) — bounded calls, pagination, and rate-limit-aware operation; inspect current headers instead of assuming a fixed allowance.
- [LangChain's Google chat integration](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai) and [embedding integration](https://docs.langchain.com/oss/python/integrations/embeddings/google_generative_ai) — model/tool/structured-output and embedding interfaces.
- [Qdrant's LangChain guide](https://qdrant.tech/documentation/frameworks/langchain/) — local on-disk mode and dense/sparse/hybrid integration.
- [Cohere reranker integration](https://docs.langchain.com/oss/python/integrations/retrievers/cohere-reranker/) — the framework reranking component; avoid copying unrelated legacy chain examples.
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers), and [SQLite saver reference](https://reference.langchain.com/python/langgraph.checkpoint.sqlite) — persistent run state and its distinction from cross-thread data.
- [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming) — use the stream/event API supported by our pinned version and project it into our public event contract.
- [LangSmith tracing quickstart](https://docs.langchain.com/langsmith/observability-quickstart) — integration-based trace collection, configured deliberately.
- [Ragas context recall](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/) and [faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/) — separate retrieval completeness from support for generated claims; verify the current metrics API.
- Curriculum cross-check: [RAG](https://github.com/rohitg00/ai-engineering-from-scratch/blob/main/phases/11-llm-engineering/06-rag/docs/en.md), [advanced retrieval](https://github.com/rohitg00/ai-engineering-from-scratch/blob/main/phases/11-llm-engineering/07-advanced-rag/docs/en.md), and [agent state machines](https://github.com/rohitg00/ai-engineering-from-scratch/blob/main/phases/11-llm-engineering/16-langgraph-state-machines/docs/en.md) — checked for missing retrieval, provenance, state, checkpoint, and evaluation concepts. Library behavior is verified against the maintainers' references above.

## Progress

- Plan consolidated: 16 October 2026, using the granularity of Projects 2 and 3.
- Completed build steps: **Steps 1-13**, 16 October 2026. See [reference cases](docs/demo-cases.md), the [setup guide](README.md), the shared contracts (`models.py` / `agent/state.py`), the GitHub readers and collector (`github_source/`), the ingest and index layer (`ingest/`), retrieval (`retrieval/`), the baseline answer (`generation/` + `reporting/`), the investigator tools (`agent/tools.py`), the investigation graph (`agent/graph.py` + `agent/nodes.py`), the policy (`agent/policy.py`), and persistence (`agent/persistence.py` + `cli.py`), checked by `scripts/check_models.py`, `scripts/check_github.py`, `scripts/check_collect.py`, `scripts/check_chunks.py`, `scripts/check_index.py`, `scripts/check_search.py`, `scripts/check_answer.py`, `scripts/check_tools.py`, `scripts/check_graph.py`, `scripts/check_policy.py`, and `scripts/check_resume.py`.
- Next: **Step 14 — Add reusable findings across investigations.**


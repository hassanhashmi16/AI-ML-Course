# Project 3: Research Briefing Agent

Give it a topic. It searches the web, reads pages, takes notes, and writes a cited Markdown briefing.

```bash
python cli.py --topic "solid-state batteries"
```

Built by hand — no LangGraph — to satisfy the roadmap's Project 3 milestone:

> a multi-step agent with real tool use that can resume after a crash and remembers across sessions.

Every part of that sentence is demonstrated, not asserted: see [The two demos](#the-two-demos).

---

## Quick start

```bash
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt     # Windows
# source venv/bin/activate && pip install -r requirements.txt  # macOS / Linux

copy .env.example .env        # then paste your GEMINI_API_KEY into .env
venv\Scripts\python.exe cli.py --topic "solid-state batteries"
```

A run prints a live trace as it works, then a summary:

```
starting 'solid-state batteries'
  run 20261015-081233-d33f  |  session 'cli-demo'
  [1] -> web_search(query=solid state batteries current status...)
  [1] <- [ { "title": "Solid-State Batteries 2026: Advances...
  [2] -> fetch_page(url=https://www.bonnenbatteries.com/...)
  [2] <- ERROR: 'fetch_page' raised HTTPStatusError: Client error '403 Forbidden'
  [3] -> fetch_page(url=https://stellarix.com/...)          <- the model adapts
  ...
  [10] -> write_brief(title=Solid-State Batteries: Current Status...)

  status   done  (the agent finished)
  turns    10   tokens 45,163   notes 4
  brief    briefs/solid-state-batteries-current-status-....md
```

Note turn 2: a site blocked the fetch, the error came back as a *string*, and the model picked a different URL. Tool failures are observations, not crashes.

### Options

| Flag | What it does |
|---|---|
| `--topic` | What to research (required for a new run) |
| `--session` | Memory bucket; runs in one session remember each other (default `default`) |
| `--resume RUN_ID` | Continue a run from its last checkpoint instead of starting fresh |
| `--capture-content` | Also record prompts/replies in the trace (off by default — that's your data) |

Exit code is `0` only when a brief was written, so a shell can tell "finished" from "ran out of budget".

### Configuration (`config.py`, overridable from `.env`)

| Setting | Default | Notes |
|---|---|---|
| `GEN_MODEL` | `gemini-3.6-flash` | Override in `.env` when a model returns 503 "high demand". |
| `MAX_STEPS` | `25` | Hard ceiling on model↔tool turns. |
| `TOKEN_BUDGET` | `120000` | Ceiling on tokens per run. |
| `SEARCH_PROVIDER` | derived | `ddgs` (free, keyless) unless `TAVILY_API_KEY` is set. |

---

## File map

| File | Responsibility |
|---|---|
| `cli.py` | **Composition root.** The only place that knows about memory, checkpoints, the loop, and the brief at once. Args, live trace, memory write-back. |
| `config.py` | One source of truth for constants and the only reader of `.env`. |
| `console.py` | Makes stdout survive characters the Windows console can't encode. |
| `agent/state.py` | `AgentState` — the dict a run carries. Every value must be JSON-safe. |
| `agent/llm.py` | Talks to Gemini: system prompt, tool schemas, `thought_signature` round-trip, retries. |
| `agent/loop.py` | **The ReAct loop.** Ask the model → run what it asked → feed the result back → repeat. Owns all mutation of state. |
| `agent/policy.py` | When a run must stop and why: `done`, step budget, token budget, no-progress. |
| `agent/checkpoint.py` | Append-only snapshots of state, so a killed run can continue. |
| `agent/tracing.py` | Loads Step 31's span emitter and points it at this project. Optional by design. |
| `tools/registry.py` | The one door tools go through: schemas out, validated calls in, errors as strings. |
| `tools/web_search.py` | `ddgs` by default, Tavily when a key exists. Returns title/url/snippet only. |
| `tools/fetch_page.py` | `httpx` + `trafilatura`: fetch a page, extract the article text, cap it. |
| `tools/notes.py` | `save_note` / `read_notes` — bound to the run's state. |
| `tools/brief.py` | `write_brief` — renders the cited Markdown, derives sources from notes, ends the run. |
| `memory/store.py` | Cross-session memory: semantic facts (upserted) + episodes (appended). |
| `demo/demo_resume.py` | Kills a run mid-flight and resumes it. |
| `demo/demo_memory.py` | Two runs in one session; the second starts knowing the first's facts. |
| `STEPS.md` | The build plan this project was executed from. |

Runtime artifacts, all gitignored: `data/agent.db` (checkpoints + memory), `briefs/*.md`, `traces/*.jsonl`.

---

## How a run flows

```
cli.py
  ├─ new_state(topic, session, run_id)          ← agent/state.py
  ├─ memory.recall(session, topic)              ← facts from earlier runs
  ├─ opening message: topic + "what you know"
  └─ loop.run(state, memory, checkpoints, on_event=printer)
       └─ while True:
            ├─ policy.should_stop(state)?        ← the only exit
            ├─ llm.call_model(state)             ← CLIENT span
            ├─ registry.dispatch(tool, args)     ← INTERNAL span, named per tool
            ├─ state["messages"] += result
            └─ checkpoint.save(state)
  ├─ memory write-back (facts + episode)         ← so the next run starts smarter
  └─ report
```

Three kinds of storage, deliberately different:

| | Where | Lifetime | Purpose |
|---|---|---|---|
| **state** | RAM | one run | what this run is doing right now |
| **checkpoint** | `data/agent.db` → `checkpoints` | one run, survives process death | resume a crashed run |
| **memory** | `data/agent.db` → `memories` | forever, per session | what the agent knows |

Same file, two tables. A checkpoint *is* an `AgentState` frozen; memory is a different shape entirely (`subject`, `provenance`, `superseded_by`) and cannot rebuild a run — that's the distinction.

---

## The two demos

### 1. It survives a crash

```bash
python demo/demo_resume.py --topic "solid-state batteries" --crash-after 2
```

Launches the real CLI as a child process, **kills it** mid-run (no cleanup, no
exception handling), reads the surviving snapshot straight out of SQLite, then
resumes it:

```
>>> KILLED the process mid-run (turn 3 was in flight)

What survived on disk (read from the checkpoints table):
  run id          20261015-084348-fb33
  last snapshot   step 2
  tokens spent    3,739

PHASE 2 - resume run 20261015-084348-fb33
  [3] -> fetch_page(...)          <- the lost turn, redone
  ...
  [10] -> write_brief(...)
  status   done  (the agent finished)
```

A crash costs at most the turn in flight — never the run.

### 2. It remembers across sessions

```bash
python demo/demo_memory.py
```

Two runs, one session, related topics. The second run's opening message, read
back from its checkpoint:

```
Research topic: solid-state battery manufacturing challenges

What you already know from earlier sessions:
- QuantumScape's 24-layer solid-state lithium-metal prototype cells exceeded...
- Major automakers are targeting late-decade launches, Toyota/Idemitsu 2027-2028...
```

No model memory is involved. It is a SQLite table, a keyword match, and prompt
assembly — which is what agent memory is before anyone sells you a vector store.

---

## Tracing

Every run writes OTel-shaped spans to `traces/<trace_id>.jsonl`. Step 31's viewer
renders them unchanged:

```bash
venv\Scripts\python.exe "..\..\STEP 31\step31-tracing\trace_view.py" traces\<id>.jsonl
```

```
invoke_agent         INTERNAL  3.12s            100%
|- call_model        CLIENT    0.00s  150 tok     0%
|- tool.web_search   INTERNAL  2.56s             82%  <- slowest
|- call_model        CLIENT    0.00s  150 tok     0%
|- tool.fetch_page   INTERNAL  0.54s             17%  <- ERROR: HTTPStatusError
...
```

Spans are named per stage (`tool.web_search`, `tool.fetch_page`), so "which step
produced the poor result?" is answerable at a glance. Content capture is off by
default: spans record structure, not your prompts.

---

## Deliberate simplifications

Known edges, written down so they're choices rather than surprises:

- **No automated tests.** The demos prove behaviour end-to-end, but nothing asserts it in CI.
- **One tool call per turn.** A multi-call response has its extra calls dropped; the model re-requests them.
- **Recall is keyword + recency**, not embeddings — zero API quota, inspectable, and it degrades to "recent things" on an empty query.
- **Note subject keys are the note's first 80 characters** (a real subject would need a model call).
- **Single-threaded.** The tracer's span stack is process-global, which is fine for a CLI and would need context variables for a server.
- **A no-tool reply ends the run** rather than nudging the model to finish; the policy notes this as the next thing to improve.

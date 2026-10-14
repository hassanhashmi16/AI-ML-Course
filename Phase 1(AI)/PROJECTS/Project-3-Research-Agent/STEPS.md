# Project 3: Research Briefing Agent — Steps

## Overview

A CLI agent that takes a research topic and returns a cited Markdown briefing. You give it a subject ("the state of solid-state batteries in early 2026"); it plans a search strategy, searches the web, fetches and reads pages, records durable notes, and writes a structured brief with inline citations.

The point of this project is **not** another RAG chatbot. It is the roadmap milestone, verbatim:

> 🏁 **Project 3: a multi-step agent with real tool use that can resume after a crash and remembers across sessions.**

That means the three things Project 2 never needed — an **agent loop**, a **checkpoint store**, and a **cross-session memory store** — are the actual deliverables here. We hand-build all three, because Project 4 is where the framework (LangGraph) is applied wholesale.

**How we work through this** (same as Projects 1–2, per `project-workflow.md`):

- Each step below is tiny and produces **one named artifact**.
- We execute **one step at a time**; you tell me when to proceed.
- After each step I explain the folder structure and how it fits the system.

---

## Why this project, and how it differs from Project 2

| | Project 2 (RAG Assistant) | Project 3 (Research Agent) |
|---|---|---|
| Shape | Fixed pipeline: retrieve → fuse → rerank → answer | Open-ended loop: plan → act → observe → repeat |
| Control flow | Linear and predictable | The model decides the next step, and must know when to stop |
| State | Stateless per request | Long-lived; must survive a crash and span sessions |
| Failure mode | Bad retrieval | Loops, tool thrash, runaway cost, lost work on a crash |
| Built by hand | Retrieval (Steps 20–29) | Agent loop, checkpoint, memory (Steps 32–37) |

Project 2 built its pipeline by hand so you could defend every line. Project 3 keeps that discipline for the **agent** concepts. **Project 4** is the framework payoff — same problem, rebuilt on LangGraph. Together the three projects prove both "I understand the mechanism" and "I know the standard tool."

---

## Requirements traceability (the milestone)

| Requirement | How Project 3 delivers it | Step |
|---|---|---|
| Multi-step agent | ReAct loop: plan → tool call → observe → repeat until done | 10 |
| Real tool use | `web_search`, `fetch_page`, `save_note`/`read_notes`, `write_brief` | 3–7 |
| Resume after a crash | Full state snapshotted to SQLite every iteration; `--resume` | 11 |
| Remember across sessions | Memory store (Step 35 schema); written at end, loaded at start | 8 |
| Observability | Reuse Step 31's tracing | 16 |

---

## Stack & decisions

| Layer | Choice | Why / trade-off |
|---|---|---|
| Model | Gemini (same key/family as Projects 1–2) | One key, native function calling, already familiar from Steps 27–28. |
| Agent runtime | **Hand-rolled ReAct loop** | The learning is the loop itself. LangGraph is Project 4. |
| Tool calling | Gemini native function calling; tools are plain Python | Hand-roll the *loop*, not the wire protocol — the SDK doing the JSON is not cheating. |
| Web search | `ddgs` (DuckDuckGo) default; `TAVILY_API_KEY` optional | `ddgs` is free and keyless so the project runs for anyone; Tavily upgrades quality when a key exists. |
| Page fetch/extract | `httpx` + `trafilatura` | Same "clean text before it reaches the model" discipline as Step 21. |
| Checkpoint store | SQLite (stdlib) | Crash-safe, no server, one file to inspect. |
| Memory store | SQLite, schema from Step 35 | `subject` / `provenance` / `superseded_by` are already designed there. |
| Tracing | Reuse `STEP 31/step31-tracing/tracing.py` | The one post-Project-2 artifact that exists as real code. |
| Output | Markdown brief + numbered citations | Diffable, portable, no UI needed yet. |

**Reuse vs build (the tiered rule).**
- **Reuse:** Step 31 tracing, Step 35's memory *schema* (as design), and the project skeleton conventions from Projects 1–2.
- **Build:** the agent loop, the checkpoint store, the memory read/write logic, and every tool.
- Nothing in the agent layer is imported. It is written once, here, so Project 4 can replace it with LangGraph and you can explain the difference out loud.

> **Note on prior artifacts:** Steps 32–37 currently exist as `.md` notes only (no code folders on disk). Where a step references "reuse from Step 35/37," it means *reuse the design*; if those artifacts are later added, we lift the code instead.

---

## System architecture

```
        ┌─────────────────────── ReAct loop (per run) ────────────────────────┐
        │                                                                     │
topic ──►  load memory ──► plan ──► [ model call ] ──► tool call ──► observe ─┐│
        │                            ▲                                     │ │
        │                            └─────────────────────────────────────┘ │
        │                every iteration: snapshot state ──► checkpoints(SQLite)│
        └───────────────────────────────────────────────┬────────────────────┘
                                                         │ done
                                                         ▼
                                          write brief ──► briefs/<slug>.md
                                                         │
                                       extract durable facts ──► memory(SQLite)
```

Data flow in words: a topic enters, relevant memory is loaded into context, and the model produces a plan and then, turn by turn, either **calls a tool** (search / fetch / note / write) or **declares it's done**. After **every** iteration the entire state is snapshotted to SQLite, so a crash loses at most one step. When the model finishes, the notes are assembled into a cited Markdown brief, and the salient facts are written back to memory so the next session starts smarter.

---

## Directory structure (target)

```
Project-3-Research-Agent/
├── STEPS.md                  # this file
├── README.md                 # how to run it + demo transcripts
├── requirements.txt
├── .env.example              # GEMINI_API_KEY, optional TAVILY_API_KEY
├── .gitignore
├── config.py                 # one source of truth: model, budgets, paths
├── cli.py                    # entry point: --topic / --resume / --session
├── agent/
│   ├── state.py              # the AgentState schema (the loop's contract)
│   ├── llm.py                # Gemini client wrapper (function calling)
│   ├── loop.py               # the ReAct loop
│   ├── checkpoint.py         # crash-resume store
│   └── policy.py             # termination + budget guards
├── tools/
│   ├── registry.py           # tool schemas + dispatch
│   ├── web_search.py         # ddgs / Tavily
│   ├── fetch_page.py         # httpx + trafilatura
│   ├── notes.py              # save_note / read_notes
│   └── brief.py              # write_brief (Markdown + citations)
├── memory/
│   └── store.py              # cross-session memory (Step 35 schema)
├── data/
│   └── agent.db              # checkpoints + memory (SQLite, gitignored)
├── briefs/                   # output briefs (gitignored)
└── demo/
    ├── demo_resume.py        # kill mid-run, resume
    └── demo_memory.py        # session 1 saves, session 2 recalls
```

---

## Phases & steps

Each step: **What** (one line), **Why** (engineering reasoning), **How** (approach), **Artifact** (the named deliverable).

### Phase A — Skeleton & the loop's contract

#### Step 1: Project skeleton, config, requirements

**What:** Create the folder, `requirements.txt`, `.env.example`, `.gitignore`, and `config.py`.
**Why:** One source of truth for the model name, budget caps, and paths — the same rule Project 2 followed ("never scatter constants across files").
**How:** `config.py` loads env via `dotenv` and exposes `GEN_MODEL`, `MAX_STEPS`, `TOKEN_BUDGET`, `DB_PATH`, `BRIEFS_DIR`, `SEARCH_PROVIDER`.
**Artifact:** `config.py`, `requirements.txt`, `.env.example`, `.gitignore`.

#### Step 2: Agent state schema

**What:** `agent/state.py` — a `TypedDict` (`AgentState`) describing everything the loop carries.
**Why:** The state is the loop's contract **and** the object the checkpoint serializes. Nail its shape first and the rest of the project has one place to agree on.
**How:** Fields: `topic`, `session_id`, `run_id`, `plan`, `messages`, `notes`, `sources`, `step`, `token_usage`, `status`, `done`. Keep every value JSON-serializable so it can be snapshotted as-is.
**Artifact:** `agent/state.py`.

### Phase B — Tools (real tool use)

#### Step 3: Tool registry & schemas

**What:** `tools/registry.py` — a `TOOLS` map of `name → {schema, fn}` plus `dispatch(name, args)`.
**Why:** The loop must never hardcode a tool. A registry keeps the loop tool-agnostic, and the JSON schema is exactly what the model is shown (Step 32.1). Tool descriptions written *for the model* is Step 32.5's whole lesson ("bad tools cause bad agents").
**How:** Each tool = a plain function + a JSON schema (`name`, `description`, `parameters`). `dispatch` validates args and calls the function, returning a compact string result.
**Artifact:** `tools/registry.py`.

#### Step 4: `web_search` tool

**What:** `tools/web_search.py` — `web_search(query, k)` returning `[{title, url, snippet}]`.
**Why:** This is the agent's door to the outside world. It must be free by default so the project runs without extra signup, and it must return *compact* results — dumping raw HTML into the window is the fastest way to blow the context budget.
**How:** `ddgs` for search; if `TAVILY_API_KEY` is set, use Tavily instead. Truncate snippets; never return page bodies here (that is `fetch_page`'s job).
**Artifact:** `tools/web_search.py`.

#### Step 5: `fetch_page` tool

**What:** `tools/fetch_page.py` — fetch a URL, extract its main text, return a truncated body.
**Why:** Raw HTML is mostly markup; feeding it to the model wastes tokens and adds noise. Extracting clean text is the Step 21 discipline ("garbage in breaks everything downstream"), now applied to live web pages instead of a corpus.
**How:** `httpx.get` → `trafilatura.extract` (readability) → cap to N characters; record the URL as a source so the brief can cite it.
**Artifact:** `tools/fetch_page.py`.

#### Step 6: Notes tools

**What:** `tools/notes.py` — `save_note(text, source_url)` and `read_notes()`.
**Why:** The brief is assembled from notes, and notes are what survive a crash. Writing facts down as the agent goes — instead of holding everything in the message history — is the central context-engineering move (Step 35.4: offload state to storage).
**How:** Append `{text, source_url, created_at}` to `state["notes"]`; each note carries its source so citations are free later. `read_notes` returns the current list.
**Artifact:** `tools/notes.py`.

#### Step 7: `write_brief` tool

**What:** `tools/brief.py` — assemble notes + sources into a cited Markdown brief written to `briefs/<slug>.md`.
**Why:** This is the terminal action. Constraining it to a schema (Step 32.6) forces the model to produce a *structured* brief (title, sections, points) rather than a wall of text, and it makes the output self-citing.
**How:** The model passes `{title, sections: [{heading, points}], sources_used}`; render numbered citations and a sources section; write the file and record its path in state.
**Artifact:** `tools/brief.py`.

### Phase C — Cross-session memory

#### Step 8: Memory store

**What:** `memory/store.py` — a SQLite store using Step 35's schema (`subject`, `provenance`, `superseded_by`, `created_at`) with `write_fact` and `search`.
**Why:** This is the "remembers across sessions" requirement. It is the piece that makes session 2 smarter than session 1, and it lives outside the context window by design.
**How:** Semantic facts upserted on `(session, subject)`; episodic notes appended with timestamps; a keyword-plus-recency read policy (`search(query, k)`) so it runs with zero extra API quota; load the top-k relevant facts into context at loop start.
**Artifact:** `memory/store.py`.

### Phase D — Agent core (multi-step + crash-resume)

#### Step 9: LLM wrapper

**What:** `agent/llm.py` — one function `call_model(state) -> tool_call | final` using Gemini function calling.
**Why:** Isolate the single place the model is invoked. This is the seam that makes the agent testable, and the exact spot Project 4 will swap for LangGraph's model node.
**How:** Send the system prompt (agent role + stop condition), the message history, and the tool schemas from the registry; parse either a function call or a final text answer.
**Artifact:** `agent/llm.py`.

#### Step 10: The ReAct loop

**What:** `agent/loop.py` — call model → if it requested a tool, dispatch it and append the observation → repeat until done or budget.
**Why:** This is the project and the milestone. A plain `while` loop makes the "reason + act" cycle visible, which is the entire point of hand-rolling it instead of importing it.
**How:** Iterate over `state`; each turn appends to `messages` and increments `step`; delegate stopping to `policy` (Step 12) and snapshot to `checkpoint` (Step 11) after every turn.
**Artifact:** `agent/loop.py`.

#### Step 11: Checkpoint store

**What:** `agent/checkpoint.py` — write the full state to SQLite after every iteration; `load(run_id)` to resume.
**Why:** "Resume after a crash" is a named requirement, and it doubles as inspectability and time-travel. The design is deliberately the same idea as LangGraph's checkpointer (Step 34.5) — you are building the thing the framework gives you, so you recognize it in Project 4.
**How:** Table `checkpoints(run_id, step, state_json, created_at)`; `save(state)` each turn; `--resume <run_id>` loads the last snapshot and continues the loop from `step+1`.
**Artifact:** `agent/checkpoint.py`.

#### Step 12: Termination & budget policy

**What:** `agent/policy.py` — decide when the agent must stop: max steps, token budget, no-progress detection, or an explicit done signal.
**Why:** Agents fail by looping and burning money (Step 33.6). A cheap, explicit guard is what turns a demo into something you'd leave running.
**How:** `should_stop(state) -> (bool, reason)` checks counters and a repeated-tool-call signature (same tool + same args twice ⇒ no progress).
**Artifact:** `agent/policy.py`.

### Phase E — Interface, proofs, and write-up

#### Step 13: CLI entry point

**What:** `cli.py` — `python cli.py --topic "..." [--resume RUN_ID] [--session NAME]`.
**Why:** This is what you actually run and demo; it also wires the four moving parts (memory → loop → brief → memory) into one flow.
**How:** `argparse`; load memory for the session, run the loop, write the brief, then write new facts back to memory. Print a live trace of each step.
**Artifact:** `cli.py`.

#### Step 14: Crash-resume demo

**What:** A reproducible demo that starts a run, kills the process mid-loop, and resumes it to completion.
**Why:** The milestone says "resume after a crash." A demo proves it instead of asserting it — and it's the clip you show in an interview.
**How:** A fault-injection flag (`--crash-at N`) raises after N checkpoints; re-run with `--resume <run_id>` and show it continues from `step N`.
**Artifact:** `demo/demo_resume.py` (+ transcript in README).

#### Step 15: Cross-session memory demo

**What:** Run 1 researches a topic and writes facts; run 2 on a related topic recalls them and says so.
**Why:** Proves memory genuinely lives outside the process, the same way Step 35's two-session demo did — but now inside a real agent.
**How:** Two CLI invocations with the same `--session`; print the facts loaded at the start of run 2.
**Artifact:** `demo/demo_memory.py`.

#### Step 16: Tracing hook

**What:** Wrap model calls and tool calls with Step 31's tracer.
**Why:** See what the agent actually did — the span hierarchy makes a bad run debuggable. This is the one place we reuse real prior code.
**How:** Import `step31-tracing/tracing.py`; emit a span per model call and per tool call, carrying `gen_ai.*` attributes.
**Artifact:** traced `agent/llm.py` + `tools/registry.py`.

#### Step 17: README + architecture write-up

**What:** `README.md` with run instructions, the architecture diagram, and the two demo transcripts.
**Why:** Makes the work legible to someone who didn't watch you build it — and it seeds the Step 42 case study.
**Artifact:** `README.md`.

---

## Definition of done

- `python cli.py --topic "..."` produces a cited Markdown brief in `briefs/`.
- Killing the process mid-run and re-running with `--resume` finishes the same brief.
- A second session on a related topic demonstrates recalled facts.
- The agent stops on its own (no infinite loop) under the budget policy.
- README explains the architecture and links both demo transcripts.

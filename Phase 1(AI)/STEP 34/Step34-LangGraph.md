# Step 34: LangGraph

> **Covers:** the reframe that makes agents debuggable — your agent *is* a state machine, so make it an explicit graph instead of a `while True:` loop — plus the library that implements it: typed state with reducers, nodes as functions, static vs. conditional edges, checkpointing and resume, interrupts for human approval, streaming, subgraphs and fan-out, and time-travel. This is the first framework in the course, and it earns its place by giving you something you cannot hand-roll cheaply: **durable state.**

---

## The Problem

You ship the tool-calling loop from Step 32. It works for three turns, then something goes wrong: a tool returns a 500, the user changes their mind mid-task, or the model is about to do something it should ask permission for. Your `while True:` loop has **no hooks.** You can't pause it, you can't rewind it, and you can't resume it — it either worked or it didn't.

The moment you ship past a demo, that loop is a black box. LangGraph's answer is a reframe: **the agent was always a state machine** — system prompt + message history + pending tool calls + next action. Write that machine down explicitly (nodes for "the model thinks", "a tool runs", "a human approves"; edges for the transitions), and you get the hooks for free.

---

## Foundational Concepts

### Not an "agent framework" — a graph runtime

LangGraph is not "here's an `AgentExecutor`, good luck." It's a **graph runtime** with first-class **state**, **persistence**, and **interrupts**. The agent loop becomes something you *draw*, not something you hand-write.

### Three things make a graph

1. **State** — a typed dict (`TypedDict` or a Pydantic model) that flows through the graph. Every node receives the whole state and returns a **partial update**.
2. **Nodes** — plain functions `state -> partial_state`. Each is one discrete step: call the model, run tools, summarise.
3. **Edges** — transitions. **Static** edges go one place; **conditional** edges call a router function `state -> next_node` so the graph can branch on model output.

You then **`compile()`** the graph — which binds the topology, attaches a checkpointer, and returns a runnable you invoke with an initial state and a `thread_id`.

### The four superpowers (this is the actual value)

| Superpower | What it buys |
|---|---|
| **Checkpointing** | state is saved after every node → **resume from where it failed** |
| **Interrupts** | pause before a node → **a human can approve or reject** |
| **Streaming** | per-node deltas → a UI that shows *"thinking… calling search… got it…"* |
| **Time-travel** | the full checkpoint log → **replay or fork from any step** |

None of the four is about the graph's *shape*. They're about state being explicit and serialized — which is why "draw your loop" is worth doing even before you want them.

### Threads

A **`thread_id`** scopes every checkpoint for one session. Same id → the graph picks up where it left off. **That single string is how "resume after a crash" and "remember across sessions" (Project 3) actually work.**

---

## 34.1 State Schema (TypedDict)

**Motivate.** The state is the interface between every node. Get it minimal and typed, or your nodes become an argument-passing mess.

**Define.** One `TypedDict` with every field a node might read or write.

```python
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]   # reducer: APPEND, not overwrite
    plan: list[str]                           # task-specific fields hoisted up
    budget: int                               # a call counter (Step 33.5)
```

**Rule of thumb.** Hoist task-specific fields (`plan`, `budget`, `retrieved_docs`) to the top level — don't stuff everything into `messages`. And **every list field needs a reducer** (34.7), or you'll lose data silently.

---

## 34.2 `StateGraph` & `compile()`

**Motivate.** You need somewhere to declare the topology, and something that turns it into a runnable.

**Define.** `StateGraph(State)` is the builder; `.compile(...)` is the finisher.

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

graph = StateGraph(State)
graph.add_node("agent", agent_node)
graph.add_node("tools", tool_node)
graph.set_entry_point("agent")
graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "agent")

app = graph.compile(checkpointer=MemorySaver())   # ← never ship without this
```

`compile()` binds the topology and returns a runnable `app`. It also takes `checkpointer=` and `interrupt_before=`/`interrupt_after=` — those three arguments are where the superpowers come from.

**Rule of thumb.** Compile once, at import; invoke many times with different `thread_id`s.

---

## 34.3 Nodes as Functions

**Motivate.** A node that mutates state in place, or that does three jobs, breaks checkpointing and reasoning.

**Define.** A node is `(state) -> partial_update`. LangGraph merges the return into state through the field's reducer.

```python
def agent_node(state: State) -> dict:
    response = llm.invoke(state["messages"])
    return {"messages": [response]}       # a PARTIAL update, not the whole state

def should_continue(state: State) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END
```

**Why the ReAct loop is four nodes:** `agent` (call the model) → conditional edge (tools, or END) → `tools` (execute the calls) → static edge back to `agent`. That's the whole Thought→Action→Observation loop **with checkpointing, interrupts, and streaming**, in about 40 lines.

**Rule of thumb.** One node, one job. If a node does two things, split it — the split *is* the observability.

---

## 34.4 `add_edge` vs. `add_conditional_edges`

**Motivate.** Most graphs should be readable rails with a few forks. Make every edge conditional and you've built a state machine nobody can reason about.

| | Use when | Example |
|---|---|---|
| **`add_edge(a, b)`** | the next step is always the same | `tools → agent` |
| **`add_conditional_edges(a, router, mapping)`** | the next step depends on state (usually model output) | `agent → tools` or `END` |

**Rule of thumb.** Prefer linear chains with *occasional* branches. "Every edge is conditional" is a smell — it usually means you haven't decided what the workflow actually is (Step 33).

---

## 34.5 Checkpointer / Persistence

**Motivate.** No checkpointer means no resume, no interrupt, no time-travel, and no memory across sessions. It is the single argument that turns a toy into a system.

**Define.** After each node, the runtime serializes the state and writes it to the checkpointer, keyed `(thread_id, checkpoint_id)`.

```python
config = {"configurable": {"thread_id": "user-42"}}
app.invoke({"messages": [HumanMessage("how tall is K2?")]}, config)
# ...later, even after a crash, in a new process:
app.invoke({"messages": [HumanMessage("and Everest?")]}, config)   # same thread → remembers
```

- `MemorySaver` — tests only. Dies with the process.
- **SQLite / Postgres / Redis** — anything that must survive a restart.

**The trap:** checkpointing only conversation turns leaves tool state, memory writes, and counters unrecoverable. **The whole state must serialize** — which means nodes must be deterministic (34.9's caveat).

**Rule of thumb.** Choose the checkpointer *before* you build, not after. Postgres is the natural fit here — you already run one.

---

## 34.6 Streaming & Human-in-the-Loop Interrupts

**Motivate.** Two of the four superpowers, and both are about the same thing: not making the user wait for a black box.

**Streaming.** `app.stream(state, config, stream_mode=...)`:

| mode | yields | for |
|---|---|---|
| `"updates"` | `{node_name: delta}` per node | a UI showing *which step* is running |
| `"messages"` | tokens from inside model nodes | token-by-token text |
| `"values"` | full state snapshots | evals and debugging |

**Interrupts.** Pause *before* a node runs:

```python
app = graph.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["tools"],     # stop before any tool call
)

state = app.invoke({"messages": [HumanMessage("delete the prod database")]}, config)
# state["__interrupt__"] is set. Inspect the proposed tool calls.
app.invoke(Command(resume=True), config)                    # approved
# or, rejected:
app.update_state(config, {"messages": [AIMessage("Blocked by reviewer.")]})
```

The state, the checkpoint, and the thread all survive the pause — nothing lives in memory except during execution.

**Rule of thumb (the important one):** **interrupt *before* the side effect, never after.** Approvals go on the edge *into* a dangerous node, so you can cancel before harm. Validation goes on the edge *out of* the model, so you reject bad calls cheaply.

---

## 34.7 Reducers — How State Fields Merge

**Motivate.** This is the only subtle thing in the library, and forgetting it is the most common LangGraph bug.

**Define.** A **reducer** is the function that combines the current state with a node's update: `(old, new) -> merged`. The default is **overwrite**. So a list field with no reducer gets *replaced* by the latest node's value — silently losing everything before it.

```python
from typing import Annotated
from operator import add
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]   # append (and handle message ids)
    docs:     Annotated[list, add]            # plain list append
    scratch:  str                             # no reducer → overwrite (fine)
```

**Why it bites:** if two nodes both write `messages` and you forgot `Annotated[list, add_messages]`, the **second wins and you lose half the turn** — with no error. Reducers also decide how **parallel** branches merge, so the same mistake breaks fan-out.

**Rule of thumb.** Any field that should **accumulate** needs a reducer. If you ever write `state["x"].append(...)` inside a node, you probably wanted a reducer instead.

---

## 34.8 Subgraphs & `Send` — Nesting and Fan-Out

**Motivate.** Real systems are graphs inside graphs, and some steps need to run *several* things at once.

**Define.**

- **Subgraph** — a compiled graph used as a node inside another graph. The outer graph sees one node; the inner one keeps its own state and its own checkpoints. This is how supervisor-worker systems are built: a supervisor graph routing into per-domain worker subgraphs.
- **`Send`** — a node returns `Send(node_name, state)` to spawn **N parallel executions** of a target node; their outputs merge through the state reducers (34.7). This is how Step 33's **orchestrator-workers** and **parallelization** patterns are expressed in LangGraph — without any threading code.

**Rule of thumb.** Reach for `Send` when the fan-out count is known at runtime (one per retrieved peak, one per file to check). Reach for a subgraph when a subsystem deserves its own state and tests.

---

## 34.9 Time-Travel: Replay and Fork

**Motivate.** "What if the model had picked the other tool?" is the best debugging question, and you can only ask it if state was saved.

**Define.** The checkpoint log is queryable and re-enterable:

```python
history = list(app.get_state_history(config))   # every checkpoint, newest first
for snapshot in history:
    print(snapshot.values["messages"][-1].content[:80], snapshot.config)

app.stream(None, history[3].config, stream_mode="values")   # replay from 3 steps back
```

Passing `None` as input **replays** from that checkpoint; passing a value **forks** (appends then continues). That's how you reproduce a bad run without re-running the whole conversation — and how you turn a production trace (Step 31) into a regression test.

**The caveat that makes it work: determinism.** Resume assumes a node given the same input produces the same update. Wall-clock time, random seeds, and live API calls all violate that — **capture them in state**, or two "identical" runs diverge and time-travel lies to you.

**Rule of thumb.** Time-travel is a debugger and a test harness, not a feature. Use it to replay a failure; make nodes deterministic so replaying means something.

---

## Pitfalls

1. **No checkpointer.** No resume, no interrupt, no time-travel, no cross-session memory. The most common way to build a LangGraph toy.
2. **Forgetting `add_messages`.** The message list overwrites instead of appending, and half the turn vanishes with no error.
3. **Checkpoints too small.** Saving only the conversation leaves tool state and counters unrecoverable.
4. **Non-deterministic nodes.** Uncaptured clock, randomness, or live API calls make resume and time-travel produce different states.
5. **Interrupting *after* the side effect.** By then the damage is done — approvals must gate the edge *into* a dangerous node.
6. **Every edge conditional.** An unreadable state machine. Prefer linear rails with occasional branches.
7. **Stuffing everything into `messages`.** Hoist `plan`, `budget`, and domain fields to the top level so they're inspectable and reducer-controlled.
8. **`MemorySaver` in production.** It's for tests; it dies with the process, taking your "durable" state with it.
9. **Mutating state in place inside a node.** Return a partial update and let the reducer merge; in-place edits fight checkpointing.

---

## Quick Reference

| Goal | How |
|---|---|
| Declare the state | `class State(TypedDict)` with a reducer on every accumulating field |
| Build a node | a function `(state) -> partial_update`; one job each |
| Always-next step | `add_edge(a, b)` |
| Branch on state | `add_conditional_edges(a, router_fn, {name: node})` |
| The ReAct loop | `agent → (router) → tools → agent`, `END` when no tool calls |
| Survive a crash | `compile(checkpointer=PostgresSaver(...))` + a stable `thread_id` |
| Pause for a human | `compile(interrupt_before=["tools"])`, resume with `Command(resume=True)` |
| Stream progress | `app.stream(state, config, stream_mode="updates")` |
| Fan out | a node returns `Send(node, state)`; outputs merge via reducers |
| Nest a system | compile a graph and add it as a node (subgraph) |
| Debug a bad run | `get_state_history(config)`, then replay or fork from a checkpoint |

---

## Theory Summary

- **An agent is a state machine; LangGraph just makes it explicit.** The loop you hand-wrote in Step 32 becomes nodes and edges, and the explicitness is what makes it debuggable.
- **State is the interface.** Typed, minimal, with a reducer per accumulating field. Reducers are the one genuine subtlety — get them right and everything else composes.
- **The value is durable state, not the graph shape.** Checkpointing, interrupts, streaming, and time-travel all fall out of serializing state after every node. That's why this library earns its place after two steps of hand-rolling.
- **A `thread_id` is a session.** Same id → resume and remember. That is literally how Project 3's "resume after a crash, remember across sessions" is implemented.
- **Interrupt before the side effect, never after.** The single rule that makes human-in-the-loop safe rather than decorative.
- **Determinism is what makes resume and replay honest.** If a node can't be replayed to the same result, time-travel tells you a story instead of the truth.

---

## Deliverable

**`Phase 1(AI)/STEP 34/step34-langgraph/`**

A **four-node ReAct agent graph** wired to Project 2's own capabilities — this is the bridge into Project 3.

- **`graph.py`** — the full graph:
  - `State` as a `TypedDict` with `add_messages` on messages **plus a second accumulating field with a custom reducer**, so 34.7 is demonstrated rather than asserted;
  - `agent` node → conditional edge (tools or `END`) → `tools` node → static edge back;
  - tools = Project 2's `list_peaks` and `lookup_peak` (Step 12) plus `search_corpus`;
  - `compile(checkpointer=...)` with a real **SQLite** checkpointer (no server needed) and `interrupt_before=["tools"]`;
  - a **scripted model node** by default so the whole thing runs with **zero API quota**; `--live` swaps in the real Gemini client.
- **`demo.py`** — walks the four superpowers end to end:
  1. run a turn → hits the **interrupt** before the tool call;
  2. **approve** and resume with `Command(resume=True)`;
  3. run a second turn on the **same `thread_id`** to show it **remembers**;
  4. **time-travel** — list the checkpoint history and replay from two steps back.

**Design notes:** the scripted model keeps the artifact runnable offline, exactly as in Steps 31 and 33 — the *graph mechanics* are the subject, and the model call is one node you swap at a single point. And the tools are Project 2's real ones, because the next thing you build (Project 3) is this graph with a real model and more tools.

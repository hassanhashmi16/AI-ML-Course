# Step 36: Multi-Agent Systems (CrewAI)

> **Covers:** CrewAI's three primitives (Agent, Task, Crew) and how they compile into separate system prompts; the role-goal-backstory pattern and why it works; wiring tools and delegation; memory (the four types tutorials still describe, and the unified `Memory` that replaced them); sequential vs. hierarchical processes and the planner; **when multi-agent loses to one good agent** — cost, latency, error compounding, and the two context principles that decide it; and Crews vs. Flows. The honest version of this step is that multi-agent is the easiest architecture to build and the easiest to get wrong.

---

## The Problem

You have one job with three distinct skills: research something, analyse it, write it up. A single agent with twelve tools can technically do all three, and it will drift — the prompt that makes it a good researcher makes it a worse writer, and by the third task its context is a pile of everything it has ever touched.

Roles look like the fix: give each step its own agent with its own focused prompt. That is the promise of a "crew."

The catch is the part most tutorials skip: **the moment you split the work, you split the context too.** Each agent is a separate context window with its own system prompt. What one agent decided is invisible to the next unless something deliberately passes it across. That is where multi-agent systems break, and most of this step is about it.

---

## Foundational Concepts

### A crew is an org chart, not a brain

CrewAI gives you three objects:

| Object | What it is |
|---|---|
| **Agent** | one role: `role`, `goal`, `backstory` + `llm`, `tools` |
| **Task** | one unit of work: `description`, `expected_output`, `agent`, `context` |
| **Crew** | the assembly: `agents`, `tasks`, `process` |

Put them together and a **Crew** is an organisation: each agent a specialist with a job description, each task a work order assigned to one of them, and a **process** deciding who runs when.

### Each agent is its own context window

This is the load-bearing fact (Step 35.5).

- An agent's `role` / `goal` / `backstory` become **its system prompt**.
- It sees **its own task**, plus whatever is listed in that task's `context`.
- It does **not** see other agents' reasoning, tool calls, or mistakes. Ever.

So "multi-agent" does not mean one smarter agent. It means several narrower agents who can only communicate through whatever you explicitly hand between them. Everything below follows from that.

---

## 36.1 Agent, Task, Crew

**Motivate.** You need somewhere to declare who does what, in what order, and what each of them has been given to work from.

**Define.** Three objects, configured in code or in JSONC/YAML.

```python
from crewai import Agent, Task, Crew, Process

researcher = Agent(
    role="Mountain Data Researcher",
    goal="Find verifiable facts about the 14 eight-thousanders",
    backstory="You are meticulous about sources and never state a fact without one.",
    tools=[search_tool],
    allow_delegation=False,
    max_iter=20,                      # hard stop, so a stuck agent can't loop forever
)

research = Task(
    description="Find the first-ascent date and team for {peak}.",
    expected_output="First ascent date, climbers, and the source.",
    agent=researcher,
)

crew = Crew(
    agents=[researcher],
    tasks=[research],
    process=Process.sequential,
    verbose=True,
)
result = crew.kickoff(inputs={"peak": "K2"})
```

The **Task** fields are worth reading closely, because they are the interface:

| Field | Why it matters |
|---|---|
| `description` | what to do |
| `expected_output` | the contract — without it the agent invents a shape |
| `agent` | who owns it |
| **`context`** | **which other tasks' outputs this task may see** — the only deliberate channel between agents |
| `output_file` / `output_pydantic` | where the result goes, and in what shape |
| `guardrail` | a validation function the output must pass |

`kickoff()` returns a `CrewOutput` with `raw`, `json_dict`, `pydantic`, `tasks_output` (every task's output) and `token_usage`.

**Rule of thumb.** `context=[other_task]` is the **only** place cross-agent knowledge flows. If a task needs to know something, list it. Assuming it "will already know" is the most common CrewAI bug there is.

---

## 36.2 Role, Goal, Backstory

**Motivate.** These three strings are the whole of an agent's system prompt — the cheapest and highest-leverage thing you configure.

**Define.**

| Field | Answers | Goes wrong when |
|---|---|---|
| **`role`** | what this agent *is* | written as a job title, adds nothing |
| **`goal`** | what it optimises — its decision rule | written vaguely, so it optimises nothing |
| **`backstory`** | the priors and tone it carries | padding, or a personality that fights the task |

**Show.**

```python
# WEAK - tells the model nothing it wasn't already assuming
role="Data Researcher",
goal="Research things well",
backstory="You are a good researcher.",

# STRONG
role="Mountain Data Researcher",
goal="Find verifiable facts about the 14 eight-thousanders. "
     "Prefer Wikipedia and published expedition records. "
     "Never state a date without a source.",
backstory="You are meticulous. You have been burned before by a "
           "second-hand claim, and now you check the primary record first.",
```

Same three fields, completely different agent. The second one says *where to look* and *what to refuse to do* — that is Step 35's "right altitude" in practice: concrete enough to guide behaviour, without becoming a brittle pile of if/else.

**Rule of thumb.** Write the `goal` as a decision rule, not a wish — "prefer X, never Y". Use the `backstory` to carry one working prior, not personality filler.

---

## 36.3 Tools and Delegation

**Motivate.** An agent with no tools can only talk. But every tool you give it costs tokens on every call and adds another way to choose wrong (Step 35.1).

**Define.**

```python
from crewai_tools import SerperDevTool, WikipediaTools

researcher = Agent(
    role="...", goal="...", backstory="...",
    tools=[SerperDevTool(), WikipediaTools()],   # attached at the agent level
    allow_delegation=True,                       # may hand work to crew colleagues
    function_calling_llm="gpt-4o-mini",          # cheap model for tool calls
)
```

Three knobs worth knowing:

- **`tools`** — CrewAI's own toolkit, LangChain tools, or your own.
- **`allow_delegation`** — **off by default.** Switched on, an agent can ask a *colleague* to do something. Powerful, and a common source of loops and runaway cost.
- **`function_calling_llm`** — split the model: a small cheap one for the mechanics of emitting tool calls, a strong one for the reasoning.

Also worth knowing: `allow_code_execution` and `code_execution_mode` are **deprecated**, and `CodeInterpreterTool` has been removed from `crewai-tools`. For sandboxed code execution, use a dedicated service (E2B, Modal) — do not hand an agent a shell and hope.

**Rule of thumb.** Give each agent the **smallest** tool set that covers its task, and prefer specific tools to general ones. If two tools could plausibly handle a request, the agent will sometimes pick the wrong one — and delegation multiplies that.

---

## 36.4 Memory

**Motivate.** A task's output should be available to a later task, and to tomorrow's run. Without memory, every run starts from zero.

**Define: this changed, and most tutorials are stale.** Older CrewAI docs describe **four** memory types. As of CrewAI v1.15 (docs read Oct 2026) they were replaced by a single **`Memory`** class, distinguished by **scope** instead:

| Older docs | Current (v1.15+) |
|---|---|
| short-term | unified `Memory`, **scoped** |
| long-term | unified `Memory`, **scoped** |
| entity | unified `Memory`, **scoped** |
| user / external | unified `Memory`, **scoped** |

Scopes form a filesystem-like tree (`/project/alpha`, `/agent/researcher`), and the LLM infers placement when you omit it.

```python
from crewai import Memory
memory = Memory()
memory.remember("We decided to use Postgres for the user database.")   # LLM infers scope
matches = memory.recall("What database did we choose?")
```

Recall is ranked by a **composite score**, which is the part worth understanding — it is a stronger default than most hand-rolled RAG:

```
composite = 0.5 × semantic_similarity  +  0.3 × recency_decay  +  0.2 × importance
```

- **semantic** — vector similarity
- **recency** — `0.5 ^ (age_days / half_life)`, default half-life 30 days
- **importance** — a 0–1 score set at write time, inferred by an LLM

It also does the two things Step 35 told you to build yourself: **consolidation** (when a new record is >0.85 similar to an existing one, the LLM decides *keep / update / delete / insert*, so corrected facts **replace** instead of accumulating) and dedup within a batch. Saves are non-blocking, with a read barrier so a `recall()` always sees pending writes.

**Short-term, concretely:** each agent's live conversation, plus **`respect_context_window=True`** (the default) which auto-summarises when the window overflows. That is Step 35.2's compaction, built into the framework. Set it to `False` when losing information is worse than failing — legal review, security audit — and the run stops with an error instead.

**Rule of thumb.** CrewAI's memory defaults are good enough that the decision left to you is **scopes**: keep them 2–3 levels deep, and scope by **concern** (`/project/alpha/decisions`) rather than by data type (`/decisions/project/alpha`). Per-record isolation comes from `source` + `private`.

---

## 36.5 Sequential vs. Hierarchical Process

**Motivate.** Someone has to decide who runs when. Sometimes the order is known up front; sometimes it depends on what the work turns out to be.

**Define.** Two processes, plus an optional planning layer.

| | **Sequential** (default) | **Hierarchical** |
|---|---|---|
| Order decided by | you, at design time | a **manager agent**, at runtime |
| Mechanics | tasks run in list order | manager plans, delegates, validates |
| Requires | nothing extra | `manager_llm` **or** `manager_agent` |
| Cost | one call per task | extra calls to plan and validate |
| Fails by | an order you got wrong | the manager mis-routing |

Plus **`planning=True`**, which sends all the crew's data to an `AgentPlanner` before execution and injects the resulting plan into every task description — a built-in, cheaper version of Step 33's planner-executor pattern.

```python
crew = Crew(
    agents=[researcher, analyst, writer],
    tasks=[research, analysis, writing],
    process=Process.hierarchical,
    manager_llm="gpt-4o",     # REQUIRED for hierarchical -- missing it fails at runtime
    planning=True,            # optional: plan before executing
)
```

For long runs there is also **checkpointing** (`checkpoint=True`, saving after each task to `.checkpoints/`, resumable with `Crew.from_checkpoint(...)`) — the same durable-state idea as Step 34's checkpointers, one call away.

**Rule of thumb.** **Start sequential.** Move to hierarchical only when the *routing itself* needs judgment — when you genuinely cannot say which task comes next. Hierarchical adds a model call per step and a new place to be wrong; it is not a free upgrade. (Same call as workflow-vs-agent, Step 33.)

---

## 36.6 When Multi-Agent Loses to One Good Agent

**Motivate.** The tutorial version of this step ends at "look, a crew!" The useful version is knowing when a crew makes things *worse*.

**The costs, plainly:**

- **Latency** — every agent is at least one model call, and hierarchical adds more.
- **Cost** — each agent re-sends its own system prompt and context. Three agents sharing a task pay for it three times.
- **Error compounding** — the real one. A 90%-reliable step chained five times is **59%** reliable.

**The two principles that decide it.** Cognition (the builders of Devin) published *Don't Build Multi-Agents* (June 2025), and their two principles are the clearest short statement of this I've found:

> **1. Share context, and share full agent traces, not just individual messages.**
> **2. Actions carry implicit decisions, and conflicting decisions carry bad results.**

**Show.** Their example: "build a Flappy Bird clone", split into two subtasks.

- Subtask 1 — "build a moving background with green pipes and hit boxes" → the agent's *implicit decision* is that this looks like Super Mario Bros.
- Subtask 2 — "build a bird you can move up and down" → its bird's art and motion match neither.
- The final agent inherits both, plus the job of reconciling two unstated, incompatible assumptions.

Neither agent did anything wrong. Each filled in a detail nobody specified, and their guesses conflicted. **That is the failure mode: dispersed decision-making with no shared context.**

**When multi-agent genuinely wins.** Anthropic's multi-agent research system beat a single agent on complex research tasks — because of the *shape* of the work:

| Multi-agent works when | Multi-agent fails when |
|---|---|
| Sub-tasks are **independent** | Sub-tasks make **interdependent decisions** |
| Sub-agents **gather / read** | Sub-agents **write or change shared state** |
| The result is a **merge of findings** | The result needs **one consistent voice or design** |
| The task is broad (many directions) | The task is deep (a chain of choices) |

Note the pattern Cognition points out in Claude Code: its subagents never work in parallel with the main agent, and usually only **answer a question** rather than write code. The reason is principle 1 — and the payoff is that all the exploration stays out of the main context (Step 35.5).

**Rule of thumb.** Reach for multi-agent for **breadth with read-only sub-agents**. Keep **one** agent for anything that makes a *chain* of dependent decisions. If your sub-agents are all writing to the same artifact, you have built the merge-conflict machine.

---

## 36.7 Crews vs. Flows

**Motivate.** A crew hands the path to the LLM. Sometimes you already know the path, and you just want the steps automated reliably.

**Define.**

| | **Crew** | **Flow** |
|---|---|---|
| Control flow decided by | the LLM (autonomous) | **you** (event-driven) |
| Shape | agents + tasks + process | `@start` / `@listen` methods |
| Predictable | no | yes |
| Right for | "work out how to do this" | "do these steps, in this order" |

A **Flow** is ordinary Python where each step is decorated, and a step fires when the step it listens to completes. Model calls happen *inside* steps; the wiring between them is deterministic.

```python
from crewai.flow.flow import Flow, listen, start

class ResearchFlow(Flow):
    @start()
    def gather(self):
        return "findings..."

    @listen(gather)                       # fires when gather completes -- no LLM decides this
    def report(self, findings):
        return f"report from {findings}"
```

Flows also have built-in memory (`self.remember()`, `self.recall()`) and a usage-metrics contract, so they are not a toy alternative — for production orchestration CrewAI's own docs lean this way.

**Rule of thumb.** **Crew when the path is unknown; Flow when the path is known** and only the *content* is uncertain. This is Step 33's workflow-vs-agent call in different clothes — and note the symmetry with Step 34: LangGraph and Flows are both "you draw the control flow," one as a graph and one as events.

---

## Pitfalls

1. **Assuming agents share context.** They don't. Only `context=[...]` passes anything.
2. **No `expected_output`.** The agent invents a shape and downstream tasks choke on it.
3. **Vague goals.** "Research things well" optimises nothing.
4. **`allow_delegation=True` by reflex.** Loops and runaway cost; leave it off unless you need it.
5. **Tool bloat.** Every schema costs tokens on every call and adds a way to choose the wrong tool.
6. **Multi-agent for a chain of decisions.** The Flappy Bird failure.
7. **Parallel agents writing the same artifact.** Inconsistency is guaranteed, not likely.
8. **Hierarchical without `manager_llm`/`manager_agent`.** CrewAI requires one; you find out at runtime.
9. **Ignoring the cost maths.** Each agent re-sends its own prompt and context — three agents is not one call.
10. **Trusting the framework for reliability.** CrewAI makes multi-agent *easy*, which is exactly why fragile ones are easy to build.

---

## Quick Reference

| Goal | How |
|---|---|
| Define a specialist | `Agent(role=, goal=, backstory=, tools=)` |
| Define a unit of work | `Task(description=, expected_output=, agent=)` |
| Pass knowledge between tasks | `Task(context=[other_task])` — the only channel |
| Fixed order | `process=Process.sequential` |
| Let a manager route | `process=Process.hierarchical` + `manager_llm`/`manager_agent` |
| Plan before executing | `planning=True` |
| Persist across runs | `memory=True`, or `Memory(llm=, embedder=)` |
| Tune recall | weights for semantic / recency / importance; `recency_half_life_days` |
| Survive context overflow | `respect_context_window=True` (auto-summarise); `False` to fail instead |
| Resume a long run | `checkpoint=True`, then `Crew.from_checkpoint(...)` |
| Cheaper tool calls | `function_calling_llm="<small model>"` |
| A deterministic path | use a **Flow** (`@start`/`@listen`), not a crew |
| Crew or one agent? | breadth + read-only → crew; dependent decisions → one agent |

---

## Theory Summary

- **A crew is an org chart, not a brain.** Several focused agents, not one smarter one.
- **Every agent has its own context window.** Nothing is shared unless a task's `context` explicitly shares it.
- **Role, goal, backstory *are* the system prompt** — the cheapest, highest-leverage thing you configure.
- **Tasks need a contract.** `expected_output` is not decoration; it is the interface.
- **Memory is scoped, and ranked by more than similarity.** Semantic + recency + importance, with consolidation that replaces rather than accumulates.
- **Sequential by default; hierarchical when routing needs judgment.** More calls, and one more way to fail.
- **Actions carry implicit decisions.** Conflicting, unstated decisions across agents produce inconsistent results.
- **Multi-agent wins on breadth with read-only sub-agents.** It loses on chains of dependent decisions.
- **Crews are autonomous; Flows are deterministic.** Pick the one matching how well you know the path.
- **The framework makes it easy, not reliable.** Easy is the trap.

---

## Deliverable

**`Phase 1(AI)/STEP 36/step36-crewai/`**

A **minimal CrewAI-style engine built from scratch** — `Agent`, `Task`, `Crew` — with a scripted model, so the mechanics are visible and it runs with **zero API quota**.

- **`crew.py`** — the three primitives and nothing else:
  - `Agent(role, goal, backstory, tools)` compiling those three strings into a **system prompt**, making 36.2 visible in code rather than asserted;
  - `Task(description, expected_output, agent, context)` where `context` is the **only** path by which one agent's output reaches another, printing exactly what each agent saw — which makes 36.1's rule concrete;
  - `Crew(agents, tasks, process=...)` supporting both **sequential** and **hierarchical** processes, the hierarchical one run by a router that can also mis-route, on purpose;
  - a `ScriptedLLM` so no API key is needed.
- **`demo.py`** — three runs, each printing the context every agent received:
  1. **Sequential** — a research → analysis → writing crew where each task declares the `context` it needs;
  2. **Hierarchical** — the same work routed by a manager, showing the extra planning and validation calls it costs;
  3. **The Flappy Bird failure** — two parallel agents each make a different *implicit* decision about an unspecified detail, then a merge step produces something incoherent. The output is deliberately bad: the point is that the printout shows *which* assumption each agent invented, and why nothing downstream could reconcile them.

**Design notes:** the re-implementation is deliberate. The subject of this step is the *org chart* — who sees what, and who decides the order — and that is only visible if you write the context-passing yourself. The failure demo is the useful half: it converts 36.6 from an opinion into something you watched happen, and it is the answer you will want when an interviewer asks "would you use multi-agent here?"

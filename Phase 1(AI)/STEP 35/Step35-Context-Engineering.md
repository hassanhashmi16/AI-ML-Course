# Step 35: Context Engineering & Agent Memory

> **Covers:** treating the context window as a finite budget rather than a container — what earns a slot and what gets evicted; short-term memory strategies (clearing, trimming, summarizing, compaction); long-term memory and its types (episodic vs. semantic) with explicit write/read policies; offloading state to files and databases and retrieving it just-in-time; isolating context with sub-agents; and the failure modes (poisoning, distraction, clash, overflow) plus how to evaluate memory. This is the step where "the agent forgot" stops being a mystery.

---

## The Problem

Your agent works beautifully for six turns, then starts contradicting itself, forgetting the task, and confidently citing a tool result from twenty messages ago that it has since superseded. Nothing crashed. The model didn't get worse. **You ran out of attention.**

LLMs don't have a hard memory limit so much as a *degrading* one. Every token you add makes the model slightly worse at using the others — measurably, across every model tested. An agent running in a loop produces an ever-growing pile of things that *could* be relevant, and someone has to decide which of them actually go into the window. That deciding is this step.

---

## Foundational Concepts

### Context engineering vs. prompt engineering

**Prompt engineering** is writing good instructions. **Context engineering** is deciding what tokens exist in the window at this moment: the system prompt, the tool definitions, the retrieved documents, the message history, and everything else that lands there. (Anthropic, Sep 2025)

Prompt engineering is largely done once, at design time. Context engineering is **iterative** and happens on *every single model call*, because the window is rebuilt every turn.

> **The shift:** for a one-shot task, the prompt *is* the context. For an agent in a loop, the prompt is a small fixed part of a state that keeps growing.

### The attention budget

Why not just use a bigger window? Because attention is **quadratic**: n tokens means n² pairwise relationships, and the model's ability to capture them gets stretched thin as n grows. Models are also trained mostly on shorter sequences, so they have less practice with long-range dependencies. The result is a performance *gradient*, not a cliff — the model still works, it's just quietly less precise.

This is **context rot**, and it's been measured. Chroma tested 18 models (GPT-4.1, Claude 4, Gemini 2.5, Qwen3, and others) on deliberately simple tasks, varying *only* the input length:

| Finding | Detail |
|---|---|
| **Degradation is universal** | every model got worse with more tokens, including on non-lexical (semantic) matching |
| **Similarity matters** | lower needle-question similarity → faster degradation |
| **Distractors hurt** | one topically-related-but-wrong sentence reduced accuracy versus needle alone; four compounded it |
| **Structure hurts** | models scored *better* on shuffled haystacks than on logically coherent ones |

Two of those are counterintuitive and worth sitting with: a *single* plausible-looking wrong fact degrades performance, and a coherent narrative is *harder* than shuffled text. The window is not a neutral container you pour facts into.

### The goal

Not "as much relevant information as possible." It is:

> **The smallest set of high-signal tokens that maximises the likelihood of the desired outcome.**

Minimum *sufficient*, not minimum. A short system prompt that omits the tool policy is worse than a long one — "minimal" means no *unearned* tokens, not few tokens.

---

## 35.1 The Context Window as a Budget

**Motivate.** If you never decide what gets evicted, the answer is "nothing", and the window fills with history until quality collapses.

**Define.** Treat the window like a fixed bank balance. Every component spends tokens, and you have to fund each one deliberately.

| Component | Typical cost | Notes |
|---|---|---|
| System prompt | small–medium | instructions, policies, output format |
| Tool definitions | **often large** | every tool = name + description + JSON schema, on *every* call |
| Retrieved context | medium–large | documents, snippets, memory hits |
| Message history | **unbounded** | the thing that actually kills you |
| Tool results | large | raw outputs, often hundreds of tokens each |
| Current input | small | |

**Show.** Measure before you guess. A worked example is worth doing by hand once: 12 tools × ~150 tokens of schema = ~1,800 tokens of tool definitions *before the user has said anything*, paid on every single call.

**Rule of thumb.** Fund in this order: instructions → tools actually needed → retrieved context → history. Tool definitions are the most commonly *un*-audited cost, and a bloated tool set is also a correctness problem — Anthropic's test is blunt: "if a human engineer can't say which tool to use, don't expect the agent to."

---

## 35.2 Short-Term Memory: Trimming, Summarizing, Compaction

**Motivate.** History grows monotonically. Something must forget, and you should choose what.

**Define.** Four strategies on a spectrum from cheapest-and-lossiest to most-expensive-and-most-faithful:

| Strategy | What it does | Cost | Loses |
|---|---|---|---|
| **Tool-result clearing** | replace old tool outputs with a placeholder | none | raw outputs (usually fine to lose) |
| **Trimming** | drop the oldest turns, keep the last K tokens | none | old decisions and constraints |
| **Summarizing** | replace old turns with an LLM-written summary | one LLM call | detail |
| **Compaction** | summarize the whole window and restart it | one LLM call | redundancy, not substance |

**Show.**

```python
# Trimming: keep the most recent tokens -- but never cut mid-turn.
# start_on="human" guarantees the history stays a VALID sequence for the API;
# cutting between an assistant tool call and its tool result is an API error.
messages = trim_messages(
    state["messages"],
    strategy="last",
    token_counter=count_tokens_approximately,
    max_tokens=128,
    start_on="human",              # never start on a dangling tool result
    end_on=("human", "tool"),      # never end on a hanging assistant tool call
)
```

**Compaction** is the one to understand properly, because it's what makes long-horizon agents work. Anthropic's description: when the conversation nears the limit, summarize it, then **re-initiate a fresh context window containing the summary** — preserving architectural decisions, unresolved bugs and implementation details while discarding redundant tool outputs. Their tuning guidance is the useful part:

> Maximise **recall** first (capture everything relevant), *then* improve **precision** (strip what isn't).

Aggressive compaction discards context whose importance only becomes apparent later. Start permissive and tighten.

**Rule of thumb.** Cheapest fix first: clear old tool results → trim → summarize → compact. And keep the **last few turns verbatim** — immediate conversation is where coherence lives.

---

## 35.3 Long-Term Memory: Episodic vs. Semantic

**Motivate.** Short-term memory dies with the thread. "You told me last week you prefer X" requires storage *outside* the window.

**Define.** Long-term memory is storage that persists across sessions, written and read explicitly. Four types show up in practice:

| Type | What it stores | Example |
|---|---|---|
| **Semantic** | facts about the world or the user | "the user runs Postgres 16" |
| **Episodic** | specific past events, timestamped | "on Tuesday the deploy failed with a 502" |
| **Procedural** | how to do things | "for this repo, run tests with `pytest -q`" |
| **Working** | this thread's live state | the message history (35.2) |

The load-bearing distinction is **semantic vs. episodic**: a fact is timeless, so it can be deduped and *overwritten*; an event happened at a moment, so it *accumulates*.

**Define: the policies.** Memory is a system, not a dict. Two decisions must be made explicitly:

**Write policy** — when does something get stored?
- **Explicit** ("remember that I...") — highest precision, lowest coverage.
- **Inferred** (extract candidate facts with a model call) — better coverage, needs validation.
- **Append-everything** (log every turn) — cheap, but the store fills with noise and retrieval quality decays.

**Read policy** — when does it come back?
- **Always** (inject everything at startup) — simple, burns budget on irrelevant memories.
- **Retrieved** (semantic search, top-k) — scales, needs embeddings.
- **On demand** (the agent calls a `recall()` tool) — most token-efficient, needs a model smart enough to ask.

**Show.**

```python
# LangGraph splits this in two (docs.langchain.com, 2026):
checkpointer = InMemorySaver()          # SHORT-term: thread-scoped state, written every step
store        = InMemoryStore()          # LONG-term: cross-session, namespaced
graph = builder.compile(checkpointer=checkpointer, store=store)

# Namespacing is the (user, purpose) key -- keeps users' memories apart by construction.
namespace = ("memories", user_id)
store.put(namespace, memory_id, {"text": "prefers terse answers"})
hits = store.search(namespace, query=question, limit=3)   # semantic search
```

**Rule of thumb.** Semantic memory is an **upsert**, keyed by `(user, subject)`, so a corrected fact *replaces* the old one. Episodic memory is an **append**, with timestamps. Get that backwards and you'll either overwrite history or accumulate contradictions.

---

## 35.4 Retrieval-as-Memory & State Offloading

**Motivate.** Some state is too big for the window and doesn't need to be there: a 400-page document, a 10,000-row result, a file tree.

**Define.** Instead of loading data into context, keep a **lightweight identifier** — a file path, a query, a URL — and load the data *just in time* by calling a tool on it.

This is how Claude Code works: it doesn't read your repo into context, it holds the file *names* and uses grep/head/tail to pull in the forty lines it needs. Anthropic frames the same idea non-technically: we don't memorise libraries, we use a card catalogue.

**Show.** Two ways to answer "what were our Q3 numbers?" against a 200-page PDF:

```
PRE-INJECT:    embed PDF → retrieve top-k chunks → put them in the prompt
               (fast, possibly stale, no control over what's included)

JUST-IN-TIME:  give the agent search_pdf(query) and read_page(n)
               (slower, precise, self-directed)
```

Metadata is a *signal*, not just a label: a file named `test_utils.py` in `tests/` means something different from one in `src/core_logic/`. Paths, timestamps and naming conventions tell the agent what is worth opening, and let it assemble understanding layer by layer — **progressive disclosure**.

The trade-off is real: runtime exploration is *slower* than pre-computed retrieval, and an agent without good heuristics will waste context chasing dead ends. The honest answer for most systems is **hybrid** — inject the small high-value things up front, let the agent explore for the rest.

**Rule of thumb.** If a piece of state is large and only sometimes relevant, **store a handle, not the content**. Anything durable and structured — a to-do list, a scratchpad, progress notes — belongs in a file or a table, not in the message history.

---

## 35.5 Sub-Agents & Context Isolation

**Motivate.** Research sub-tasks fan out. If every branch's findings land in the main window, the main window becomes a junk drawer.

**Define.** A **sub-agent** is a separate agent with a **fresh context window**, given a scoped task. It can burn 50,000 tokens exploring and return **1,000–2,000 tokens** of distilled result. The parent never sees the exploration.

```
        ┌── sub-agent A (clean window) ──► 1.5k summary ──┐
parent ─┼── sub-agent B (clean window) ──► 1.2k summary ──┼─► parent synthesises
        └── sub-agent C (clean window) ──► 2.0k summary ──┘
```

Three things this buys:

1. **Isolation** — one sub-agent's dead ends and failures don't poison the parent's context.
2. **Compression** — the parent's window holds conclusions, not evidence.
3. **Parallelism** — sub-agents can run concurrently.

Not free: a sub-agent cannot see what the parent knows, so the task brief must be self-contained, and cost and latency multiply.

**Rule of thumb.** Use a sub-agent when the *process* of a task is long but its *result* is short. Keep it in the main thread when the reasoning is intertwined with everything else. (This is Step 33's orchestrator-workers pattern, implemented in LangGraph with subgraphs — Step 34.8.)

---

## 35.6 Failure Modes & Evaluating Memory

**Motivate.** Memory bugs don't crash. They produce plausible answers built on the wrong premise, which is worse.

**Define.** The four named ways context goes bad:

| Failure | What happens | How you'd notice |
|---|---|---|
| **Poisoning** | a wrong "fact" enters context (bad tool output, hallucination, stale memory) and is *repeated back* later as established truth | the agent asserts something you never told it |
| **Distraction** | irrelevant-but-similar content outcompetes the real answer | confidently wrong, and the right text *was* present |
| **Clash** | two contradictory facts both in context; the model picks one arbitrarily | inconsistent answers to the same question |
| **Overflow** | the window is exceeded and something is silently dropped | truncation errors, or detail vanishing mid-task |

Poisoning is the nastiest because it is self-reinforcing: once a bad fact reaches the *store*, it returns in every future session. Distraction is the most common in practice — Chroma showed a single distractor degrades performance.

**Mitigations:**

- **Provenance on every memory** — record where it came from (user, tool, model) so trustworthiness is inspectable.
- **Never write unvalidated model output to memory** — a hallucinated summary becomes a permanent lie.
- **Recency plus conflict handling** — on a contradicted fact, prefer the newer *explicit* one and mark the old one superseded. Don't just append both.
- **Budget checks are tests, not stack traces** — detect overflow deliberately.

**Evaluating memory.** You cannot eyeball this. The reference benchmark is **LongMemEval**, which Chroma used: long conversational histories (~113k tokens) with questions requiring knowledge-update, temporal reasoning, and multi-session recall. Chroma's headline result is the whole justification for this step:

> Given **focused** prompts (only the relevant parts, ~300 tokens), models score far higher than on **full** prompts (~113k tokens) containing the same information. The gap is the model having to *retrieve inside the window* and *reason* at the same time.

So the metric for a memory system is not "did we store it". It is **can the agent answer a question from three sessions ago**, and at what token cost.

**Rule of thumb.** Test memory with questions whose answers exist *only* in an old session, and score both accuracy and tokens spent. A memory system that stores everything and retrieves badly is worse than no memory at all.

---

## Pitfalls

1. **Nothing is ever evicted.** History grows until quality collapses. Pick an eviction policy on day one.
2. **Unbounded tool definitions.** A bloated tool set costs tokens on every call *and* causes wrong-tool selection.
3. **Trimming mid-turn.** Cutting between an assistant tool call and its result produces an invalid sequence and an API error.
4. **Aggressive compaction.** Summarizing too hard drops context whose importance only appears later. Recall first, then precision.
5. **Storing model output unvalidated.** A hallucination written to long-term memory is permanent.
6. **Append-only semantic memory.** Contradictions accumulate; a corrected fact must *replace* the old one.
7. **Injecting all memories every turn.** Simple, and it quietly eats the budget while adding distractors.
8. **No provenance.** You cannot tell whether a remembered fact came from the user or from a model's guess.
9. **Sub-agents with underspecified briefs.** They cannot see the parent's context, so a vague task returns confidently wrong work.
10. **Believing a bigger window solves it.** Context rot degrades every model tested; more room is not the fix.

---

## Quick Reference

| Goal | How |
|---|---|
| Decide what is in the window | smallest set of high-signal tokens: instructions → tools → retrieval → history |
| Measure before guessing | count tokens per component; tool schemas are the usual surprise |
| Cheapest history fix | clear old tool results |
| Bound the history | `trim_messages(..., start_on="human", end_on=("human", "tool"))` |
| Keep the thread coherent | summarize old turns, keep the last few verbatim |
| Long-horizon tasks | compaction: summarize → fresh window with the summary (recall first, then precision) |
| Remember across sessions | a store, not the checkpointer, keyed `(user, purpose)` |
| Facts vs. events | semantic = upsert/replace; episodic = append with timestamps |
| Big state, rarely needed | store a handle (path/query), load just-in-time via a tool |
| Isolate a sub-task | sub-agent, fresh window, self-contained brief, returns 1–2k distilled tokens |
| Debug "the agent forgot" | was the fact in context? evicted, or never retrieved? |
| Test memory | LongMemEval-style: questions answerable only from an old session; score accuracy *and* tokens |

---

## Theory Summary

- **Context is a budget, and attention is the currency.** Every token spends some — including the ones you didn't think about: tool schemas, tool results, and history.
- **Context rot is universal.** Performance degrades with input length across every model tested, even on trivial tasks, and distractors and structure matter as much as raw length.
- **The goal is the smallest set of high-signal tokens.** Minimum *sufficient*, not minimum.
- **Short-term memory is a choice about forgetting.** Clear → trim → summarize → compact, and keep recent turns verbatim.
- **Long-term memory needs a write policy and a read policy.** A store without them is a junk drawer with an API.
- **Semantic upserts, episodic appends.** Get it backwards and you either lose history or accumulate contradictions.
- **Offload large state; keep handles.** Just-in-time retrieval trades latency for precision and scale.
- **Sub-agents buy context isolation.** Long process in, short conclusion out.
- **Poisoning is self-reinforcing.** Never write unvalidated model output into long-term memory.
- **Memory is measurable.** Test it the LongMemEval way: answers available only in an old session, scored on accuracy and tokens.

---

## Deliverable

**`Phase 1(AI)/STEP 35/step35-context/`**

A **context budgeter plus a long-term memory store** for Project 2's assistant — the piece Project 3 needs and Project 2 never had.

- **`budget.py`** — assemble a context window against a fixed token budget:
  - components declared with a **priority** (system → tools → retrieved docs → history);
  - a `TokenBudget` that measures each component and prints a per-component table of used vs. available tokens;
  - eviction in the cheap-to-expensive order of 35.2: clear old tool results → trim → summarize;
  - `--budget N` to watch behaviour change as the window shrinks.
- **`memory.py`** — a small long-term store on **SQLite** (stdlib, no server):
  - **semantic** memories upserted on a `(user, subject)` key, and **episodic** memories appended with timestamps, so 35.3's distinction is *demonstrated* rather than asserted;
  - every row carries **provenance** (`user` / `tool` / `model`) and a `superseded_by` pointer for conflicts;
  - a keyword-and-recency read policy (`search(query, k)`) so it runs with zero API quota, with an `--embed` flag that swaps in Gemini embeddings for the semantic path.
- **`demo.py`** — three scenarios end to end, no API key required:
  1. **Budget** — a long conversation that overflows; watch tool results clear, then trimming, then summarization engage as `--budget` shrinks;
  2. **Two sessions** — session 1 writes a fact to memory from a fresh process; session 2 recalls it and answers, proving the memory genuinely lives outside the window;
  3. **Poisoning** — a `model`-provenance claim is rejected on write, and a user-corrected fact flips the old row to `superseded_by` instead of appending a contradiction.

**Design notes:** SQLite keeps it dependency-free and re-runnable, and the keyword read path keeps it offline by default — the same discipline as Steps 31, 33 and 34. The store schema (`subject`, `provenance`, `superseded_by`, `created_at`) is the real content here: it is the shape Project 3's memory needs, and it is cheap to copy forward.

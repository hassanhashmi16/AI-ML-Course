# Step 31: Tracing & LLM Observability (LangSmith / Langfuse)

> **Covers:** what a trace is and why a per-request timeline is the only way to debug a RAG system, the span hierarchy and the OpenTelemetry GenAI semantic conventions that every backend parses, how to read a trace (latency and token spend per stage), the platform landscape and how to choose, capturing content vs redacting it, propagating trace context across services, metrics alongside traces, sampling when the volume gets real, and the feedback loop that turns a bad production run into a permanent eval case.

---

## The Problem

Your Project 2 has an eval (Step 30) that tells you quality *dropped*. It cannot tell you **why**. A user reports a wrong answer and you have nothing: the logs show the final string, not the question that was rewritten, the chunks that were retrieved, the order the reranker left them in, or which stage spent 11 of the 12 seconds. You guess, you change something, and you hope. Tracing is what turns "it's wrong sometimes" into "the reranker demoted the right chunk on 3 of the last 40 runs, all of them when the query contained a number."

**Eval measures quality. Tracing explains a single run.** Different questions, different tools, and you need both.

---

## Foundational Concepts

### Three tools, three questions

They get conflated constantly. Keep them separate:

| Tool | Question it answers | When | Scope |
|---|---|---|---|
| **Eval** (Step 30) | *Is the quality good?* | offline, on a frozen set | aggregate |
| **Trace** | *What happened on this one run?* | online, per request | one request |
| **Metrics** | *Is the system healthy over time?* | online, continuous | aggregate, streaming |

An eval tells you a score fell. A trace tells you which line of code did it. Metrics tell you it's been falling for three hours and nobody noticed. You will build all three, and none replaces the others.

### Spans and traces

- A **span** is one timed operation with a name, a start, an end, and attributes: `retrieve`, `rerank`, `llm.chat`, `tool.execute`.
- A **trace** is a tree of spans that share a **trace id**, linked parent→child by span ids.

That tree is the whole value. If you only instrument the LLM call, your timeline has a hole exactly where the bug lives.

### OpenTelemetry, and why the attribute names matter

**OpenTelemetry (OTel)** is the open standard for traces, metrics, and logs. Its **GenAI semantic conventions** (stable from v1.37 onward, 2025–2026) fix the *attribute names* for LLM work, so Datadog, Langfuse, Phoenix, OpenLLMetry, and AgentOps all parse the same spans. Instrument once; ship to any backend.

The practical consequence: **do not invent attribute names.** `gen_ai.request.model` is parsed everywhere; `model_name` is parsed nowhere. The convention is the interface.

---

## 31.1 Enabling Tracing on a Run

**Motivate.** Tracing is easy once you know where the instrument goes; the hard part is that a hand-built pipeline like ours gets no automatic instrumentation.

**Define.** "Enabling tracing" = wrapping each stage of the pipeline in a span, with the same trace id propagated down the call stack.

**Show.** Two ways to get spans:

- **Auto-instrumentation** — a library monkey-patches your framework and emits spans for you (LangChain, LangGraph, Pydantic AI, MCP clients all have this). Free, but blind to code the library doesn't own — and our pipeline is hand-rolled, so it would trace almost nothing.
- **Manual instrumentation** — you open a span around each stage you care about. More typing, full control, works on anything.

Ours is manual, and the shape is a context manager:

```python
with span("retrieve", kind="INTERNAL", **{"db.system": "postgresql"}) as s:
    chunks = hybrid_search(question)
    s.set("retrieval.chunk_ids", [c.chunk_id for c in chunks])
```

**Rule of thumb.** Instrument the boundaries where work crosses a component: one span per pipeline stage, plus one per external call (LLM, DB, rerank API). That is usually 5–7 spans per question, and it is enough to see the whole story.

---

## 31.2 Reading a Trace

**Motivate.** A trace is useless if you can't read it under pressure. The skill is knowing what to look at, in what order.

**Define.** Reading a trace = walking the span waterfall for three signals: **where the time went**, **where the money went**, and **where it went wrong**.

**Show.** A healthy trace of one question looks like this:

```
trace 7f3a…  (total 4.2s, 3,140 tokens, $0.0019)
├─ rewrite          INTERNAL   0.6s   llm.chat 320 tok
├─ retrieve         INTERNAL   0.4s
│   ├─ dense.search   CLIENT   0.2s   db  (20 rows)
│   └─ sparse.search  CLIENT   0.1s   db  (20 rows)
├─ rerank           CLIENT     0.3s   cohere (20 → 5)
└─ generate         CLIENT     2.7s   llm.chat 2,820 tok   ← 64% of latency, 90% of cost
```

Read it in this order:

1. **Total latency, then the widest bar.** Here `generate` dominates. If your users say "it's slow", the answer is in the widest span, not the total.
2. **Token spend per span.** Cost is almost always the *generate* span, and it scales with how many chunks you fed it — which is a retrieval decision. This is where you discover that `top_k=20` costs you money on every question.
3. **The attributes on the failing span.** This is the part a log can't give you: the rewrites that were tried, the chunk ids retrieved, the rerank scores. When the answer is wrong, the trace shows whether the right chunk was *never retrieved* or *retrieved and then demoted* — two completely different bugs.

**The one habit that matters:** when the answer is wrong, look at the **retrieve and rerank spans first**, not the prompt. In a RAG system the model is usually innocent; it answered faithfully from bad context.

**Rule of thumb.** Optimise the widest bar; investigate the span*whose attributes are wrong. And check p99, not the mean — the mean latency of a good system hides the 5% of runs that take 30 seconds.

---

## 31.3 Creating a Dataset from Real Runs

**Motivate.** The highest-value eval cases are not the ones you invent — they're the ones that actually broke. And they arrive one at a time, in production, where you'd otherwise fix them and forget them.

**Define.** Promote a trace into a dataset row: take the question, the retrieved contexts, the answer, and the *correct* answer you determine by hand, and append them to the frozen golden set from Step 30.

**Show — the flywheel:**

```
production run ──► trace (what happened)
                      │  a human reads it and asks "was this right?"
                      ▼
                 dataset row (question + contexts + reference)
                      │
                      ▼
              eval (Step 30) scores it forever after
                      │
                      ▼
              CI gate (30.10) fails the next time someone breaks it
```

Every bug becomes a permanent test. This is the whole reason to have traces and an eval in the same project: **tracing finds the case, the eval stops it coming back.** Without the loop, you fix the same class of bug in Project 4, in Project 8, and again in Project 9.

**Rule of thumb.** Every time you debug a bad answer, ask one question: "is this a case the eval should have caught?" If yes, it goes in the dataset before you close the ticket. Fixing without capturing is a bug you've agreed to meet again.

---

## 31.4 OpenTelemetry-Based Tracing & Self-Hosted Options

**Motivate.** You can trace to a JSONL file for a while. The moment you want history, search, dashboards, or someone else's eyes on it, you want a platform.

**Define.** All the serious options **speak OTLP** (the OpenTelemetry wire format) and **parse the `gen_ai.*` conventions**. So the choice is about features and licensing, not about lock-in.

**Show — the 2026 landscape** (licenses and positioning as of late 2025 / 2026; verify before you commit):

| Platform | License | Strongest at |
|---|---|---|
| **Langfuse** | MIT | all-in-one: tracing + **prompt versioning** + evals + session replay |
| **Arize Phoenix** | Elastic License 2.0 | RAG relevancy, **trace clustering / drift**, auto-instrumentation (OpenInference) |
| **Comet Opik** | Apache 2.0 | **automated prompt optimisation**, guardrails, hallucination judging |
| **Datadog / Honeycomb** | commercial | teams already living in those tools — they natively parse `gen_ai.*` |
| **LangSmith** | commercial | the roadmap's link; deep LangChain integration |

**Picking one, honestly:**

| Your need | Pick |
|---|---|
| Prompt versioning + tracing together, permissive licence | Langfuse |
| Deep RAG evaluation and behavioural drift | Phoenix |
| Prompt optimisation loop + guardrails | Opik |
| Mixed ops/ML team already on a platform | whatever they run — it parses OTel |

**Self-host vs cloud.** Langfuse and Phoenix both self-host, which matters for two reasons: your traces contain your users' prompts (31.6), and a free tier will not hold a real corpus of history. Start self-hosted with Docker — it's a `docker compose up`, exactly like the Postgres you already run.

**Rule of thumb.** Pick OTel-compatible and self-hostable. You're choosing where your *traces* live, not rewriting your instrumentation. Take vendor benchmarks (e.g. "Opik is 14× faster than Langfuse") as directional, never as fact — measure your own.

---

## 31.5 The Span Hierarchy & GenAI Semantic Conventions

**Motivate.** Everyone's trace viewer renders a tree. If your spans nest wrongly — or your attribute names are invented — the platform shows you a flat list of orphaned boxes.

**Define.** The convention defines a **tree** and a **vocabulary**:

```
invoke_agent            INTERNAL   gen_ai.agent.name
├─ llm.chat             CLIENT     gen_ai.request.model, gen_ai.usage.*
├─ execute_tool         INTERNAL   gen_ai.tool.name, gen_ai.tool.call.id
│    └─ mcp.call        CLIENT     (same trace id, propagated)
└─ llm.chat             CLIENT
```

**The attributes worth knowing by heart** (2025–2026 semconv):

| Attribute | On | Meaning |
|---|---|---|
| `gen_ai.operation.name` | any | `chat`, `embeddings`, `execute_tool`, `invoke_agent` |
| `gen_ai.provider.name` | LLM | `google`, `openai`, `anthropic` |
| `gen_ai.request.model` | LLM | the model you *asked* for |
| `gen_ai.response.model` | LLM | the model *actually served* (they differ more often than you'd think) |
| `gen_ai.usage.input_tokens` / `output_tokens` | LLM | the token spend — your cost signal |
| `gen_ai.response.id` | LLM | provider id, for correlating with the provider's own logs |
| `gen_ai.tool.name` / `call.id` | tool | which tool, which invocation |

**Span kind is not decoration:** `CLIENT` for anything crossing a process boundary (LLM provider, database, rerank API, MCP server) and `INTERNAL` for your own steps. It's how a viewer knows to draw a call as a call.

**Rule of thumb.** Nest by *ownership* — the span that owns the work is the parent. `generate` owns the LLM call; the agent loop owns everything. If a span's parent is ambiguous, your component boundaries are ambiguous, which is itself useful information.

---

## 31.6 Capturing Content vs Redacting It

**Motivate.** The most useful span attribute is the prompt — and the most dangerous one. Prompts contain user data, and your trace store is a new copy of it, with a new access list and a new retention policy.

**Define.** Content capture is the recording of **prompts, completions, and retrieved document text** as span attributes or events. The convention puts it **off by default** and behind an explicit opt-in.

**Show — what to capture, and at what level:**

| Content | Default | When to enable |
|---|---|---|
| Model name, token counts, latencies | **always** | never optional — no PII, all the value |
| Chunk **ids** and rerank scores | **always** | never optional — tells you *which* chunk, not what it said |
| Chunk **text** | opt-in | debugging retrieval quality, on a small sampled fraction |
| Full **prompts / completions** | opt-in | debugging generation, with a redaction pass, short retention |
| Raw user identifiers | **never in attributes** | put a hashed id; join to your `query_log` for the real one |

**Show — the mechanism (OTel convention):**

```python
# Content is off unless you opt in. Names per the GenAI semconv.
import os
os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] = "gen_ai_latest_experimental"
os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"  # ← do this in dev only
```

**Why this is a design decision, not a checkbox.** The trace store is now a second database of your users' text. It needs the same redaction (PII scrubbing), the same access control, and a *shorter* retention than the primary store — because traces are copied everywhere, exported to third parties, and rarely anyone's job to clean up.

**Rule of thumb.** Capture **structure** by default (ids, scores, counts, timings) and **content** only behind a flag, on a sample, with redaction, with a retention window. "We log everything" is how a trace store becomes a liability.

---

## 31.7 Propagating Context Across Services

**Motivate.** The moment your pipeline is more than one process — the FastAPI server from Step 14 calling the retrieval code, an MCP tool call, a sub-agent — a trace that stops at the process boundary is a trace with a hole.

**Define.** Propagation = passing the trace context (trace id + parent span id) across a boundary so the remote side's spans join the same tree. The W3C standard header is **`traceparent`**.

**Show — our project's boundary, concretely:**

```
React  ──POST /ask-stream──►  FastAPI  ──►  pipeline (in-process)
                                 │
                                 └─ one trace id for the whole request
```

- **In-process** (our pipeline): the context is a parameter you thread through — no header needed, just make sure `connect()`-style helpers don't start a new trace.
- **Across HTTP** (an MCP server, a sub-agent, a separate retrieval service): inject `traceparent` into the request headers, and the server continues the same trace.
- **`stdio` transports** (MCP over stdio) carry no HTTP headers, so the spec's approach is a `_meta.traceparent` field on the JSON-RPC call. Until that's universal, put the traceparent in `_meta` by hand and have the server log the trace id.

**Why it's worth doing now:** Project 4 turns this into an agent with tools and sub-agents. Every one of those hops is a process boundary. Propagate from the start and the agent's trace is one tree; skip it and you get five unrelated traces and the same debugging pain you started with.

**Rule of thumb.** If a call crosses a process, thread the trace id. A trace that stops at a boundary is worse than no trace, because it looks complete.

---

## 31.8 Metrics Alongside Traces

**Motivate.** Traces are per-request and expensive to keep. The question "has p99 latency been climbing since Tuesday?" is not answerable by reading traces — it's a metric.

**Define.** Metrics are the aggregated, streaming view: numbers sampled continuously, cheap to store, ideal for dashboards and alerts. The GenAI conventions define them alongside the spans:

| Metric | Type | What it tells you |
|---|---|---|
| `gen_ai.client.token.usage` | histogram | cost trajectory, per model |
| `gen_ai.client.operation.duration` | histogram | latency distribution — **p50/p95/p99**, not the mean |
| `gen_ai.tool.execution.duration` | histogram | which tool is slow, and when it started |

**Show — the split that keeps you sane:**

- **Traces** answer *"why is **this** run bad?"* — kept for a short window, sampled.
- **Metrics** answer *"is the system getting worse?"* — kept for months, cheap, and what pages someone at 3am.

Alert on metrics; debug with traces. An alert that fires without a *link to a representative trace* makes you re-derive the same context from scratch. Make the trace id a field in your logs so a p99 alert leads straight to the offending run.

**Rule of thumb.** Alert on **p99 latency**, **error rate**, and **token spend per hour** — the three that catch a real incident. And always alert on the tail, never the average: the same lesson as Step 30's bottom decile, in a different costume.

---

## 31.9 Sampling & the Cost of Tracing at Scale

**Motivate.** At a hundred questions a second, storing every trace is its own infrastructure project with its own bill. But the runs you most need are the rare ones — the failures.

**Define.** Sampling = deciding which traces to keep. The craft is keeping the informative ones.

**Show — the standard strategies:**

| Strategy | How | Problem |
|---|---|---|
| **Head sampling** | decide at the start, keep N% | cheap, but you decide *before* knowing it failed |
| **Tail sampling** | decide at the end, keep if interesting | keeps failures — needs the whole trace buffered first |
| **Always keep** | errors, timeouts, user negative feedback, cost spikes, low eval score | the rule that gives tail sampling its definition of "interesting" |

**Translation for our project:** always keep a trace when (a) the request errored, (b) latency exceeded some multiple of p95, (c) the user gave negative feedback, or (d) the automated faithfulness score (Step 30) came back low. Keep a small random sample of everything else — occasionally you need a *good* trace as a baseline to compare against.

**Rule of thumb.** Sample the happy path, never the unhappy one. A trace store holding only your slowest and most wrong runs is doing its job; one holding 100% of traffic is a bill pretending to be observability.

---

## Pitfalls

1. **Tracing without evaluation is expensive logging.** A trace viewer you never turn into a dataset row is a screensaver. Close the loop (31.3).
2. **Prompt versions not tied to traces.** When production regresses you cannot bisect to the prompt that caused it. Tag every span with the prompt version — it's one attribute and it's the difference between a 10-minute fix and an afternoon.
3. **Content captured by default.** Prompts are PII. Default to structure (ids, scores, counts) and opt into text behind a flag, on a sample, with redaction.
4. **Instrumenting only the LLM call.** The timeline then has a hole exactly where retrieval bugs live. Instrument every stage boundary.
5. **Trusting the mean.** Mean latency hides the 5% of runs that take 30 seconds — which are the ones users complain about. Read p99.
6. **No trace id in the user-visible error.** If a failure surfaces without a trace id, nobody can correlate the complaint to the run. Put it in the error payload and the logs.
7. **A self-rolled LLM-judge with no grounding.** A judge scoring "is this correct?" with no tools will hallucinate agreement. Give it the reference or the source passages (Step 30's lesson, restated).
8. **Tracing everything.** 100% retention is a storage bill and a PII surface. Sample the happy path; always keep failures.
9. **Self-hosted trace store with no retention policy.** It grows forever. Set a retention window on the day you set it up.
10. **Taking vendor benchmarks as fact.** "14× faster" was one vendor measuring their own product. Measure yours.

---

## Quick Reference

| Goal | How |
|---|---|
| Instrument a stage | open a `span(name, kind)` around it; one span per component boundary |
| Correlate the whole request | one trace id, threaded through every span and every process hop |
| Name attributes so any backend parses them | `gen_ai.*` per the OTel GenAI semconv — never invent names |
| Find the slow stage | widest bar in the waterfall; then check p99 across runs |
| Find the expensive stage | token counts per span — usually `generate`, scaling with `top_k` |
| Debug a wrong answer | read the **retrieve + rerank** span attributes first, not the prompt |
| Keep traces safe | structure by default, content behind a flag, sampled, redacted, with retention |
| Across a boundary | inject `traceparent` (HTTP) or `_meta.traceparent` (stdio MCP) |
| Watch the system over time | metrics (`token.usage`, `operation.duration`) — alert on p99, not the mean |
| Keep the right traces | sample the happy path; **always** keep errors, slow runs, and bad-feedback runs |
| Stop a bug coming back | promote the trace into a `golden.jsonl` row (Step 30) and let CI gate it |
| Choose a platform | OTel-compatible + self-hostable: Langfuse (MIT) / Phoenix (ELv2) / Opik (Apache 2.0) |

---

## Theory Summary

- **A trace is a per-request story; an eval is an aggregate verdict.** They answer different questions and you need both. Tracing explains *this* run; the eval decides whether you've actually improved.
- **The tree is the value, not the individual span.** Instrument every stage boundary, so the timeline has no holes. A trace that stops at a process boundary is worse than none, because it looks complete.
- **Standard attribute names are the interface.** `gen_ai.*` is what makes one instrumentation line portable across every backend. Invent a name and lose every tool that would have understood you.
- **Capture structure by default, content by exception.** Prompts are PII; your trace store is a second copy of your users' data with a new access list. Opt in, sample, redact, expire.
- **Traces debug; metrics alert.** Histograms over months catch the drift that no single trace reveals. Always watch the tail (p99), never the mean.
- **Sample the happy path, never the unhappy one.** The runs worth keeping are rare, which is exactly why keeping all of them is the wrong default.
- **The loop that makes it worth it:** a trace becomes a dataset row, the dataset becomes an eval case, CI gates it. Tracing finds the bug once; the eval makes sure you only ever meet it once.

---

## Deliverable

**`Phase 1(AI)/STEP 31/step31-tracing/`**

A **dependency-free tracing kit** for a hand-rolled pipeline — the same reasoning as every other step here: the span model *is* the lesson, and OTel-compatible output is a few dozen lines, not a framework.

- **`tracing.py`** — a minimal span emitter. `with span(name, kind, **attrs):` opens a span, times it, nests it under the current one, and writes **one JSON line per span** in OTel-GenAI shape (`trace_id`, `span_id`, `parent_span_id`, `name`, `kind`, `start`/`end`, and `gen_ai.*` attributes). **Content capture is off by default** (31.6); a `capture_content=True` flag turns it on explicitly.
- **`trace_view.py`** — reads a trace file and prints the **waterfall** with per-span latency and token spend, the share of total each span took, and a flag on the slowest span (31.2). This is the tool you'll actually use when an answer is wrong.
- **`to_dataset.py`** — takes a stored trace and appends a `golden.jsonl` row (question + retrieved contexts + a `reference` you fill in) for the Step 30 eval (31.3). **This is the flywheel**: trace → dataset → eval → CI gate.

**Instrumented target:** Project 2's pipeline shape — `rewrite → retrieve (dense + sparse) → rerank → generate`. The demo mirrors those stages exactly, in name and attributes, so instrumenting the *real* project is a one-line change per stage: wrap `rewrite_query`, `dense_search` / `sparse_search`, `rerank`, and the generation call in the same `with span(...)` blocks. Each external call is a `CLIENT` span, each of our own steps an `INTERNAL` span, and one trace id runs through the whole question.

**Run it** (from `step31-tracing/`):

```bash
python demo.py          # runs the instrumented pipeline -> traces/<trace_id>.jsonl
python trace_view.py    # prints the waterfall, token spend, and the slowest span
python to_dataset.py    # promotes a run into a dataset row for the Step 30 eval
```

**Expected output** — a healthy run, then the same pipeline failing at generation:

```
ask                     INTERNAL    3.96s              100%
|- rewrite              CLIENT      0.60s    320 tok    15%
|- retrieve             INTERNAL    0.32s                8%
|  |- dense.search      CLIENT      0.21s                5%
|  \- sparse.search     CLIENT      0.10s                3%
|- rerank               CLIENT      0.31s                8%
\- generate             CLIENT      2.72s  2,960 tok    69%  <- slowest
```

**Deliberate scope note (to be stated in the step):** we emit OTel-*shaped* JSONL rather than a real OTLP exporter. That keeps the artifact runnable with zero infrastructure and teaches the span model itself. Wiring the same spans into a real collector — a self-hosted Langfuse via `docker compose up`, then replacing the file writer with an OTLP exporter — is the follow-on exercise, and the span code does not change.

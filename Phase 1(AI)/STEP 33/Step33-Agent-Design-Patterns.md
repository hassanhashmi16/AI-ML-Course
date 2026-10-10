# Step 33: Agent Design Patterns

> **Covers:** the architectural choice senior interviews actually probe — **workflow or agent?** — plus the augmented-LLM building block everything is made of, the five composable workflow patterns (prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer), ReAct loops, planning and termination, the failure modes that break agents, and why the right answer is usually *less* autonomy than you want.

---

## The Problem

Step 32 gave you the primitive: a model that can call your functions. Now a decision, and it's the one that separates a working system from an expensive one:

**Should the model decide the steps, or should you?**

Reaching for an autonomous agent when a fixed sequence of calls would do buys you latency, cost, and new failure modes in exchange for flexibility you didn't need. Anthropic's own field report says the successful systems were "simple, composable patterns rather than complex frameworks." The skill this step teaches is knowing which one you're building — and being able to defend the answer.

---

## Foundational Concepts

### What an agent actually is

An agent is three things, and only three:

1. **A model** — it decides.
2. **Tools** — so it can act (Step 32).
3. **A loop** — it acts, sees the result, and decides again, until it stops.

All three, or it isn't one. **A single model call that returns text is not an agent** — no tools, no loop. And **Project 2 is not an agent either**, even though a model is central to it: the model never chose a step.

**The subtlety worth getting straight first:** the program wrapped around the model (the *harness* — Command Code, Cursor, Claude Code) provides the **frame**: the system prompt, the tool list, the permissions, and the mechanics of actually calling the model and running a tool. The **model** provides the **path**: which tool, with what arguments, in what order, and when to stop.

So "the model decides" means: *given a goal and a toolset, the model chooses the next step.* A system prompt constrains **behaviour** ("be concise", "stay inside this folder"); it does not script **steps**. If a harness scripted the steps, the system would be a workflow — **the more a harness scripts, the less agent it is.**

**The chess-engine analogy is the clean one.** The rules and the board are fixed (the harness). The engine chooses every move (the model). Nothing scripts "move the knight to f3."

**And the word is used loosely.** In marketing, "agent" means anything with an LLM in it, which makes the term useless. Engineering-wise it is the three ingredients above — which is exactly why the workflow-vs-agent distinction is real and not wordplay.

### Workflow vs agent — the one distinction

| | Who owns the graph? | Cost | Debugging |
|---|---|---|---|
| **Workflow** | you — steps are code paths you wrote | bounded, predictable | read the code |
| **Agent** | the model — it directs its own steps and tools | unbounded, unpredictable | read the trajectory |

Both are "agentic systems". The difference is **who decides the next step.** Neither is better; they're the right answer to different problems.

**You have already built a workflow.** Project 2's `ask → rewrite → retrieve → rerank → generate` is one — the order is hard-coded in `generation/answer.py`, and every question takes the same path. We just called it a "pipeline". That's the whole reason this distinction is worth naming: you'd done it without the vocabulary.

### The augmented LLM — the building block

Every pattern below is built from one thing: an LLM with three augmentations wired in.

- **Retrieval** — it can look things up (your Project 2 pipeline, exactly).
- **Tools** — it can act (Step 32).
- **Memory** — it can persist what matters across turns.

Design the *interface* to these carefully; everything else is composition. This is why Step 32 came first.

### Complexity is a cost you pay forever

Add a layer and you pay for it in latency, tokens, debugging time, and failure modes — every run, forever. The rule: **add complexity only when it demonstrably improves outcomes.** The default is one good prompt with retrieval.

---

## 33.1 Workflow vs. Agent — When Autonomy Is the Wrong Answer

**Motivate.** Autonomy sounds like progress. It's usually just risk.

**Decide with these:**

| Use a **workflow** when… | Use an **agent** when… |
|---|---|
| you can enumerate the steps | the next step depends on what the last one returned |
| the task is predictable | the task is open-ended (research, multi-file edits) |
| cost must be bounded | step count genuinely varies (minutes to hours) |
| an auditor wants to read the flow | you don't yet know the right flow |

**The three signs you don't need an agent:** you can draw the steps as a flowchart; the number of LLM calls is knowable in advance; a failure would be your bug, not the model's judgment call.

**Rule of thumb.** Build the simplest thing that works. Upgrade to an agent when a *specific, observed* task defeats the workflow — not pre-emptively.

---

## 33.2 ReAct (Reason + Act) Loops

**Motivate.** The smallest thing that deserves the name "agent": think, act, look at the result, repeat.

**Define.** ReAct interleaves **reasoning** and **acting**: the model produces a thought, emits a tool call, receives the observation, and decides what to do next — until it has enough to answer.

```
thought → action (tool call) → observation (result) → thought → … → answer
```

This is the loop your Step 32 code already implements; the only addition is that **it repeats**, and each iteration's observation informs the next decision.

**The two guards you must add:** a **max-iteration cap** (it will not stop on its own if it's confused) and a **budget** on tool calls. An unbounded ReAct loop is a runaway bill.

**Rule of thumb.** ReAct for genuinely variable tasks; anything with a knowable sequence should be a workflow, because a loop that doesn't need to loop only adds ways to fail.

---

## 33.3 Prompt Chaining, Routing, Parallelization

Three patterns that cover most real work, and all three are **workflows** — you write the control flow.

**Prompt chaining.** Call N's output is call N+1's input. Use when a task decomposes cleanly into fixed subtasks, trading latency for accuracy (each call is an easier job). *Example: draft → check against criteria → revise.* Optional **gates**: a programmatic check that halts the chain if step 1 went wrong.

**Routing.** A classifier picks which downstream prompt, chain, or **model size** handles the input. Use when categorically different inputs need different handling. *Example: refund request → refund flow; easy question → a cheap model; hard one → an expensive model.* Routing is also your main **cost lever**.

**Parallelization.** Run N calls at once, aggregate. Two shapes:
- **Sectioning** — independent subtasks (one model answers, another screens for unsafe content).
- **Voting** — the same task N times; majority or synthesis (multiple prompts reviewing code for bugs).

**Rule of thumb.** Chaining for fixed sequences, routing for distinct categories, parallel for speed or confidence. All three are cheaper and more debuggable than an agent doing the same job.

---

## 33.4 Orchestrator-Worker & Evaluator-Optimizer

The two patterns that look most like agents while staying bounded.

**Orchestrator-workers.** An orchestrator LLM **decides which workers to run** and synthesizes their results. It's topographically similar to parallelization — the difference is **the subtasks aren't predefined**; the orchestrator invents them from the input. Use for coding tasks across an unknown number of files, or research across unknown sources.

**Evaluator-optimizer (reflection).** One call produces, another **critiques**, repeat until it passes. Use when you have clear criteria and iteration measurably helps — literary translation, multi-round search. It's Self-Refine generalised, and it's the same shape as the LLM-as-judge you met in Step 30.

**The bound that makes them safe:** the orchestrator doesn't loop indefinitely, and the evaluator has a **max iteration count** plus a pass condition. Add the counter and the exit or they will not stop.

**Rule of thumb.** Orchestrator-workers when *what* the subtasks are is unpredictable; evaluator-optimizer when *the quality bar* is checkable.

---

## 33.5 Planning, Task Decomposition & Termination

**Motivate.** Most agent failures are not bad reasoning. They're a loop that never ended, or a plan that drifted from the goal.

**Define.** Planning = producing an explicit list of steps before executing. Decomposition = splitting a goal into checkable subgoals. Termination = the conditions that stop the loop.

**Make the plan visible.** Writing the steps down first (even as text) does two things: it improves the model's own execution, and it makes failure legible to you — you can see *which* step went wrong instead of staring at an opaque trajectory. Anthropic's second principle is exactly this: **prioritise transparency.**

**Termination conditions, in order of reliability:**

1. **The model says it's done** (it stops requesting tools) — usually works, sometimes lies.
2. **A hard iteration cap** — always include one.
3. **A budget** on tokens, wall-clock, or tool calls.
4. **A verifier's pass** — a check that the *result* meets the goal, not just that the loop ended.

**Rule of thumb.** Every loop needs a counter and a budget, and the best ones also need a verifier. "It stopped" is not the same as "it finished".

---

## 33.6 Failure Modes: Loops, Tool Thrash, Runaway Cost

**Motivate.** Agents fail differently from functions, and the failures are cheap to prevent and expensive to discover in production.

| Failure | What it looks like | The fix |
|---|---|---|
| **Infinite loop** | same tool, same arguments, forever | iteration cap + detect repeated calls with identical args |
| **Tool thrash** | calling tool after tool without converging | fewer, clearer tools (Step 32.5); a plan; a budget |
| **Runaway cost** | one question, forty model calls | hard call budget; route easy work to cheap models |
| **Context bloat** | the window fills with tool output; quality drops | return only needed fields; compact/summarise (Step 35) |
| **Compounding error** | step 3 was wrong; steps 4–9 build on it | gates between steps (33.3); verify, don't just proceed |
| **Silent drift** | it "succeeds" at the wrong task | explicit plan + a verifier against the *original* goal |
| **First-success anchoring** | takes a poor plan because it came first | evaluator-optimizer with a pass criterion |

**Rule of thumb.** Every one of these is cheaper to prevent with a counter, a budget, and a verifier than to debug from a trace after a bill arrives.

---

## 33.7 The Augmented LLM

**Motivate.** Every pattern above is composition. Get the *part* right and the patterns get easier.

**Define.** One LLM plus three capabilities — and the interface to each is a design decision:

- **Retrieval** → what can it look up, and does it know *when*? (Steps 8–12.)
- **Tools** → what can it do, and are the descriptions unambiguous? (Step 32; Anthropic calls this the **ACI**, the agent-computer interface, and says to invest in it like HCI.)
- **Memory** → what persists across turns, and what gets dropped?

**The lesson from the field:** teams that spent their effort on *tool and interface design* got further than teams that added orchestration. The tool list is the product.

**Rule of thumb.** If your agent behaves badly, improve the augmented LLM before adding a pattern. Re-read 32.5 — descriptions are prompts — and treat the ACI as seriously as any UI.

---

## Pitfalls

1. **Reaching for an agent when a function chain would do.** The most common and most expensive mistake.
2. **No iteration cap.** It will loop. Not "might".
3. **No budget.** Forty tool calls per question is a pricing incident, not a bug report.
4. **No verifier.** "It stopped" ≠ "it's correct".
5. **An opaque plan.** If you can't see the steps, you can't debug the failure.
6. **Frameworks before understanding.** You can't tell a framework limitation from your own bug until you've built the loop yourself.
7. **Skipping the augmented-LLM work.** Fancy orchestration over vague tools and a bad retriever is complexity spent in the wrong place.
8. **Adding patterns "just in case".** Every layer is a permanent tax on latency, tokens, and debugging.

---

## Quick Reference

| Situation | Pattern |
|---|---|
| Fixed subtasks, one after another | **Prompt chaining** |
| Distinct categories need different handling | **Routing** (also your cost lever) |
| Independent subtasks, or want confidence | **Parallelization** (sectioning / voting) |
| Subtasks unknown until you see the input | **Orchestrator-workers** |
| Clear quality criteria, iteration helps | **Evaluator-optimizer** |
| Next step depends on the last result | **Agent** (ReAct loop) |
| You can draw the flow chart | **Workflow** — do that instead |
| Bounds needed | iteration cap + call/token budget + a verifier |

---

## Theory Summary

- **The choice is who owns the graph.** Workflow = you wrote the paths. Agent = the model decides. Pick deliberately and be able to defend it.
- **Everything is built from one augmented LLM** — retrieval, tools, memory. The interface to those three is the highest-leverage work you'll do.
- **The five patterns are composable and cheap.** Prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer cover most real tasks, and each is a few dozen lines — versus thousands for the framework that would hide them.
- **Autonomy trades certainty for flexibility.** Take the trade only when the task genuinely can't be enumerated.
- **Every loop needs three things:** a counter, a budget, and a verifier. All three failures in 33.6 are prevented by them.
- **Simplicity, transparency, and the ACI.** Anthropic's three principles, and they're the ones that survive contact with production.

---

## Deliverable

**`Phase 1(AI)/STEP 33/step33-agent-patterns/`**

- **`patterns.py`** — all five patterns implemented against a **`ScriptedLLM`** (a deterministic fake that returns canned responses), so the artifact runs with **zero API calls and zero quota**: `prompt_chain`, `route`, `parallel_section`/`parallel_vote`, `orchestrator_workers`, `evaluator_optimizer`. Each is ~10–20 lines, which is the point: compare that against the framework you'd otherwise import.
- **`choose.py`** — the **judgment** half, turned into code: given a task's traits (can you enumerate the steps? is the step count knowable? is cost bounded? is the output verifiable?), it recommends workflow-vs-agent and names the pattern, with its reasoning printed. This is the part interviews probe, so it's worth making explicit.
- **`demo.py`** — runs every pattern and prints its trace, so you can see the control flow each one creates.

**Design notes:** the `ScriptedLLM` keeps it runnable offline and makes the *patterns* the subject rather than the model. Swapping it for a real client is a one-line change at the call site — the same trick as Step 31's demo.

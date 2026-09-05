# Step 16: Prompt Engineering

> **What it covers:** System prompt design, few-shot examples and output formatting, chain-of-thought and reasoning-model prompting, prompt templating/versioning/A-B testing, and failure modes — the highest-leverage control surface you have over an LLM.

---

## The Problem

You call an LLM and it gives you *something* — but not what you actually need. It's too verbose, or it refuses, or it hallucinates a number instead of saying "I don't know," or it returns free-form prose when you wanted JSON. You could fix any one of these by swapping models, but a model swap is expensive, slow, and often doesn't fix the real issue: the model didn't understand what you wanted.

Prompt engineering is the fix that costs nothing but attention. A clearer system prompt, one good example, or a single instruction like "return JSON only" changes output more reliably than moving up a model tier — and it's the control surface you have on every call, in every step of this course from here on. The problem is that "just write a better prompt" is vague until you know *which* lever to pull.

---

## Foundational Concepts

### A prompt is a specification, not a conversation opener

The single biggest mindset shift: the model has no context about your task, your norms, or what "good" looks like. It's a brilliant new employee who lacks every piece of context you take for granted. So a good prompt is a *specification* — precise about the output format, the constraints, and what "done" means — not a vague request you'd hope a colleague infers from context. Anthropic's golden rule: show your prompt to a colleague with minimal context; if they'd be confused, the model will be too.

### Where instructions live: system vs. user

Instructions sit in two places with different weights. The **system prompt** (Step 15) carries persistent, task-level instructions — who you are, what you do, hard rules — and it persists across every turn. The **user message** carries the specific task and data. The practical rule: put *stable identity and rules* in the system prompt, put *this particular input and request* in the user message.

### The model is pattern-matching, not reasoning (usually)

Non-reasoning models generate the most likely next token. This is why examples work so well: you're not "teaching" the model so much as showing it the distribution of outputs you want, and it imitates the pattern. It also explains most failure modes — if the pattern isn't in the prompt or the training data, the model guesses.

---

## 16.1 — System Prompt Design & Role Setting

### The role is a dial, not decoration

Setting a role in the system prompt focuses behavior and tone. Even one sentence helps:

```python
system = "You are a senior Python engineer who reviews code for bugs and security issues."
```

The role does real work: it activates the model's training distribution for that persona — the vocabulary, the level of detail, the conventions. "You are a tax accountant" and "you are a curious student" produce different answers to the same question, because they sample from different parts of the model's learned distribution.

### Be clear and direct

State exactly what you want. If you want extra thoroughness, ask for it — don't rely on inference:

```
Bad:  "Create an analytics dashboard."
Good: "Create an analytics dashboard. Include as many relevant features as possible
       and go beyond the basics to a fully-featured implementation."
```

Two more rules that consistently improve results:

1. **Give instructions as sequential steps** (numbered list) when order or completeness matters.
2. **Tell the model what to do, not what not to do.** "Write in smoothly flowing prose paragraphs" beats "don't use bullet points" — the negative form leaves the model guessing what you *do* want.

### Give the *why*, not just the *what*

Context and motivation help the model generalize. This is one of the most underused tricks in practice:

```
Bad:  "NEVER use ellipses."
Good: "Your response will be read aloud by a text-to-speech engine, so never use
       ellipses — the engine won't know how to pronounce them."
```

The model is smart enough to extrapolate from the explanation to other punctuation or phrasing choices you didn't list.

---

## 16.2 — Few-Shot Examples & Output Formatting

### Examples steer format, tone, and structure

**Few-shot prompting** means putting 2–5 worked examples in the prompt. It's the most reliable way to control output *shape*, because the model imitates the pattern you show. Three properties make examples good:

- **Relevant** — mirror your actual use case, not a toy one.
- **Diverse** — cover edge cases so the model doesn't learn an unintended pattern (e.g., all examples are "yes" so it learns to always say yes).
- **Structured** — wrap them in tags (`<example>`, or `<examples>` around multiple) so the model can tell examples apart from instructions.

```xml
<instructions>
Classify each support ticket as billing, technical, or account.
Return JSON with a single "category" field.
</instructions>

<examples>
  <example>
    <input>I was charged twice for my subscription</input>
    <output>{"category": "billing"}</output>
  </example>
  <example>
    <input>The app crashes when I open it</input>
    <output>{"category": "technical"}</output>
  </example>
</examples>

<input>The login page won't load my saved password</input>
```

### Output formatting: explicit beats implied

Three levers, in order of reliability:

1. **Specify the format directly** — "Return valid JSON with these fields..."
2. **Use XML tags** — "Write the answer inside `<answer>` tags" gives you a clean parse boundary.
3. **For strict schemas, use tool calls or Structured Outputs** (Step 17 / Step 32) instead of hoping the prompt is enough. Prompt-and-parse is a fallback, not the first choice, when you need guaranteed structure.

One subtle but real effect: **the formatting of your prompt influences the formatting of the output.** A prompt written in clean markdown tends to produce markdown-y output. If you want plain prose, write the prompt in plain prose.

---

## 16.3 — Chain-of-Thought & Reasoning-Model Prompting

### Two different situations, easily confused

This is the most common point of confusion in 2026, so keep them separate:

- **Reasoning models** (models with built-in thinking) *already* reason before answering. You generally do **not** prompt them with "think step by step" — their internal thinking is on, and adding manual CoT instructions can even *hurt* by adding tokens and latency without improving the answer.
- **Non-reasoning models** don't think unless you make them. **Chain-of-thought (CoT)** — asking the model to work through the problem in steps before answering — measurably improves accuracy on math, logic, and multi-step tasks.

### CoT on a non-reasoning model: the pattern

```xml
<instructions>
Solve the problem step by step. Put your reasoning in <thinking> tags, then
your final answer in <answer> tags.
</instructions>
```

Separating reasoning from the answer with tags has two benefits: you can strip the thinking before showing the answer to a user, and you can *see* where the model went wrong when it fails.

### When CoT helps, when it hurts

| | Helps | Hurts |
|---|---|---|
| **When** | Multi-step math/logic, debugging, planning | Simple classification, extraction, single-step answers |
| **Why** | Forces intermediate steps that prevent a wrong jump to the answer | Adds tokens and latency with no accuracy gain, and can overcomplicate trivial tasks |

The rule of thumb: **match the technique to the task's reasoning depth.** A "what's the sentiment of this sentence" prompt doesn't need CoT; "debug why this pipeline fails" does.

### Reasoning models: prompt the *outcome*, not the process

For reasoning models (e.g., models with adaptive thinking), the guidance flips:

- **Don't prescribe hand-written step-by-step plans.** A general "think carefully about this" often beats a human's scripted steps, because the model's reasoning exceeds what you'd prescribe.
- **Control *effort*, not thinking.** Reasoning models expose an effort/depth knob (and possibly a thinking budget) rather than you manually writing out the steps.
- **Watch for overthinking.** On hard reasoning models, asking for verification you don't need can add tokens and latency — verify *only* against criteria that matter.

---

## 16.4 — Prompt Templating, Versioning & A/B Comparison

### Templates: separate the fixed from the variable

A **prompt template** splits your prompt into a stable skeleton and variable slots. The variable parts (user input, retrieved context, few-shot examples) get injected at runtime; the fixed parts (system instructions, format rules) stay constant.

```python
SYSTEM = "You classify support tickets. Return JSON with a 'category' field."

USER_TEMPLATE = """
Classify this ticket:

<ticket>
{ticket_text}
</ticket>
"""

prompt = USER_TEMPLATE.format(ticket_text=raw_ticket)
```

The template is where you put the stable structure (tags, format rules); the `.format()` slot is where dynamic data flows in. This is the seam that makes everything else in this section possible — you can't A/B test or version a prompt that's a hand-edited string inlined in code.

### Versioning: prompts are code

A prompt that changes behavior should be treated like a code change: stored in a file (or a table), with a version, a changelog, and a way to roll back. Inline string edits have no history and can't be diffed. The minimum viable versioning is: prompts live in their own files/module, and every change to one goes through the same review and commit flow as code.

### A/B comparison: measure, don't vibe

You can't tell which prompt is better by eyeballing one output. The workflow:

1. Build a small eval set — 20–50 representative inputs with expected outcomes (Step 30/76 formalize this).
2. Run both prompts over the same set.
3. Score on a metric (accuracy, format validity, task-specific correctness), not "looks better."

The key discipline: **change one variable at a time.** If you rewrite the system prompt *and* add examples *and* change the model in the same experiment, you don't know which change moved the needle.

---

## 16.5 — Failure Modes

### Ambiguity: the model guesses your intent

When a prompt leaves room for interpretation, the model picks one — often not the one you meant. "Summarize this" (how long? what style? for whom?) produces wildly different outputs run to run. The fix is specificity: state the audience, length, format, and what to leave out. Every ambiguity you don't resolve, the model resolves for you, and you pay for the wrong answer.

### Over-constraint: too many rules fight each other

The opposite failure. A prompt with 15 hard rules, several of which conflict ("be concise" + "be thorough" + "cover every edge case"), produces a model that's confused about priority and violates at least one. The fix is to **prioritize explicitly** — "if these conflict, X wins" — or reduce the rule count to the few that actually matter for the task.

### Hallucination triggers

Hallucination (confident, plausible, wrong output) is most common when the model is asked to produce facts it wasn't given. The specific triggers to watch for:

- **Asking for specific facts/numbers** the prompt doesn't contain ("what was the revenue in Q3?") with no source in context.
- **Leading questions** ("why did the company fail?") that assume a premise — the model often accepts the premise and invents a reason.
- **Forcing an answer** when "I don't know" or "insufficient information" is the correct response.

The mitigations: give the model a way to say it doesn't know; provide the source material in-context rather than asking from memory; and ask the model to quote from the context first before answering (this forces grounding — the model focuses on what's actually there, not what it imagines).

---

## Pitfalls

1. **Writing a vague prompt and blaming the model.** If a colleague without context would be confused, the model is too. Be specific first.
2. **Negative instructions only.** "Don't do X" leaves the model guessing what to do. Pair every "don't" with a "do this instead."
3. **No examples when you need consistent format.** If output shape matters, show 2–5 examples; prose instructions alone are fragile.
4. **Homogeneous examples.** All-positive examples teach the model to always answer "yes." Vary them deliberately.
5. **Adding "think step by step" to a reasoning model.** It already thinks; the instruction adds cost, not accuracy.
6. **Over-constraining with conflicting rules.** More rules isn't more control — it's more ways to fail. Prioritize instead.
7. **Not separating reasoning from answer.** Without tags, you can't strip the thinking for users or debug the failure.
8. **Editing prompts inline with no versioning.** An un-versioned prompt is an unreproducible result; treat prompts like code.
9. **Judging prompts by vibes.** One output can't tell you which prompt is better. A/B over a small eval set.
10. **Asking for facts not in context, with no "I don't know" escape.** This is the #1 hallucination trigger; give the model an out.

---

## Quick Reference

| Goal | Lever |
|---|---|
| Consistent output format | Few-shot examples + explicit format instruction |
| Persistent rules/identity | System prompt |
| Better multi-step accuracy (non-reasoning model) | Chain-of-thought with `<thinking>`/`<answer>` tags |
| Reasoning model | Prompt the outcome; control effort, don't script steps |
| Strict schema | Tool calls / Structured Outputs, not prose |
| Grounding against hallucination | Provide source in context; ask for quotes first |
| Reusable prompts | Template with `.format()` slots |
| Track prompt changes | Version in files/module, review like code |
| Compare two prompts | A/B over a 20–50 input eval set, one variable at a time |
| Fix ambiguity | State audience, length, format, exclusions |
| Fix over-constraint | Fewer rules, explicit priorities |

---

## Theory Summary

**The prompt is the control surface, and it's mostly about removing ambiguity.** The model has no idea what you want beyond what you write. Every word you add that disambiguates — the role, the format, an example, the *why* — narrows the space of possible outputs toward the one you actually need. Most prompt engineering is just "be more specific" done deliberately rather than accidentally.

**Examples are the strongest signal you can send.** Because the model is pattern-matching, a worked example transmits more information about output shape than any amount of prose. Three to five diverse, relevant examples beat a paragraph of formatting instructions — and the two together beat either alone.

**Reasoning is a property of the model, not something you always add.** The 2026 split is: reasoning models think internally (so you prompt the *outcome* and control effort), while non-reasoning models need explicit chain-of-thought to get the same effect. Applying the wrong technique to the wrong model wastes tokens without improving output.

**Prompts are code, and should get the same treatment.** Version them, review them, and test them on an eval set rather than eyeballing one response. The discipline of "one variable at a time" is what turns prompt tweaking from superstition into engineering.

**Failure comes from two directions: too little specificity, or too much.** Ambiguity makes the model guess; over-constraint makes it contradict itself. The skill is finding the minimum set of constraints that fully pins down the task — and explicitly resolving the conflicts that remain.

---

## Deliverable

**`Phase 1(AI)/step16-prompting/`** — a small prompt-engineering lab that reuses your Step 15 SDK setup:

- **`prompts.py`** — a versioned prompt module (not inline strings): a system prompt, a templated user prompt with `.format()` slots, and 3 few-shot examples for one concrete task (e.g., support-ticket classification into `billing`/`technical`/`account`).
- **`ab_test.py`** — a script that runs two prompt variants (e.g., with vs. without few-shot examples, or with vs. without a role) over a 20–30 input eval set, and prints a side-by-side score (format validity + category accuracy) so you can see which wins by measurement, not vibes.
- **`hallucination_demo.py`** — one script showing the failure mode: ask the model for a fact *not* in context (it invents one), then the fixed version that provides the source in-context and gives an "I don't know" escape — and show the difference.

**Prove it:** run `ab_test.py` and paste the win/loss numbers; run `hallucination_demo.py` and capture the before/after. Commit all three files.

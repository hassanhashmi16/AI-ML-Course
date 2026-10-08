# Step 30: RAGAS

> **Covers:** how to score the *answer side* of a RAG system — faithfulness, answer relevancy, context precision, context recall — plus the machinery underneath them (LLM-as-judge), how that machinery lies (bias, self-evaluation, JSON failures, drift), how to calibrate it against humans, how to generate a golden dataset instead of hand-writing one, the metrics beyond the four, and how to wire the whole thing into CI so a regression fails a build.

---

## The Problem

Your RAG system answers "June 29th, 2007." The reference says "June 29, 2007." Exact match scores **zero**. A human scores it 100%. Now multiply that by 10,000 test cases, and again by every change you make to chunking, the retriever, the prompt, or the model. You need a scorer that understands *meaning*, runs cheaply at scale, does not lie about regressions, and tells you **which** part broke.

Step 16 measured retrieval — did the right *passages* come back (recall@k, MRR, nDCG). It said nothing about whether the final **answer** was truthful or even on topic. A system can retrieve perfectly and still hallucinate. RAGAS is the other half.

---

## Foundational Concepts

### RAG quality is two separable questions

This split is the single most useful idea in this step, because it tells you where to look when something is wrong:

| Question | What it measures | Tool |
|---|---|---|
| **Did we retrieve the right passages?** | the retriever | recall@k, MRR, nDCG (your Step 16 eval), RAGAS *context precision* / *context recall* |
| **Did the model use them honestly?** | the generator | RAGAS *faithfulness* / *answer relevancy* |

If faithfulness drops but context recall is fine, the retriever is innocent and the prompt or model changed. If context recall drops, no prompt can save you: the answer was never in the context to begin with. **Measure them separately or you will debug the wrong layer.**

### Reference-free vs reference-based

- **Reference-free** — scores an answer using only the question, the answer, and the retrieved context. No human-written "correct answer" needed. This is what makes RAGAS practical: writing references for thousands of cases is the part nobody does.
- **Reference-based** — compares against a gold answer (context recall needs this; answer correctness does too).

Faithfulness and answer relevancy are reference-free. Context recall is not. That asymmetry is worth remembering, because it decides how expensive a metric is to adopt.

### The hidden ingredient: LLM-as-judge

None of these metrics is a formula over strings. Each one is an **LLM prompted to score something against a rubric**. "Faithfulness" is really: *break the answer into claims, and ask a model whether each claim is supported by the context.* That is the engine in 30.6, and everything in 30.1–30.4 is a prompt built on top of it. **Understand the engine before the dials.**

### The four metrics at a glance

| Metric | The question it answers | Needs a reference? |
|---|---|---|
| **Faithfulness** | Is every claim in the answer supported by the retrieved context? | no |
| **Answer relevancy** | Does the answer actually address the question asked? | no |
| **Context precision** | Of the chunks we retrieved, how many were actually useful? | no (uses the question) |
| **Context recall** | Did retrieval return everything needed to answer? | **yes** (a gold answer) |

A near-universal shape: all four land in **0–1, higher is better**, and all four are *proxies*, not truth. Treat them as a smoke detector, not a verdict.

---

## 30.1 Faithfulness

**Motivate.** This is the hallucination metric. Everything else can be perfect and the system still fails if the model invents a fact.

**Define.** Faithfulness = the fraction of claims in the answer that are entailed by the retrieved context. It is a *groundedness* check: not "is the answer true in the world", but "is the answer true **given what we retrieved**".

**Show.** The standard implementation is three steps:

1. **Decompose** the answer into atomic claims (here, with an LLM).
2. **Check** each claim against the context with natural-language inference (NLI) — is the context *entailed by* / consistent with the claim?
3. **Score** = supported claims ÷ total claims.

```python
# Faithfulness, RAGAS-style. `llm(prompt) -> str` is any generation callable.
from transformers import pipeline

nli = pipeline(
    "text-classification",
    model="MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli",  # pinned: NLI backend
    top_k=None,
)


def atomic_claims(answer, llm):
    prompt = f"Break this answer into simple factual claims, one per line:\n{answer}"
    return [line for line in llm(prompt).splitlines() if line.strip()]


def faithfulness(answer, context, llm):
    claims = atomic_claims(answer, llm)
    if not claims:
        return 0.0
    supported = 0
    for claim in claims:
        result = nli({"text": context, "text_pair": claim})[0]
        entailment = next((r for r in result if r["label"] == "entailment"), None)
        if entailment and entailment["score"] > 0.5:   # 0.5 is a choice, not a law
            supported += 1
    return supported / len(claims)
```

**Rule of thumb.** Use faithfulness whenever the answer is supposed to come from documents. A faithfulness of 1.0 with a terrible answer means the model was *faithfully* repeating unhelpful context — which is why you need 30.2 as well.

---

## 30.2 Answer Relevancy

**Motivate.** Faithfulness can be perfect and the answer still useless: "K2 is in the Karakoram" is 100% faithful to the sources and does not answer *"who first climbed it?"*. Grounded ≠ relevant.

**Define.** Answer relevancy = does the answer address the question that was actually asked.

**Show.** The clever trick RAGAS uses avoids needing a reference answer: **generate questions the answer could have been the answer to**, then measure how close those are to the real question.

```python
import numpy as np

def answer_relevancy(question, answer, encoder, llm, n=3):
    prompt = f"Write {n} questions this answer could be the answer to:\n{answer}"
    generated = [line for line in llm(prompt).splitlines() if line.strip()][:n]
    if not generated:
        return 0.0
    q_vec = np.asarray(encoder.encode([question], normalize_embeddings=True)[0])
    g_vecs = np.asarray(encoder.encode(generated, normalize_embeddings=True))
    return float(sum(q_vec @ g for g in g_vecs) / len(g_vecs))
```

**Why it works:** if the answer implies *different* questions than the one asked, the similarity drops. That is exactly the "answered something adjacent" failure, caught without a gold answer.

**Rule of thumb.** Reach for it whenever a model is allowed to be conversational — it catches the model wandering off, which faithfulness never will.

---

## 30.3 Context Precision

**Motivate.** Retrieval that returns 20 chunks when 2 matter buries the signal in the prompt and wastes tokens. Quality of *what we fed in* is a score of its own.

**Define.** Context precision = of the chunks retrieved, **how many were actually relevant to the question** (and, in RAGAS's ranking-aware form, whether the relevant ones came *first*).

**Show.** Give the judge the question and the retrieved chunks, and ask which were useful:

```python
def context_precision(question, chunks, llm):
    listing = "\n".join(f"[{i+1}] {c}" for i, c in enumerate(chunks))
    prompt = (
        f"Question: {question}\n\n"
        f"Retrieved passages:\n{listing}\n\n"
        "Return the numbers of the passages that are useful for answering the "
        "question, one per line, and nothing else."
    )
    useful = {int(x) for x in llm(prompt).split() if x.isdigit()}
    return len(useful) / len(chunks) if chunks else 0.0
```

**Rule of thumb.** Watch this one when you change chunk size, `top_k`, or your fusion. It is the cheapest way to see that you started over-fetching.

---

## 30.4 Context Recall

**Motivate.** The failure that no prompt can fix: the answer was never in the context. You can't ground a fact you didn't retrieve.

**Define.** Context recall = of the claims needed to produce the correct answer, **how many are present in the retrieved context**. It needs a **reference answer**, because "everything needed" has to be defined by someone.

**Show.**

```python
def context_recall(reference_answer, context, llm, nli):
    # 1. the reference answer defines what SHOULD have been recoverable
    needed = atomic_claims(reference_answer, llm)
    # 2. is each needed claim supported by the retrieved context?
    supported = sum(
        1 for claim in needed
        if any(r["label"] == "entailment" and r["score"] > 0.5
               for r in nli({"text": context, "text_pair": claim})[0])
    )
    return supported / len(needed) if needed else 0.0
```

Same machinery as faithfulness, different inputs: faithfulness slices the *generated* answer; recall slices the *reference* answer. Low precision + high recall = retrieval works but is wasteful. Low recall = retrieval is broken.

**Rule of thumb.** If context recall is low, stop tuning the prompt. Go fix ingestion, chunking, or `top_k`. This single number decides which half of your system to work on.

---

## 30.5 `evaluate()` and Building a Golden Dataset

Everything above is a function. RAGAS wraps it into one entry point that takes a table of rows and returns a table of scores:

```python
# Shape of the modern API (RAGAS ≥ 0.2). Pin the version; this API moved a lot.
from ragas import evaluate
from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
from ragas.metrics import (
    Faithfulness, ResponseRelevancy, LLMContextPrecisionWithoutReference,
    LLMContextRecall,
)

dataset = EvaluationDataset(samples=[
    SingleTurnSample(
        user_input=q,
        response=answer,                 # what your system produced
        retrieved_contexts=chunks,       # what retrieval returned
        reference=gold_answer,           # only needed for reference-based metrics
    )
    for q, answer, chunks, gold_answer in run_my_pipeline(questions)
])

report = evaluate(
    dataset=dataset,
    metrics=[
        Faithfulness(),
        ResponseRelevancy(),
        LLMContextPrecisionWithoutReference(),
        LLMContextRecall(),          # ← the one that needs `reference`
    ],
)
print(report)          # a table, one row per sample, one column per metric
```

**The four columns you must supply** — and note that three of them come free from a system you already built:

| Column | Where it comes from |
|---|---|
| `user_input` | your question set |
| `retrieved_contexts` | `hybrid_search()` — you already have this |
| `response` | `answer_question()` — you already have this |
| `reference` | the only part you must write by hand (or generate — see 30.8) |

**Building the golden set.** The pragmatic recipe, in priority order:

1. **Answer from the corpus, then write the reference yourself.** Ask your system a question, read the retrieved chunks, and write the *correct* answer in one sentence. Ten of these beats a hundred generated ones.
2. **Stratify deliberately.** Not ten questions of the same type. Include: a thematic question, an exact-fact question, a nickname/alias question, a multi-hop question ("who climbed X and what else did they do"), and a question the corpus **cannot** answer (to test honesty — the system should refuse, not invent).
3. **Freeze it.** Commit it. A dataset you keep editing cannot measure change over time (30.10).
4. **Then scale it with generation** — 30.8 — once you trust the shape.

**Rule of thumb.** 20–50 hand-written, stratified, committed questions is a real eval. Ten thousand generated ones you never read is theatre.

---

## 30.6 LLM-as-judge: How These Metrics Actually Score, and How They Lie

Every metric above is an LLM with a rubric. That buys judgment at ~$0.003/case and loses determinism, so know the failure modes cold. They are not edge cases; they are the default.

**1. Judge bias — the judge's taste leaks into your scores.**
- *Length bias:* longer answers score higher even when wrong.
- *Self-preference:* judges favour text from their own model family. **If your generator and judge are the same model, scores inflate by roughly 10–20%.** Use a different family for the judge than for the generator.
- *Style bias:* answers that match the judge's prompt cadence score higher.

**2. JSON parsing failures — the silent data loss.** The judge returns malformed JSON, the field is `NaN`, and the aggregate quietly drops the row. Your score improves because your failures disappeared. This is a known RAGAS pain point: **wrap every judge call in try/except, count the failures, and print them.** A run with a 10% parse-failure rate is not a score, it's a rumour.

**3. Drift under model versions.** Upgrade the judge and every metric moves — including on unchanged code. **Freeze the judge model and its version** in config, next to your embedding and generation pins, and treat a judge upgrade as a change that needs a parallel baseline run.

**4. Aggregates hide catastrophes.** A mean faithfulness of 0.85 can contain 5% of answers at zero. Always look at the **bottom decile**, not just the mean.

**Rule of thumb.** A judge is a measuring instrument. Instrument it (version it), check it against reality (30.7), and watch its error rate. Never report a single number from an uncalibrated judge.

---

## 30.7 Calibration: Does the Judge Agree With Humans?

**Motivate.** An uncalibrated judge is a random number generator with good manners. If your score doesn't correlate with human judgment, every decision you make from it is noise.

**Define.** Calibration = the correlation between the judge's scores and human scores on the same examples (Spearman rank correlation, ρ, for ordinal 0–1 scores).

**Show.**

1. Hand-label **50–100** examples yourself, 0–1.
2. Score the same examples with the judge.
3. Compute **Spearman ρ**.

```python
from scipy.stats import spearmanr

rho, p = spearmanr(human_scores, judge_scores)
print(f"rho={rho:.2f}")   # want >= 0.7 before trusting the judge
```

**Interpretation, plainly:**

| ρ | What it means |
|---|---|
| ≥ 0.7 | The judge tracks human judgment. Trust it for A/B comparisons. |
| 0.4–0.7 | Directionally useful, not decision-grade. Loosen thresholds; read the failures. |
| < 0.4 | Noise. Fix the rubric (make the criteria explicit) or change the judge model. |

**Rule of thumb.** Calibrate once per judge model, per metric, and re-calibrate when you change either. The hand-labelled set is the most valuable asset you own — it's the only ground truth about "good" you have.

---

## 30.8 Synthetic Test-Set Generation — a Golden Dataset Without Hand-Labelling

**Motivate.** Hand-writing 500 references is the reason most evals stop at 20. But 20 questions cannot distinguish a 2-point improvement from luck.

**Define.** Generate questions **from the corpus** instead of from your imagination. RAGAS ships a generator that builds a knowledge graph from your documents, then writes questions whose answers are *known by construction* (because the source passage is known).

**Show — the shape:**

```python
from ragas.testset import TestsetGenerator

generator = TestsetGenerator(llm=judge_llm, embedding_model=embedder)
testset = generator.generate_with_langchain_docs(
    documents,        # your chunks
    testset_size=100, # start small
)
# Each row carries a question AND the reference passage it came from,
# so `reference` and `retrieved_contexts` fall out of the data itself.
```

**The catch, and it is the whole point:** synthetic questions inherit the *vocabulary of the source text*. A generated question says "K2", because the article says "K2". It will never say "Savage Mountain". So a synthetic set **over-estimates** your system on exactly the queries real users type — the nickname/vague ones. Use it to get volume, keep a hand-written set for realism, and always keep a handful of questions you wrote yourself.

**Rule of thumb.** Generate for scale, hand-write for realism, and never let the generated set be the only gate.

---

## 30.9 Noise Sensitivity & Factual Correctness

The four are the core, not the whole library. Two more earn their place:

**Noise sensitivity** — *does irrelevant context in the retrieved set cause the model to make errors?* Where context precision asks "how much junk did we retrieve", noise sensitivity asks **"did the junk actually break the answer"**. Directly comparable across chunking strategies, and it's the metric that reveals a model that will believe anything you paste in front of it. A system with high precision and high noise sensitivity is one bad retrieval away from a wrong answer.

**Factual correctness** — *does the answer match the reference, claim by claim?* Splits into precision (of the claims the answer makes, how many are in the reference) and recall (of the reference's claims, how many the answer makes). This is the reference-based counterpart to faithfulness: faithfulness compares answer↔context, factual correctness compares answer↔reference. Use both when you have references; a high faithfulness with low correctness means the model faithfully reproduced *the wrong passage*.

**Also in the box** (know they exist, reach for them when the case fits): Context Entities Recall (long-tail entity coverage), Semantic Similarity / BLEU / ROUGE (classical, non-LLM, cheap, and bad at paraphrases), Answer Accuracy and Response Groundedness (NVIDIA's variants), and the agent metrics (Tool Call Accuracy, Agent Goal Accuracy) for when this course reaches agents.

**Rule of thumb.** Start with the four. Add noise sensitivity the first time a chunking change makes answers worse for no obvious reason.

---

## 30.10 Versioned Datasets & CI Regression Gates

**Motivate.** An eval you run once is a screenshot. An eval that runs on every change is a **test**, and tests are what let you refactor without fear — the thing that lets you change the retriever in Project 4 and *know* you didn't break it.

**Define.** Two ingredients: a **frozen** dataset (versioned, never silently edited) and **thresholds** that fail a build.

**Show.** Wrap the metrics in pytest and gate on the things that matter:

```python
import pytest
from ragas import evaluate

FAITHFULNESS_MIN = 0.85
CONTEXT_RECALL_MIN = 0.75

def test_rag_quality():
    report = evaluate(dataset=FROZEN_DATASET, metrics=[Faithfulness(), LLMContextRecall()])
    scores = report.to_pandas()

    # Means are not enough: a catastrophe hides inside a good average.
    assert scores["faithfulness"].mean() >= FAITHFULNESS_MIN
    assert scores["faithfulness"].min() >= 0.4          # bottom-of-the-list guard
    assert scores["context_recall"].mean() >= CONTEXT_RECALL_MIN
```

**The discipline that makes it work:**

| Practice | Why |
|---|---|
| Freeze and tag the dataset (`golden-v1`, `golden-v2`) | An edited set can't measure change; you can't tell a regression from a relabelling |
| Version the judge model alongside the dataset | A judge upgrade moves every number |
| Gate on the **worst cases**, not just the mean | 0.85 mean with 5% zeros is a broken product |
| Recalibrate after changing either | The ρ you measured was for a different instrument |
| Run it on every PR | That's what makes it a test instead of a report |

**Rule of thumb.** If a change can't fail a build, it isn't measured — it's decorated.

---

## Pitfalls

1. **No calibration.** A judge at ρ < 0.4 is noise. Calibrate before you trust a single number you plan to act on.
2. **Self-evaluation.** Same model generates and judges → inflated scores. Use a different family for the judge.
3. **JSON parse failures vanishing.** Unparseable judge output becomes `NaN` and drops out of the mean. Count and report failures.
4. **Reporting only the mean.** A 0.85 average can hide a 5% catastrophic rate. Always surface the bottom decile.
5. **Golden-set rot.** Unversioned, endlessly edited datasets destroy longitudinal comparison. Tag every change.
6. **Synthetic-only datasets.** Generated questions mirror the source vocabulary and overstate performance on real (nickname, vague) queries.
7. **Reference-free metrics where a reference is needed.** Context recall without a gold answer is not a measurement; it's a guess.
8. **Treating a proxy as truth.** RAGAS metrics are detectors, not verdicts. When a score moves, read the actual answers behind it.
9. **Judging cost surprising you.** Judge calls dominate eval cost at scale. Use the cheapest model that clears your calibration floor, and cache judge results per (question, answer) hash.
10. **Measuring one layer and blaming the other.** Faithfulness down ≠ retrieval broken. Use context recall to decide which half to fix.

---

## Quick Reference

| Goal | How |
|---|---|
| Is the answer grounded? | Faithfulness — claims of the answer vs the retrieved context |
| Did it answer the question asked? | Answer relevancy — regenerate questions from the answer, compare |
| Was retrieval wasteful? | Context precision — fraction of retrieved chunks that mattered |
| Was retrieval incomplete? | Context recall — reference claims covered by the context (needs a reference) |
| Score a whole dataset at once | `evaluate(dataset=..., metrics=[...])` |
| Write a reference | Read the retrieved chunks, write one correct sentence. Ten of these beats a hundred generated |
| Generate questions at scale | `TestsetGenerator` — but keep hand-written ones for realism |
| Make the judge trustworthy | Calibrate vs 50–100 human labels; need Spearman ρ ≥ 0.7 |
| Keep the judge honest | Version the judge model; different family from the generator; log parse failures |
| Make it a test | Frozen, tagged dataset + thresholds in pytest, gating on the worst cases |

---

## Theory Summary

- **RAG quality is two questions, not one.** Retrieval (did we fetch the right passages) and generation (did the model use them honestly). Measure them separately, or you will debug the wrong layer. Step 16 covered the first half; this step is the second.
- **The metrics are prompts wearing lab coats.** Faithfulness, relevancy, precision, and recall are all LLM-as-judge rubrics. The rubric *is* the metric: change the rubric, change the number.
- **Every judge is biased and none is versioned by default.** Length, self-preference, and style leak in; parse failures silently delete your worst rows; a judge upgrade moves every historical number. Instrument it like a measuring device, because that's what it is.
- **Calibration is the difference between measurement and vibes.** Correlation against human labels, ρ ≥ 0.7, is the floor for trusting a judge to make a decision.
- **A dataset is an asset with a version.** Frozen, tagged, stratified, and committed. Generated questions give volume; hand-written ones give realism; you need both.
- **An eval that can't fail a build is a decoration.** Freeze the set, set thresholds, gate on the worst cases, run it on every change.

---

## Deliverable

**`Phase 1(AI)/STEP 30/step30-ragas/`**

- **`golden.jsonl`** — a **stratified, hand-written** set of ~10 questions over the eight-thousanders corpus, each with a one-sentence `reference` answer and a `type` tag (`thematic` / `exact` / `alias` / `unanswerable`). The `unanswerable` rows exist to prove the system refuses instead of inventing.
- **`quality_eval.py`** — runs **Project 2's actual pipeline** and scores the answer side of it:
  - `--offline` computes the retrieval-side metrics (**context precision**, **context recall**) with **zero LLM calls**, using the scoring logic from 30.3/30.4 — so it runs under a spent quota;
  - with a judge available it also computes **faithfulness** and **answer relevancy**;
  - prints a per-question table **and the bottom decile**, not just the mean.

**Deliberate design choices, to be explained in the step:**

- **We implement the metrics rather than install RAGAS**, for the same reason we hand-built retrieval in Steps 8–11: the rubric *is* the metric, and writing it is the lesson. It also keeps the artifact dependency-light. Installing RAGAS is a follow-on exercise, not the deliverable.
- **The judge is a different model family from the generator** where the quota allows, and every judge call is wrapped so a parse failure is *counted and printed*, never silently dropped.

**Run it:** `python -m step30_ragas.quality_eval --offline` first (free), then without the flag once judge quota is available.

# AI/ML Engineer, Step by Step

My working roadmap for going from Python fundamentals to building and deploying AI systems.

The rule for every step: **nothing is done until something ships.** A script, a benchmark, a small tool, a working project. No steps that are just "read about X".

## Start here

Open **[`AI_Engineer_StepByStep.html`](./AI_Engineer_StepByStep.html)** in a browser. That's the whole roadmap: every phase, every step, and what each one produces.

## How this repo is laid out

```
AI_Engineer_StepByStep.html   the roadmap (open this first)
Phase 0/                      Python, shell, git, testing, logging
Phase 1(AI)/                  LLM engineering
  STEP 15/ ... STEP 34/       one folder per step
  PROJECTS/                   what the steps build up to
```

Each step folder holds two things:

- **`StepN- Topic.md`** — the notes for that topic: the concept from first principles, plus the trade-offs and pitfalls, not a summary you could have gotten from a blog post
- **`stepN-.../`** — the artifact that step produced

## The projects

The steps stack. A handful together become a retrieval pipeline, and a few more become a working system.

- **Project 1 — Meeting Notes Summarizer.** A CLI that reads a transcript and returns a validated, structured summary. Structured output, Pydantic validation, error handling.
- **Project 2 — Eight-Thousanders RAG Assistant.** A knowledge assistant over the 14 mountains above 8,000 m. Hybrid retrieval, cross-encoder reranking, grounded answers with citations, an API, a UI, and an evaluation suite that scores the retrieval on labelled questions.

## Where this is going

The LLM-engineering phase continues into tool calling, agent design patterns and LangGraph, then evaluation and observability, then the classical ML and deployment phases. The roadmap in the HTML is the source of truth for what's done and what's next.

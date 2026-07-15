# AI Engineer → ML Engineer Roadmap
### From CS Undergrad to Production AI Engineer, with an MLOps-Adjacent Second Layer
**Prepared for Hassan — 4th semester, FAST NUCES Lahore | July 2026 | Pace: 5–10 hrs/week**

---

## How This Roadmap Is Built

Two phases, sequenced deliberately — not because Phase 2 matters less, but because theory retains better once it's anchored to a real system you've already broken and fixed.

- **Phase 1 — AI Engineering** (~8 months): RAG, agents, evals, production deployment. Matches your existing Next.js/FastAPI stack and gets you freelance-ready fastest.
- **Phase 2 — ML Theory + MLOps** (~7 months): The math and infrastructure layer underneath what you built in Phase 1 — embeddings, transformers, Docker/K8s, monitoring.

At 5–10 hrs/week, total runway is roughly **14–15 months**. That's a real estimate, not a marketing number — some weeks will run long, especially the eval and agent stages, which are where most self-taught AI engineers cut corners. Don't cut them here.

**Before either phase starts:** go back through "Opportunity Inbox Copilot" and one other past project. For each one, write out — from memory, no notes — every architectural decision: why this database, why this framework, why this data flow. Anywhere you can't explain it, that's a gap. Close it before writing a single new line of code. This isn't busywork; it's the fix for the exact problem you flagged — vibe-coding now would just be a more expensive version of the same mistake later, at the agent-architecture level instead of the component level.

---

## PHASE 1: AI ENGINEERING (Weeks 1–32, ~8 months)

### Stage 0 — Codebase Audit (Week 1)
**Goal:** Close the vibe-coding gap before adding anything new.

- Re-read "Opportunity Inbox Copilot" end to end. Diagram the architecture from memory, then check it against the actual code.
- For every library/pattern you can't justify, spend 30–60 minutes reading its docs until you can.
- Repeat for one more existing project.
- **Output:** a one-page written explanation of both projects' architectures, good enough to walk a technical interviewer through unaided.

### Stage 1 — Foundations (Weeks 2–5)
**Topics:** LLM APIs (OpenAI, Anthropic, open-source via Ollama/Groq), prompt engineering patterns (few-shot, chain-of-thought, structured output), tokens/context windows/cost math, Pydantic for structured LLM output, async Python for I/O-bound API calls.

**Why it matters:** ~90% of AI engineering roles apply existing LLMs rather than train foundational models — this is the actual day-to-day toolkit.

- **Project 1:** A CLI or small web tool (reuse your Next.js/FastAPI stack) that calls an LLM with structured, validated output (Pydantic schemas), streams responses, and handles rate limits/errors gracefully. Nothing fancy — the point is clean error handling and structured output, not a flashy UI.

### Stage 2 — RAG & Vector Databases (Weeks 6–11)
**Topics:** Embeddings (conceptual, not the math yet — that's Phase 2), chunking strategies (fixed-size vs. semantic vs. recursive), vector databases (pgvector — fits your Postgres stack — plus Chroma or Qdrant for comparison), retrieval quality basics, reranking.

- **Project 2:** A RAG knowledge assistant over a real corpus (your own docs, a domain you know, or class materials) — FastAPI backend, Postgres + pgvector, a simple frontend. This is the project you'll keep extending through Stages 3–6.

### Stage 3 — Evals (Weeks 12–15)
**Topics:** RAGAS metrics (faithfulness, answer relevance, context precision/recall), building a versioned eval dataset by hand, LangSmith or Braintrust for tracing, what a "regression gate" is and why it matters.

**Why this stage is non-negotiable:** in 2026's hiring market, evals are the line between an AI enthusiast and an AI engineer. A resume without evaluation work is read as "unevaluated features shipped" — a disqualifier at serious companies. This is also your stated differentiation strategy — lean into it here, don't just check the box.

- **Project 2, extended:** Add an eval harness to the RAG assistant — a versioned test set, numeric scores (faithfulness/relevance/precision), and a script that flags regressions. This is the artifact that turns "I built a RAG demo" into "I built a RAG system I can prove works."

### Stage 4 — Agents (Weeks 16–21)
**Topics:** Agent fundamentals (ReAct, tool calling), LangGraph (typed state, graph-based workflows, conditional branching, checkpointing/resumption), CrewAI or PydanticAI for multi-agent orchestration, MCP (Model Context Protocol) for external tool integration.

- **Project 3:** A multi-step agent (research assistant, support triage bot, or similar) built in LangGraph, with real tool use and checkpointing so it can resume after a failure — not just a single-shot chain.

### Stage 5 — Agentic RAG + Trajectory Evals (Weeks 22–25)
**Topics:** Combining retrieval with agentic control flow, evaluating agent trajectories (not just final answers — did it call the right tools, in the right order, for the right reasons), failure-mode analysis.

- **Project 4 (flagship):** Merge Projects 2 and 3 into an agentic RAG system with a full eval suite covering both retrieval quality and agent trajectory correctness. This is the project to lead with in interviews and freelance pitches — "explain why it doesn't hallucinate" is your stated edge, and this is where you earn the right to say it.

### Stage 6 — Production & Deployment (Weeks 26–29)
**Topics:** FastAPI production patterns (auth, rate limiting, logging), a light pass on Docker (containerize the app — full Docker/K8s depth comes in Phase 2), deployment (Fly.io, Render, or Railway), basic cost/latency monitoring.

- **Output:** Project 4, live at a real URL, with basic auth and logging. It needs to survive someone other than you clicking around in it.

### Stage 7 — Portfolio & Freelance Positioning (Weeks 30–32)
- Write technical case studies for your 2–3 strongest projects: the architecture, the eval results, the trade-offs you made and why. This is what makes a portfolio readable by a hiring manager instead of just a GitHub link.
- Update resume/LinkedIn/portfolio site around the "AI engineering + evals" positioning.
- Start freelance outreach targeting RAG/agent-building gigs — this is your fastest path to income while Phase 2 is underway.

**Phase 1 checkpoint:** by week 32 you should have three defensible projects — a production RAG assistant with evals, a LangGraph multi-agent system, and a deployed agentic RAG flagship — each with a case study you can talk through without notes.

---

## PHASE 2: ML THEORY + MLOPS (Weeks 33–60, ~7 months)

### Stage 8 — Math & Classical ML Foundations (Weeks 33–38)
**Topics:** Linear algebra and probability refresher (targeted at what you'll need for embeddings/attention — not a full course), classical ML (regression, trees, clustering) via scikit-learn, bias-variance tradeoff, evaluation metrics for classical ML.

- **Project 5:** A small classical ML project using your own freelance or portfolio data (e.g., predicting something from real usage data you already have access to). The point is anchoring the theory to something concrete you own.

### Stage 9 — Deep Learning & Transformers from First Principles (Weeks 39–46)
**Topics:** Neural nets and backprop from scratch (at least once, by hand), embeddings math (word2vec → contextual embeddings), attention mechanism and transformer architecture in depth, fine-tuning basics (LoRA/PEFT).

**Why now, not earlier:** you already know what embeddings and attention *do* from Phase 1 — this is where you learn *why* they work, which is exactly the sequencing you flagged as the right way to retain theory.

- **Project 6:** Implement a minimal transformer from scratch, or fine-tune a small open model with LoRA. Either way, connect it explicitly back to the RAG/agent systems from Phase 1 — "here's the math behind why my chunking strategy in Project 4 worked."

### Stage 10 — MLOps Core (Weeks 47–52)
**Topics:** Docker in depth, Kubernetes basics, CI/CD for ML pipelines, model registries (MLflow), experiment tracking (Weights & Biases or Comet).

- **Project 7:** Properly containerize and deploy a model (or revisit Project 4) with a real CI/CD pipeline and model registry — this is the "scarcer skillset" layer that pairs with your AI engineering work.

### Stage 11 — Observability & Infrastructure (Weeks 53–58)
**Topics:** Monitoring and alerting (Prometheus/Grafana), feature stores (Feast), infrastructure-as-code (Terraform), GitOps (ArgoCD), orchestration (Airflow or Kubeflow).

- **Project 8:** Add full monitoring/alerting to your Phase 1 flagship agentic RAG system — latency, cost, eval-score drift over time. This closes the loop between "I built an AI system" and "I run an AI system in production."

### Stage 12 — Integration & Repositioning (Weeks 59–60)
- Fold the MLOps layer back into your flagship project so it's one coherent system, not two separate portfolios.
- Reposition your resume/portfolio around the combined "AI Engineer with MLOps depth" story — this pairing is the rarer, higher-value combination in the current market.
- Revisit freelance/job targeting now that you can credibly cover both the systems layer and the infrastructure underneath it.

---

## Standing Risk to Watch

You flagged this yourself: the danger isn't failing to learn AI engineering, it's declaring victory once it "works well enough" and never circling back for Phase 2. Treat the Stage 8 start date as a real commitment, not a someday — book it on a calendar now, not after Phase 1 "feels done."

---

## Quick Reference: Tools by Stage

| Stage | Core Tools |
|---|---|
| Foundations | OpenAI/Anthropic APIs, Ollama, Pydantic |
| RAG | pgvector, Chroma/Qdrant, FastAPI, Postgres |
| Evals | RAGAS, LangSmith or Braintrust |
| Agents | LangGraph, CrewAI or PydanticAI, MCP |
| Deployment | Docker (light), Fly.io/Render/Railway |
| Math/DL | NumPy, PyTorch, scikit-learn |
| MLOps Core | Docker, Kubernetes, MLflow, GitHub Actions |
| Observability | Prometheus, Grafana, Feast, Terraform, ArgoCD |

---

*Sources consulted for 2026 tooling/market accuracy: LangChain's State of Agent Engineering report, industry roadmap aggregators (technovids.com, letsdatascience.com, dataskew.io), and MLOps tooling surveys (prepzee.com, scaler.com) — all accessed July 2026.*

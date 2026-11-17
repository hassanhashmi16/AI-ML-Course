# WhyTheDiff Project Evidence

Working case study for Step 42, prepared 7 November 2026. Intended audience: reviewers for AI engineering internships and junior LLM application roles. Verify the narrative and contribution descriptions before using them in applications.

## Project Status

WhyTheDiff is implemented locally and packaged with Docker. Public cloud hosting is deferred: attempts to allocate an Oracle Ampere A1 VM in Dubai failed with an out-of-capacity error. A network and deployment stack were saved. There is no verified public application URL.

Source: [standalone repository](https://github.com/hassanhashmi16/whythediff) and [current project README](../PROJECTS/Project-4-WhyTheDiff/README.md).

## Problem and Scope

Developers can inspect a diff to learn what changed while still lacking the reason behind the change. WhyTheDiff accepts a public GitHub repository, a reference, and a question, then investigates relevant code and history. Its report includes sources, a timeline, and distinctions between documented reasons, inferences, and unresolved questions.

The project does not promise to reconstruct a developer's private intent. An explanation can only be as strong as the inspected public evidence. Private repositories are rejected.

## Request Flow

A signed-in user submits a question through the React interface. FastAPI checks the request and account quota, then records a job in a bounded SQLite queue. A single worker starts a supervised investigation process. The LangGraph workflow collects GitHub sources, chunks and indexes evidence, retrieves relevant passages, and calls the generation provider. Citations are matched to stored sources and claims undergo grounding checks. Progress is checkpointed; completed reports remain associated with the submitting account.

Generation uses Groq by default. Embedding and reranking models run locally through FastEmbed, with an embedded Qdrant index. SQLite also stores application state and LangGraph checkpoints. The app therefore needs persistent storage in its current deployment design.

Implementation references:

- [Queue and account state](../PROJECTS/Project-4-WhyTheDiff/api/store.py)
- [Worker supervision](../PROJECTS/Project-4-WhyTheDiff/api/worker.py)
- [Retrieval clients and local Qdrant](../PROJECTS/Project-4-WhyTheDiff/retrieval/clients.py)
- [Checkpoint storage](../PROJECTS/Project-4-WhyTheDiff/agent/persistence.py)
- [Architecture and answer invariants](../PROJECTS/Project-4-WhyTheDiff/docs/architecture.md)

## Decisions and Trade-Offs

**Investigate beyond one retrieval pass.** The workflow can inspect additional evidence and revise an answer after checks. The historical evaluation showed a citation failure corrected on one case, with substantially more model calls and latency. The case study should describe that measured trade-off rather than assert that agents are always better than a baseline.

**Expose uncertainty.** Finding a matching quote does not prove that it supports the claim. Citation validation and semantic grounding are separate controls. Unsupported claims can be removed or downgraded, and the report makes partial results visible.

**Keep a bounded, single-server runtime.** One active investigation, quotas, and process deadlines limit resource use. The trade-offs are waiting jobs, limited throughput, and a dependency on persistent local state. No multi-server scalability or public load-test result is claimed.

**Separate users' work.** Identity, owner-checked access, and account-specific workspaces keep histories and research data associated with their owners. These controls require continued testing on the actual production host; their presence is not a blanket security guarantee.

## Recorded Evaluation

The historical evaluation covered three Flask cases with the same snapshot, generation settings, and report contract for baseline and investigation. These are recorded results from an earlier pipeline, not a fresh benchmark of the latest release.

| CT-002 recorded outcome | One-pass baseline | Investigation |
|---|---:|---:|
| Citation validation | Failed | Passed |
| Model calls | 1 | 7 |
| Recorded latency | 20.951 seconds | 74.097 seconds |

On CT-001, the investigation still ended partial. On CT-003, both workflows avoided inventing an unsupported numerical answer. A fourth case was added later and is not part of this original comparison.

Evidence: [recorded evaluation table and limitations](../PROJECTS/Project-4-WhyTheDiff/docs/architecture.md#evaluation-as-recorded-16-october-2026).

A later model-judged faithfulness check scored old outputs against reconstructed cited-source contexts. For CT-002 it recorded 0.8182 for the baseline and 0.90 for the investigation. This is not "90% accuracy," an independent truth benchmark, or a current full-pipeline result. Preserve the [complete scoring qualifications](../PROJECTS/Project-4-WhyTheDiff/docs/faithfulness-results.md) whenever discussing it.

## Candidate Resume Bullets

Choose two or three according to available space; these are drafts to check against personal ownership and understanding.

- Built a public-repository investigation app using LangGraph and Qdrant to trace code changes and produce cited explanations with explicit uncertainty labels.
- Implemented GitHub OAuth, account-isolated histories, a bounded investigation queue, and checkpoint-based recovery in a FastAPI application.
- Compared one-pass and agent workflows on three labelled Flask cases; documented a corrected citation failure alongside increased model-call count and latency.

A short resume need not carry the Ragas score. The case study can preserve the qualifications without compressing it into a misleading percentage.

## Complementary Course Projects

**Eight-Thousanders RAG Assistant:** a retrieval application over 14 mountains, with dense and keyword search, reciprocal rank fusion, cross-encoder reranking, and a FastAPI/React interface. Its README records an evaluation harness over 20 labelled questions using recall@5, MRR, and nDCG. No numerical improvement is asserted here because a recorded results table has not been verified in this review. [Project README](../PROJECTS/Project-2-RAG-Assistant/README.md).

Candidate bullet: "Implemented dense and keyword retrieval with reciprocal rank fusion and cross-encoder reranking in a pgvector-backed assistant; added a labelled evaluation harness comparing retrieval configurations."

**Research Briefing Agent:** a Python tool-calling loop that searches and reads web sources, writes cited briefings, checkpoints state in SQLite, and recalls session memory. Its documented demos kill and resume a run and show memory injected into a later run. These are demo observations; the README explicitly says there is no automated test suite. [Project README and demos](../PROJECTS/Project-3-Research-Agent/README.md#the-two-demos).

Candidate bullet: "Built a Python research agent with validated tools, SQLite checkpoints, session memory, execution budgets, and per-stage traces; demonstrated recovery after a forced process termination."

## Evidence Still to Add

- A recording of one successful investigation and one uncertainty or failure case, identified by the actual version used.
- A fresh, representative evaluation if the case study is to make claims about the latest pipeline.
- Explicit personal explanations of the main design choices and verification work.
- A working public URL only after hosting, HTTPS, OAuth, persistence, and recovery are verified there.

## Interview Walkthrough

Explain the user question first. Follow it through admission, evidence collection, retrieval, checking, and saved output. Then discuss why an agent helped one observed case, why it increased cost, and why a simpler one-pass workflow remains a useful baseline. Finish with the current hosting and evaluation limitations and the experiment that would resolve the most consequential uncertainty.

# Ragas faithfulness check — 5 November 2026

`eval/score_faithfulness.py` now scores saved reports without generating their
answers again. It uses the project's pinned Ragas 0.4.3 compatibility API and
the configured model provider, with per-case failure reporting and reusable
scores keyed by report hashes. Successful cases are not charged again on retry.

The first run used Groq `openai/gpt-oss-120b` on the reports saved in
`reports/eval/20261017T171957Z/`:

| Case | Baseline | Investigation |
|---|---:|---:|
| CT-001 | 0.50 | 0.75 |
| CT-002 | 0.8182 | 0.90 |
| CT-003 | not applicable | not applicable |

One case initially hit a provider rate limit and completed on retry. CT-003
contains no surviving claims; abstention is not counted as perfect faithfulness.
The raw output is `faithfulness.json` in the ignored evaluation run directory.

**Limits:** These are old reports, not a new evaluation of the changed pipeline.
Their original retrieved passages were not saved, so the scorer reconstructs
contexts from the complete *cited* public Flask PR documents in the source cache.
This measures support relative to those documents; it is not a retrieval-recall
or independent factual-correctness benchmark. CT-004 was not in this saved run.
The judge is model-based, and four scored reports do not establish generality.

New evaluation runs save an `.evidence.json` sidecar with all inspected source
documents. The evaluator labels which context scope it used and rejects missing
or changed citations instead of silently scoring incomplete evidence.

The review also found that an unsupported model summary could survive rejected
claims. New reports derive summaries from surviving claims, and grounding
downgrades rebuild both summary and cited timeline. Old reports and the table
above are retained as measured; they are not rewritten to improve the scores.

```powershell
.\.venv\Scripts\python.exe eval\score_faithfulness.py --run-dir reports/eval/<run>
```

This command makes evaluator-model calls. It does not regenerate investigations.
Ragas reference: [faithfulness](https://github.com/vibrantlabsai/ragas/blob/main/docs/concepts/metrics/available_metrics/faithfulness.md).

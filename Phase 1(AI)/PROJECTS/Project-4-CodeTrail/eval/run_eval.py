r"""Evaluate the baseline RAG workflow against the investigation workflow.

Run from the project folder with:
    .\.venv\Scripts\python.exe eval\run_eval.py

Each labelled case runs through both workflows on the same pinned snapshot,
the same model settings, and the same output contract. The report shows, per
case and workflow: evidence retrieved, rationale correctness, unknown
handling, citation validity, latency, and model calls/tokens (tokens where
the provider reports them).

Disclosure: both workflows share the local Qdrant index and the on-disk
source cache; findings for this repository@snapshot are reset before the run.
Failures stay visible -- they are printed per case and never averaged away.
Every report is saved under reports/eval/<run>/ so later scoring (for example
Ragas faithfulness) can reuse the exact outputs without re-spending calls.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Running a file inside eval/ otherwise places eval/, rather than the project
# folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from langchain_core.messages import HumanMessage  # noqa: E402

from agent.graph import build_graph  # noqa: E402
from agent.memory import clear_findings  # noqa: E402
from agent.state import new_state  # noqa: E402
from agent.tools import ToolContext  # noqa: E402
from console import make_stdout_safe  # noqa: E402
from generation.answer import answer_question, build_llm  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.collect import Collector  # noqa: E402
from ingest.index import index_records  # noqa: E402
from models import Coverage, InvestigationRequest, Report  # noqa: E402
from retrieval.clients import (  # noqa: E402
    build_embeddings,
    build_sparse_embedding,
    build_vector_store,
    collection_name,
    open_qdrant,
    reset_collection,
)
from retrieval.rerank import rerank_documents  # noqa: E402
from retrieval.search import search_evidence  # noqa: E402

CASES_PATH = Path(__file__).parent / "cases.jsonl"


class Meter:
    """Counts model calls and provider-reported tokens for one workflow."""

    def __init__(self) -> None:
        self.calls = 0
        self.tokens = 0


class MeteredModel:
    """Wraps a chat model so every invoke is counted (including structured calls)."""

    def __init__(self, inner, meter: Meter) -> None:
        self.inner = inner
        self.meter = meter

    def bind_tools(self, tools):
        return MeteredModel(self.inner.bind_tools(tools), self.meter)

    def with_structured_output(self, schema, **kwargs):
        return MeteredModel(self.inner.with_structured_output(schema, **kwargs), self.meter)

    def invoke(self, *args, **kwargs):
        self.meter.calls += 1
        result = self.inner.invoke(*args, **kwargs)
        metadata = getattr(result, "response_metadata", {}) or {}
        usage = metadata.get("token_usage") or metadata.get("usage") or {}
        self.meter.tokens += int(usage.get("total_tokens") or 0)
        return result


def load_cases() -> list[dict]:
    return [
        json.loads(line)
        for line in CASES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def score_report(report: Report, expect: dict, issues: list[str]) -> dict:
    """Score one report against the case's expectations; flags, never averages."""
    cited = {excerpt.source_id for claim in report.claims for excerpt in claim.excerpts}
    text = " ".join(
        [report.summary, *[claim.statement for claim in report.claims]]
    ).lower()
    mentions = [term.lower() for term in expect.get("must_mention", [])]
    mention_ok = all(term in text for term in mentions) if mentions else True
    cite_ok = (not expect.get("must_cite_any")) or bool(
        cited & set(expect["must_cite_any"])
    )

    if expect.get("answerable", True):
        rationale_ok = bool(report.claims) and mention_ok
        unknown_handled = None
    else:
        pattern = expect.get("forbid_claim_pattern")
        violated = bool(
            pattern
            and any(re.search(pattern, claim.statement) for claim in report.claims)
        )
        unknown_handled = (not violated) and bool(
            report.unresolved or not report.claims
        )
        rationale_ok = unknown_handled

    return {
        "status": report.status.value,
        "claims": len(report.claims),
        "cited_sources": len(cited),
        "citation_issues": len(issues),
        "citations_valid": not issues,
        "must_mention_ok": mention_ok,
        "must_cite_ok": cite_ok,
        "rationale_ok": rationale_ok,
        "unknown_handled": unknown_handled,
    }


def save_case_report(run_dir: Path, case_id: str, workflow: str, report: Report) -> None:
    path = run_dir / f"{case_id}-{workflow}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")


def main() -> None:
    make_stdout_safe()
    cases = load_cases()
    gh = get_github()
    first = cases[0]
    repo = get_repository(gh, first["repository"])
    snapshot = resolve_ref(gh, first["repository"], first["ref"])
    assert all(
        case["repository"] == first["repository"] and case["ref"] == first["ref"]
        for case in cases
    ), "all cases must share one repository@snapshot for a fair comparison"

    embeddings = build_embeddings()
    sparse = build_sparse_embedding()
    collection = collection_name(snapshot)
    client = open_qdrant()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = PROJECT_DIR / "reports" / "eval" / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    failures: list[str] = []
    try:
        # One index for the whole evaluation: every case's evidence on the
        # same snapshot. Findings are reset so memory cannot leak between runs.
        union = Collector(repo, snapshot)
        try:
            for case in cases:
                for path in case["files"]:
                    union.add_file(path)
                for number in case["pulls"]:
                    union.add_pull(number)
                    union.add_reviews(number)
            all_records = [union.sources[key] for key in sorted(union.sources)]
        finally:
            union.close()
        reset_collection(client, embeddings, collection)
        store = build_vector_store(
            client, embeddings, collection, sparse_embedding=sparse, mode="hybrid"
        )
        index_records(client, store, collection, snapshot, all_records, rebuild=True)
        cleared = clear_findings(client, snapshot)
        print(f"index: {len(all_records)} source(s) @ {snapshot.sha[:7]} | "
              f"findings cleared: {cleared} | run dir: {run_dir.name}")
        print("shared by both workflows: local Qdrant index + on-disk source cache")
        print("tokens = provider-reported (structured calls usually report none)\n")

        header = (
            f"{'case':<8}{'flow':<15}{'status':<10}{'claims':>7}{'cites':>7}"
            f"{'rationale':>11}{'unknown':>9}{'calls':>7}{'tokens':>8}{'ms':>8}"
        )
        print(header)
        print("-" * len(header))

        for case in cases:
            question = case["question"]
            case_collector = Collector(repo, snapshot)
            try:
                for path in case["files"]:
                    case_collector.add_file(path)
                for number in case["pulls"]:
                    case_collector.add_pull(number)
                    case_collector.add_reviews(number)
                case_sources = dict(case_collector.sources)

                # --- Baseline: one retrieval pass, one structured answer.
                baseline_meter = Meter()
                baseline_llm = MeteredModel(build_llm(), baseline_meter)
                started = time.perf_counter()
                candidates, warning = search_evidence(
                    client,
                    embeddings,
                    sparse,
                    snapshot,
                    question,
                    mode="hybrid",
                    source_ids=list(case_sources),
                )
                if warning:
                    raise SystemExit(warning)
                ranked, _ = rerank_documents(question, candidates)
                coverage = Coverage(
                    repository=snapshot.repository,
                    snapshot_sha=snapshot.sha,
                    files_read=sum(
                        1 for record in case_sources.values() if record.kind.value == "file"
                    ),
                    discussions_read=sum(
                        1
                        for record in case_sources.values()
                        if record.kind.value in ("pull_request", "issue")
                    ),
                    comments_read=sum(
                        1
                        for record in case_sources.values()
                        if record.kind.value in ("comment", "review")
                    ),
                )
                baseline_report, baseline_issues = answer_question(
                    question, snapshot, list(case_sources.values()), ranked, coverage,
                    llm=baseline_llm,
                )
                baseline_ms = int((time.perf_counter() - started) * 1000)
                baseline_score = score_report(baseline_report, case["expect"], baseline_issues)
                save_case_report(run_dir, case["id"], "baseline", baseline_report)
                baseline_score.update(
                    {
                        "case": case["id"],
                        "flow": "baseline",
                        "calls": baseline_meter.calls,
                        "tokens": baseline_meter.tokens,
                        "ms": baseline_ms,
                        "evidence_docs": len(ranked),
                    }
                )
                results.append(baseline_score)

                # --- Investigation: the graph over the same evidence boundary.
                investigation_meter = Meter()
                context = ToolContext(
                    repo=repo,
                    snapshot=snapshot,
                    collector=case_collector,
                    client=client,
                    embeddings=embeddings,
                    sparse_embedding=sparse,
                    store=store,
                    collection=collection,
                )
                graph = build_graph(
                    context,
                    llm=MeteredModel(build_llm(), investigation_meter),
                    grader_llm=MeteredModel(build_llm(), investigation_meter),
                    judge_llm=MeteredModel(build_llm(), investigation_meter),
                )
                state = new_state(
                    InvestigationRequest(repository=case["repository"], question=question),
                    snapshot,
                )
                state["sources"] = dict(case_collector.sources)
                state["messages"] = [HumanMessage(content=question)]
                started = time.perf_counter()
                result = graph.invoke(state)
                investigation_ms = int((time.perf_counter() - started) * 1000)
                investigation_report = result.get("report")
                if investigation_report is None:
                    investigation_score = {
                        "status": "no_report",
                        "claims": 0,
                        "cited_sources": 0,
                        "citation_issues": 0,
                        "citations_valid": False,
                        "must_mention_ok": False,
                        "must_cite_ok": False,
                        "rationale_ok": False,
                        "unknown_handled": None,
                    }
                else:
                    investigation_score = score_report(
                        investigation_report, case["expect"], []
                    )
                    save_case_report(
                        run_dir, case["id"], "investigation", investigation_report
                    )
                investigation_score.update(
                    {
                        "case": case["id"],
                        "flow": "investigation",
                        "calls": investigation_meter.calls,
                        "tokens": investigation_meter.tokens,
                        "ms": investigation_ms,
                        "evidence_docs": len(result["sources"]),
                        "tool_calls": result["tool_calls"],
                    }
                )
                results.append(investigation_score)
            finally:
                case_collector.close()

            for row in (baseline_score, investigation_score):
                unknown_cell = (
                    "-" if row["unknown_handled"] is None
                    else ("ok" if row["unknown_handled"] else "FAIL")
                )
                print(
                    f"{row['case']:<8}{row['flow']:<15}{row['status']:<10}"
                    f"{row['claims']:>7}"
                    f"{'ok' if row['citations_valid'] else 'FAIL':>7}"
                    f"{'ok' if row['rationale_ok'] else 'FAIL':>11}"
                    f"{unknown_cell:>9}"
                    f"{row['calls']:>7}{row['tokens']:>8}{row['ms']:>8}"
                )
                if not row["citations_valid"]:
                    failures.append(
                        f"{row['case']}/{row['flow']}: {row['citation_issues']} citation issue(s)"
                    )
                if not row["rationale_ok"]:
                    failures.append(f"{row['case']}/{row['flow']}: rationale check failed")
                if row["unknown_handled"] is False:
                    failures.append(f"{row['case']}/{row['flow']}: unknown handling failed")
                if not row["must_cite_ok"]:
                    failures.append(f"{row['case']}/{row['flow']}: expected citation missing")
                if not row["must_mention_ok"]:
                    failures.append(f"{row['case']}/{row['flow']}: expected term missing")
    finally:
        client.close()

    summary = {
        "run": stamp,
        "snapshot": {"repository": snapshot.repository, "sha": snapshot.sha},
        "disclosure": {
            "index": collection,
            "source_cache": str(PROJECT_DIR / "data" / "cache"),
        },
        "results": results,
        "failures": failures,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\nreports saved under: {run_dir}")
    if failures:
        print(f"FAILED checks ({len(failures)}):")
        for failure in failures:
            print(f"  - {failure}")
    else:
        print("no failed checks in this run")
    print("EVALUATION COMPLETE")


if __name__ == "__main__":
    main()

r"""Exercise Step 9: one retrieval pass -> a validated, cited Report.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_answer.py

Builds the index for a small sample (ctx.py + globals.py + PR #4682 + its
reviews), retrieves and reranks for a known question, then asks the configured
LLM (Groq) for a structured answer. Embeddings, sparse search, and reranking
stay local; only the generation call leaves the machine.

What is verified:
  1. A known question produces a saved report whose claims cite inspected
     sources with quotes that exist verbatim in those records.
  2. Line numbers are derived from the quote's position, not trusted blindly.
  3. Invented source IDs and altered quotations are rejected by validation.
  4. The saved JSON reloads as the shared Report model with the same claims.
"""

import sys
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from config import settings  # noqa: E402
from console import make_stdout_safe  # noqa: E402
from generation.answer import DraftClaim, answer_question, save_report  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.collect import Collector  # noqa: E402
from ingest.index import index_records  # noqa: E402
from models import Report  # noqa: E402
from reporting.citations import validate_claims  # noqa: E402
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

REPO = "https://github.com/pallets/flask"
EXPECTED_SHA = "b17bb9ed563ab2857c0db9a07ec4e6407404c7be"
PR = 4682
FILES = ["src/flask/ctx.py", "src/flask/globals.py"]
QUESTION = "Why did Flask replace the LocalStack-based context storage with direct ContextVar handling?"


def main() -> None:
    make_stdout_safe()
    gh = get_github()
    repo = get_repository(gh, REPO)
    snapshot = resolve_ref(gh, REPO, "2.2.0")
    assert snapshot.sha == EXPECTED_SHA

    collector = Collector(repo, snapshot)
    try:
        for path in FILES:
            collector.add_file(path)
        collector.add_pull(PR)
        collector.add_reviews(PR)
        records = [collector.sources[key] for key in sorted(collector.sources)]
        coverage = collector.coverage()
    finally:
        collector.close()
    records_by_id = {record.source_id: record for record in records}

    collection = collection_name(snapshot)
    client = open_qdrant()
    try:
        reset_collection(client, collection)
        embeddings = build_embeddings()
        sparse = build_sparse_embedding()
        store = build_vector_store(
            client, embeddings, collection, sparse_embedding=sparse, mode="hybrid"
        )
        index_records(client, store, collection, snapshot, records, rebuild=True)

        candidates, warning = search_evidence(
            client, embeddings, sparse, snapshot, QUESTION, mode="hybrid"
        )
        assert warning is None and candidates
        ranked, rerank_warning = rerank_documents(QUESTION, candidates)
        assert rerank_warning is None and ranked
        print(f"PASS  evidence: {len(candidates)} candidates -> {len(ranked)} reranked")

        report, issues = answer_question(QUESTION, snapshot, records, ranked, coverage)
    finally:
        client.close()

    # 1) The report has valid, verbatim citations.
    assert report.claims, "the answer must contain at least one validated claim"
    assert not issues, f"citation validation reported issues: {issues}"
    for claim in report.claims:
        for excerpt in claim.excerpts:
            record = records_by_id[excerpt.source_id]
            assert excerpt.quote in record.content, "quote is not verbatim"
            assert 1 <= excerpt.start_line <= excerpt.end_line
    labels = ", ".join(sorted({claim.label.value for claim in report.claims}))
    print(f"PASS  claims validated: {len(report.claims)} (labels: {labels})")

    # 2) Invented source IDs and altered quotations must fail validation.
    good = report.claims[0]
    good_excerpt = good.excerpts[0]
    bad_id = DraftClaim(
        statement="invented", label=good.label, source_id="github:nope/repo:sentinel:1",
        quote=good_excerpt.quote,
    )
    bad_quote = DraftClaim(
        statement="altered", label=good.label, source_id=good_excerpt.source_id,
        quote=good_excerpt.quote + " (altered)",
    )
    _, id_issues = validate_claims([bad_id], records_by_id)
    _, quote_issues = validate_claims([bad_quote], records_by_id)
    assert any("unknown source_id" in issue for issue in id_issues)
    assert any("not found verbatim" in issue for issue in quote_issues)
    print(f"PASS  rejected: {id_issues[0]} | {quote_issues[0]}")

    # 3) The saved JSON reloads as the shared Report model.
    path = save_report(report)
    reloaded = Report.model_validate_json(path.read_text(encoding="utf-8"))
    assert len(reloaded.claims) == len(report.claims)
    assert reloaded.snapshot.sha == EXPECTED_SHA
    print(f"PASS  report saved and reloaded: {path.name} "
          f"({path.stat().st_size} bytes, status={reloaded.status})")
    print(f"      summary: {report.summary[:220]}")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

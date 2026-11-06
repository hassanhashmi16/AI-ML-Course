r"""Exercise Step 14: reusable findings across investigations.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_memory.py

Phase 1 saves a validated claim (the real PR #4682 record, quoted exactly)
into the findings store. Phase 2 uses a fresh client and a fresh collector --
the next run -- to recall it for the same repository@snapshot and revalidate
the quote against freshly collected sources. Phase 3 proves the guard rails:
another repository and another revision recall nothing, and changed evidence
turns a finding `stale`. No model calls; embeddings are local.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from agent.memory import (  # noqa: E402
    format_leads,
    recall_findings,
    revalidate_findings,
    save_findings,
)
from console import make_stdout_safe  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.collect import Collector  # noqa: E402
from models import (  # noqa: E402
    Claim,
    ClaimLabel,
    Coverage,
    Report,
    ReportStatus,
    RepoSnapshot,
    SupportingExcerpt,
)
from retrieval.clients import build_embeddings, open_qdrant  # noqa: E402

REPO = "https://github.com/pallets/flask"
EXPECTED_SHA = "b17bb9ed563ab2857c0db9a07ec4e6407404c7be"
PR = 4682
PR_ID = f"github:pallets/flask:pr:{PR}"
QUOTE = "there's no reason to use a `LocalStack` now"  # verbatim in PR #4682
QUESTION = "Why did Flask replace the LocalStack-based context storage?"


def main() -> None:
    make_stdout_safe()
    gh = get_github()
    repo = get_repository(gh, REPO)
    snapshot = resolve_ref(gh, REPO, "2.2.0")
    assert snapshot.sha == EXPECTED_SHA
    embeddings = build_embeddings()

    # Phase 1 -- a finished report's cited claim becomes a finding.
    collector = Collector(repo, snapshot)
    try:
        collector.add_pull(PR)
        records = dict(collector.sources)
    finally:
        collector.close()
    claim = Claim(
        statement="The PR states there is no reason to use a LocalStack now.",
        label=ClaimLabel.DOCUMENTED,
        excerpts=[SupportingExcerpt(source_id=PR_ID, quote=QUOTE)],
    )
    coverage = Coverage(repository=REPO, snapshot_sha=EXPECTED_SHA, discussions_read=1)
    report = Report(
        question=QUESTION,
        snapshot=snapshot,
        status=ReportStatus.COMPLETE,
        summary="fixture",
        claims=[claim],
        coverage=coverage,
    )
    client = open_qdrant()
    try:
        saved = save_findings(client, embeddings, report, records, thread_id="check-memory")
        assert saved, "no finding was saved"
        print(f"PASS  saved {len(saved)} finding(s) from a cited report")
    finally:
        client.close()

    # Phase 2 -- a later run recalls the finding and revalidates it.
    collector2 = Collector(repo, snapshot)
    try:
        collector2.add_pull(PR)
        records2 = dict(collector2.sources)
    finally:
        collector2.close()
    client2 = open_qdrant()
    try:
        recalled = recall_findings(client2, embeddings, snapshot, QUESTION)
        assert recalled, "the finding was not recalled in a later run"
        results = revalidate_findings(recalled, records2)
        assert any(status == "supported" for _, status in results)
        print(f"PASS  recalled in a later run: {format_leads(results)[0]}")

        # Phase 3a -- another repository cannot inherit it.
        other = RepoSnapshot(
            repository="https://github.com/example/other-repo",
            sha="deadbeef" * 5,
            commit_date=datetime.now(timezone.utc),
        )
        assert recall_findings(client2, embeddings, other, QUESTION) == []
        print("PASS  isolation: another repository recalls nothing")

        # Phase 3b -- another revision of the same repository cannot either.
        revision = snapshot.model_copy(update={"sha": "0" * 40})
        assert recall_findings(client2, embeddings, revision, QUESTION) == []
        print("PASS  isolation: another revision recalls nothing")

        # Phase 3c -- changed evidence makes the finding stale, not trusted.
        changed = records2[PR_ID].model_copy(update={"content": "the text changed"})
        stale = revalidate_findings(recalled, {PR_ID: changed})
        assert any(status.startswith("stale") for _, status in stale)
        print(f"PASS  revalidation marks changed evidence stale: {format_leads(stale)[0]}")
    finally:
        client2.close()

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

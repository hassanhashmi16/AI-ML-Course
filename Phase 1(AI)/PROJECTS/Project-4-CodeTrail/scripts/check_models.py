r"""Check the shared contracts, without any provider calls or network access.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_models.py

Two things are verified:
  1. The manually verified CT-001 demo case (docs/demo-cases.md) fits the
     schemas end to end: request -> snapshot -> source record -> claim ->
     report, plus a fresh investigation state.
  2. The schemas reject shapes that would let a dishonest or ambiguous
     result travel: a documented claim with no excerpt, an unknown claim
     carrying excerpts, a non-GitHub URL, a traversal path, a partial
     report that does not say what limited it, and a misspelled field.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from agent.state import new_state  # noqa: E402
from models import (  # noqa: E402
    Claim,
    ClaimLabel,
    Coverage,
    InvestigationRequest,
    Report,
    ReportStatus,
    RepoSnapshot,
    SourceKind,
    SourceRecord,
    SupportingExcerpt,
    TimelineEvent,
    make_source_id,
)

# The pinned snapshot from docs/demo-cases.md (Flask 2.2.0).
SHA = "b17bb9ed563ab2857c0db9a07ec4e6407404c7be"
REPO = "https://github.com/pallets/flask"


def check_demo_case_fits() -> None:
    """CT-001 as a full pass through the schemas, then a fresh state."""
    request = InvestigationRequest(
        repository=REPO + "/",  # a trailing slash must normalize away
        ref="2.2.0",
        path="src/flask/ctx.py",
        question="Why did Flask replace LocalStack with direct ContextVar handling?",
    )
    assert request.repository == REPO, "repository URL was not normalized"
    assert request.path == "src/flask/ctx.py"

    snapshot = RepoSnapshot(
        repository=REPO,
        ref_requested="2.2.0",
        sha=SHA,
        commit_date=datetime(2022, 8, 2, 0, 12, 9, tzinfo=timezone.utc),
    )

    pr_id = make_source_id(SourceKind.PULL_REQUEST, REPO, SHA, "4682")
    record = SourceRecord(
        source_id=pr_id,
        kind=SourceKind.PULL_REQUEST,
        repository=REPO,
        snapshot_sha=SHA,
        url="https://github.com/pallets/flask/pull/4682",
        title="Use ContextVar directly",
        author="davidism",
        source_date=datetime(2022, 7, 8, tzinfo=timezone.utc),
        content="The previous approach had performance and memory overhead on every push and pop.",
    )

    documented = Claim(
        statement="The refactor removed the list-stack bookkeeping that copied on every push.",
        label=ClaimLabel.DOCUMENTED,
        excerpts=[
            SupportingExcerpt(
                source_id=pr_id,
                quote="performance and memory overhead on every push and pop",
            )
        ],
    )
    unknown = Claim(
        statement="Exact throughput gain and its benchmark setup are not established in the inspected scope.",
        label=ClaimLabel.UNKNOWN,
    )

    Report(
        question=request.question,
        snapshot=snapshot,
        status=ReportStatus.COMPLETE,
        summary="ContextVar tokens replaced the mutable-list stack; no measured throughput figure was found.",
        claims=[documented, unknown],
        timeline=[
            TimelineEvent(
                date=datetime(2022, 7, 8, tzinfo=timezone.utc),
                kind=SourceKind.PULL_REQUEST,
                title="PR #4682 merged",
                source_id=pr_id,
            )
        ],
        unresolved=["No benchmark figure for the refactor was found in the inspected scope."],
        coverage=Coverage(
            repository=REPO,
            snapshot_sha=SHA,
            files_read=1,
            discussions_read=1,
            comments_read=3,
            notes=["Discussion search limited to PR #4682."],
        ),
    )

    state = new_state(request, snapshot)
    state["sources"][pr_id] = record  # how collection will fill it in Step 5

    print("PASS  CT-001 fits the schemas end to end")
    print(f"PASS  unknown stays distinct: documented carries {len(documented.excerpts)} excerpt(s), unknown carries {len(unknown.excerpts)}")
    print(f"PASS  stable ids: {make_source_id(SourceKind.FILE, REPO, SHA, 'src/flask/ctx.py')} | {pr_id}")
    print(f"PASS  state ready: {len(state['sources'])} source(s), counters "
          f"{(state['tool_calls'], state['retrieval_rounds'], state['answer_revisions'])}")


def check_dishonest_shapes_rejected() -> None:
    """Every call below must raise; accepting any of them is the failure."""

    def must_fail(what: str, fn) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - any rejection is a pass here
            print(f"PASS  rejected: {what} -> {type(exc).__name__}")
            return
        raise SystemExit(f"FAIL: accepted '{what}'")

    snapshot = RepoSnapshot(
        repository=REPO,
        sha=SHA,
        commit_date=datetime(2022, 8, 2, tzinfo=timezone.utc),
    )
    pr_id = make_source_id(SourceKind.PULL_REQUEST, REPO, SHA, "4682")

    must_fail(
        "documented claim with no excerpt",
        lambda: Claim(statement="x", label=ClaimLabel.DOCUMENTED),
    )
    must_fail(
        "unknown claim carrying excerpts",
        lambda: Claim(
            statement="x",
            label=ClaimLabel.UNKNOWN,
            excerpts=[SupportingExcerpt(source_id=pr_id, quote="q")],
        ),
    )
    must_fail(
        "non-GitHub repository URL",
        lambda: InvestigationRequest(repository="https://gitlab.com/a/b", question="why"),
    )
    must_fail(
        "path with '..' segments",
        lambda: InvestigationRequest(repository=REPO, question="why", path="../../etc/passwd"),
    )
    must_fail(
        "partial report with no stated limitation",
        lambda: Report(
            question="q",
            snapshot=snapshot,
            status=ReportStatus.PARTIAL,
            summary="s",
            coverage=Coverage(repository=REPO, snapshot_sha=SHA, complete=False),
        ),
    )
    must_fail(
        "misspelled field",
        lambda: Claim(statement="x", label=ClaimLabel.UNKNOWN, label2="y"),
    )


def main() -> None:
    check_demo_case_fits()
    check_dishonest_shapes_rejected()
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

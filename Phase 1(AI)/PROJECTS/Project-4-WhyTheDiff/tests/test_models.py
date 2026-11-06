"""Contract tests: the label rules that keep reports honest."""

from datetime import datetime, timezone

import pytest

from models import (
    Claim,
    ClaimLabel,
    Coverage,
    Report,
    ReportStatus,
    RepoSnapshot,
    SupportingExcerpt,
)


def _snapshot() -> RepoSnapshot:
    return RepoSnapshot(
        repository="https://github.com/a/b",
        sha="a" * 40,
        commit_date=datetime.now(timezone.utc),
    )


def test_documented_claim_requires_an_excerpt():
    with pytest.raises(ValueError):
        Claim(statement="x", label=ClaimLabel.DOCUMENTED)


def test_inferred_claim_requires_an_excerpt():
    with pytest.raises(ValueError):
        Claim(statement="x", label=ClaimLabel.INFERRED)


def test_unknown_claim_cannot_carry_excerpts():
    with pytest.raises(ValueError):
        Claim(
            statement="x",
            label=ClaimLabel.UNKNOWN,
            excerpts=[SupportingExcerpt(source_id="source", quote="q")],
        )


def test_partial_report_must_state_what_limited_it():
    snapshot = _snapshot()
    coverage = Coverage(repository=snapshot.repository, snapshot_sha=snapshot.sha)
    with pytest.raises(ValueError):
        Report(
            question="q",
            snapshot=snapshot,
            status=ReportStatus.PARTIAL,
            summary="s",
            coverage=coverage,
        )


def test_complete_report_requires_a_claim():
    snapshot = _snapshot()
    coverage = Coverage(repository=snapshot.repository, snapshot_sha=snapshot.sha)
    with pytest.raises(ValueError):
        Report(
            question="q",
            snapshot=snapshot,
            status=ReportStatus.COMPLETE,
            summary="s",
            coverage=coverage,
        )

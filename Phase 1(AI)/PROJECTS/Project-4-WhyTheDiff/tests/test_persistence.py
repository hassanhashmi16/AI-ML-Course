"""Persistence tests: thread handles and missing-checkpoint recovery."""

import uuid
from datetime import datetime, timezone

from agent.persistence import new_thread_id, open_checkpointer, saved_state
from models import RepoSnapshot


def _snapshot() -> RepoSnapshot:
    return RepoSnapshot(
        repository="https://github.com/pallets/flask",
        sha="b17bb9ed563ab2857c0db9a07ec4e6407404c7be",
        commit_date=datetime.now(timezone.utc),
    )


def test_thread_id_carries_repository_and_snapshot():
    thread = new_thread_id(_snapshot())
    assert "pallets-flask" in thread
    assert _snapshot().sha[:12] in thread


def test_unknown_thread_has_no_saved_state():
    with open_checkpointer() as saver:
        assert saved_state(saver, f"missing-{uuid.uuid4().hex[:8]}") is None

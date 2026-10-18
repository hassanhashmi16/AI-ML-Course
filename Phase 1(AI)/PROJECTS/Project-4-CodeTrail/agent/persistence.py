"""Checkpointing: durable investigation state via LangGraph's SQLite saver.

An investigation is checkpointed after every graph step, so an interrupted run
resumes from its last durable state instead of starting over. The saver owns
execution state; source IDs and idempotent application writes keep a replay
from duplicating evidence.

Thread IDs are application-generated and printed by the CLI -- that is the
handle a user keeps to resume a run later.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from config import settings
from models import (
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
    repo_slug,
)

# Types that may appear in checkpointed state. Registering them explicitly
# keeps deserialization warning-free and survives LangGraph's stricter
# msgpack policy.
_ALLOWED_MSGPACK_TYPES = {
    (model.__module__, model.__name__)
    for model in (
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
    )
}


def checkpoints_path() -> Path:
    """Where investigations are checkpointed (under the ignored data/ dir)."""
    return settings.data_dir / "checkpoints.sqlite"


@contextmanager
def open_checkpointer(path: Path | None = None):
    """Open the SQLite saver with a connection whose lifetime we control."""
    db_path = Path(path) if path is not None else checkpoints_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), check_same_thread=False)
    serde = JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED_MSGPACK_TYPES)
    try:
        yield SqliteSaver(connection, serde=serde)
    finally:
        connection.close()


def new_thread_id(snapshot: RepoSnapshot) -> str:
    """A readable, unique investigation handle: repo@sha-prefix + random suffix."""
    slug = repo_slug(snapshot.repository).replace("/", "-")
    return f"{slug}@{snapshot.sha[:12]}-{uuid4().hex[:10]}"


def saved_state(saver, thread_id: str) -> dict | None:
    """The last checkpointed channel values for a thread, or None."""
    checkpoint = saver.get_tuple({"configurable": {"thread_id": thread_id}})
    if checkpoint is None:
        return None
    return checkpoint.checkpoint.get("channel_values", {})

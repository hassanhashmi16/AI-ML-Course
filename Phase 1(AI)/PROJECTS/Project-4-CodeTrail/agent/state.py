"""The investigation's working memory, typed for LangGraph.

The graph (Step 11) passes one ``InvestigationState`` between nodes.
Everything an investigation accumulates lives here: what was requested,
which snapshot it is about, every collected source, retrieved IDs for the
current step, working notes, provisional claims, the timeline being built,
failed lookups, and the budget counters that keep the run bounded.

Collections that several nodes may write carry a **reducer** annotation, so
LangGraph merges writes instead of letting the last one overwrite: a fan-out
of tool calls *adds* sources and notes. The ``sources`` dict is keyed by the
stable ``source_id`` from ``models.make_source_id`` -- so a repeated fetch
replaces its own record instead of duplicating evidence (idempotent replay).
"""

from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from models import (
    Claim,
    InvestigationRequest,
    RepoSnapshot,
    Report,
    SourceRecord,
    TimelineEvent,
)


def _merge_sources(
    left: dict[str, SourceRecord],
    right: dict[str, SourceRecord],
) -> dict[str, SourceRecord]:
    """Reducer: merge by ID, later writes replacing the same stable key."""
    return {**left, **right}


class InvestigationState(TypedDict):
    """One investigation's full working state, from request to report."""

    # What we are investigating, and the pinned moment it is about.
    request: InvestigationRequest
    snapshot: RepoSnapshot

    # The investigator's conversation: model decisions and tool results.
    # add_messages merges by message ID, so replay never duplicates turns.
    messages: Annotated[list[AnyMessage], add_messages]

    # Collected evidence by stable ID; `retrieved` holds the IDs selected for
    # the current step (overwritten each retrieval round, not accumulated).
    sources: Annotated[dict[str, SourceRecord], _merge_sources]
    retrieved: list[str]

    # Working material that accumulates across steps.
    notes: Annotated[list[str], add]          # leads, observations, open questions
    claims: Annotated[list[Claim], add]       # provisional claims before the report
    timeline: Annotated[list[TimelineEvent], add]
    failures: Annotated[list[str], add]       # failed lookups stay visible, not silent

    # Budget counters; the configured maxima live in config.settings
    # (max_tool_calls, max_retrieval_rounds, max_answer_revisions, ...).
    tool_calls: int
    retrieval_rounds: int
    answer_revisions: int

    # Control fields written by the grade node and read by graph edges.
    evidence_sufficient: bool | None
    investigation_rounds: int

    # The finished artifact, set by finalization; None while running.
    report: Report | None


def new_state(request: InvestigationRequest, snapshot: RepoSnapshot) -> InvestigationState:
    """A fresh state: empty collections, zeroed budget counters, no report."""
    return InvestigationState(
        request=request,
        snapshot=snapshot,
        messages=[],
        sources={},
        retrieved=[],
        notes=[],
        claims=[],
        timeline=[],
        failures=[],
        tool_calls=0,
        retrieval_rounds=0,
        answer_revisions=0,
        evidence_sufficient=None,
        investigation_rounds=0,
        report=None,
    )

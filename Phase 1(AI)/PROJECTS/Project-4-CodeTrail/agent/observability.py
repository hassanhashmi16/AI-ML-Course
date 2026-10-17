"""Local stage logs plus optional LangSmith tracing.

Two layers, one rule -- a run must behave identically with or without a
tracing account:

  * **always on** -- a structured JSONL log per investigation under
    ``data/traces/``. One line per public event (``api/events``), so a run can
    be inspected after the fact without any cloud service.
  * **opt-in** -- LangSmith, only when ``LANGSMITH_TRACING=true`` and a key is
    configured. Inputs and outputs are hidden on purpose: the trace records
    structure and timing, not prompt or completion content.

Graph events are projected into the small public event format here; hidden
model reasoning never leaves the node.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from langchain_core.messages import ToolMessage

from api.events import EventKind, ProgressEvent
from config import settings

# Node name -> public stage name. Kept explicit so the contract does not
# change silently when the graph is refactored.
NODE_STAGES = {
    "investigate": "model",
    "tools": "tools",
    "grade": "grading",
    "synthesize": "synthesis",
}


def configure_tracing() -> str:
    """Enable LangSmith only when explicitly configured; return a status note."""
    if not settings.langsmith_tracing:
        return "tracing off (LANGSMITH_TRACING=false)"
    key = settings.langsmith_api_key.get_secret_value()
    if not key:
        return "tracing requested but LANGSMITH_API_KEY is empty; tracing stays off"
    # Deliberate capture policy: structure and timing, never prompt content.
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_API_KEY", key)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    os.environ.setdefault("LANGSMITH_HIDE_INPUTS", "true")
    os.environ.setdefault("LANGSMITH_HIDE_OUTPUTS", "true")
    return f"tracing on -> project {settings.langsmith_project} (inputs/outputs hidden)"


class StageLog:
    """Append-only JSONL log for one investigation."""

    def __init__(self, thread_id: str | None = None) -> None:
        name = thread_id or f"run-{uuid.uuid4().hex[:10]}"
        self.path: Path = settings.data_dir / "traces" / f"{name}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: ProgressEvent) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")


def _stage_event(
    node: str, update: dict, duration_ms: int, thread_id: str | None
) -> ProgressEvent:
    """Project one node's update into a public event (counts and names only)."""
    stage = NODE_STAGES.get(node, node)
    data: dict[str, str | int | bool] = {}
    message = f"{node} finished"

    if node == "tools":
        tools = [
            message_.name
            for message_ in update.get("messages", [])
            if isinstance(message_, ToolMessage) and message_.name
        ]
        if tools:
            data["tools"] = ", ".join(tools)
            data["tool_calls"] = len(tools)
            message = "tool call(s): " + ", ".join(tools)
    elif node == "investigate":
        replies = [m for m in update.get("messages", []) if getattr(m, "tool_calls", None)]
        if replies:
            names = [call["name"] for call in replies[-1].tool_calls]
            data["requested_tools"] = ", ".join(names)
            data["tool_calls"] = len(names)
            message = "model requested " + ", ".join(names)
    elif node == "grade":
        notes = [
            note
            for note in update.get("notes", [])
            if note.startswith(("evidence grade", "stopping early", "evidence grading failed"))
        ]
        if notes:
            message = notes[-1][:180]
            data["grade"] = notes[-1][:120]
        data["sufficient"] = bool(update.get("evidence_sufficient"))
    elif node == "synthesize":
        report = update.get("report")
        if report is not None:
            data["claims"] = len(report.claims)
            data["status"] = report.status.value
            message = f"report synthesized: {report.status.value}, {len(report.claims)} claim(s)"

    return ProgressEvent(
        kind=EventKind.STAGE_FINISHED,
        stage=stage,
        message=message[:200],
        thread_id=thread_id,
        duration_ms=duration_ms,
        data=data,
    )


def run_with_events(graph, payload, config, *, thread_id: str | None = None):
    """Stream the graph, emit public events, and return (events, state, log path).

    Uses LangGraph's multi-mode streaming: per-node updates for the event
    trail, plus full state snapshots to return the final state.
    """
    thread = thread_id or (config or {}).get("configurable", {}).get("thread_id")
    log = StageLog(thread)
    events: list[ProgressEvent] = []

    def emit(event: ProgressEvent) -> None:
        events.append(event)
        log.write(event)

    emit(
        ProgressEvent(
            kind=EventKind.RUN_STARTED,
            stage="run",
            message="investigation started",
            thread_id=thread,
        )
    )

    started = time.perf_counter()
    previous = started
    final_state: dict = {}
    for mode, chunk in graph.stream(payload, config, stream_mode=["updates", "values"]):
        now = time.perf_counter()
        if mode == "values":
            final_state = chunk
            continue
        for node, update in chunk.items():
            emit(_stage_event(node, update or {}, int((now - previous) * 1000), thread))
        previous = now

    report = final_state.get("report")
    status = report.status.value if report is not None else "no_report"
    notes = [
        note
        for note in final_state.get("notes", [])
        if note.startswith(("evidence grade", "stopping early"))
    ]
    emit(
        ProgressEvent(
            kind=EventKind.RUN_FINISHED,
            stage="run",
            message=f"investigation finished: {status}",
            thread_id=thread,
            duration_ms=int((time.perf_counter() - started) * 1000),
            data={
                "status": status,
                "tool_calls": final_state.get("tool_calls", 0),
                "rounds": final_state.get("investigation_rounds", 0),
                "last_grade": (notes[-1][:120] if notes else ""),
            },
        )
    )
    return events, final_state, log.path

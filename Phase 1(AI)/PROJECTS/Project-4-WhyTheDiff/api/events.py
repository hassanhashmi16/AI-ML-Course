"""Public progress events: the small, stable contract the API and UI consume.

Deliberately no hidden model reasoning. An event carries a stage name, a short
human-readable message, a duration, and scalar data (counts, tool names,
statuses) -- never prompts, raw completions, or chain-of-thought.

Historical timeline events live in the report; these events describe the
agent's *execution* progress. Keeping them separate stops the UI from
confusing "what the code's history says" with "what the agent is doing now".
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import AwareDatetime, Field

from models import Contract


class EventKind(StrEnum):
    RUN_STARTED = "run_started"
    STAGE_FINISHED = "stage_finished"
    RUN_FINISHED = "run_finished"


class ProgressEvent(Contract):
    """One inspectable step of an investigation, safe to show to a user."""

    kind: EventKind
    stage: str  # run | model | tools | grading | synthesis
    message: str = Field(max_length=200)
    thread_id: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    data: dict[str, str | int | bool] = Field(default_factory=dict)
    timestamp: AwareDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

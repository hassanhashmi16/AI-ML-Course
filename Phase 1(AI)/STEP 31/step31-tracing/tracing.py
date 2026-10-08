"""Step 31 deliverable: a minimal, dependency-free span emitter.

Everything Step 31 teaches lives in this one file:

  * a **span** is a timed operation with a name, a *kind*, and attributes;
  * spans **nest** (parent -> child) and together form a **trace**;
  * the attribute **names** follow the OpenTelemetry GenAI semantic conventions, so
    any backend (Langfuse, Phoenix, Datadog) can read them without a translator.

What this deliberately is NOT: a real OTLP exporter, or a wrapper around an
observability SDK. Emitting OTel-*shaped* JSON to a file keeps the artifact runnable
with zero infrastructure and makes the span model itself the thing you read. Swapping
the file writer for an OTLP exporter is the follow-on exercise, and the span code
below does not change.

Two rules from the step are enforced here:

  1. **Content is OFF by default.** Structure (ids, counts, timings, model names) is
     always recorded; prompts/completions/retrieved text are not, because they are
     your users' data (PII). `set_capture_content(True)` opts in explicitly.
  2. **Kind matters.** CLIENT means "this step called something outside our process"
     (a model, a database, another server). INTERNAL means "this is our own code".
"""
from __future__ import annotations

import json
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Where traces are written. One file per trace: traces/<trace_id>.jsonl
TRACE_DIR = Path(__file__).parent / "traces"

# --- process-local trace state -------------------------------------------------------
# A real implementation threads this through context variables so concurrent requests
# cannot mix traces. A single-threaded CLI is all this needs, so a module dict is fine.
_state: dict = {"trace_id": None, "stack": [], "capture_content": False}


def set_capture_content(on: bool) -> None:
    """Turn recording of prompts/completions on or off. Off by default (31.6)."""
    _state["capture_content"] = on


def _new_id(hex_chars: int) -> str:
    """OTel ids: 32 hex chars for a trace, 16 for a span."""
    return secrets.token_hex(hex_chars // 2)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class Span:
    """One timed operation. `attributes` is where the `gen_ai.*` vocabulary goes."""

    name: str
    kind: str  # "CLIENT" | "INTERNAL"
    attributes: dict = field(default_factory=dict)
    events: list = field(default_factory=list)  # content lives here, and only if opted in
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: str | None = None
    start: float = 0.0
    end: float = 0.0
    status: str = "OK"  # "OK" | "ERROR"

    def set(self, key: str, value) -> "Span":
        """Attach a structural attribute. Returns self so calls can chain."""
        self.attributes[key] = value
        return self

    def record_error(self, exc: Exception) -> None:
        """Mark the span failed. An error is a first-class outcome, not a log line."""
        self.status = "ERROR"
        self.set("error.message", f"{type(exc).__name__}: {exc}")

    def record_content(self, prompt: str | None = None, completion: str | None = None) -> None:
        """Record prompt/completion text - ONLY when capture is explicitly on.

        These go into `events` rather than `attributes` because the convention puts
        bulk content there, and because it keeps the PII clearly separated from the
        structure you always keep.
        """
        if not _state["capture_content"]:
            return
        if prompt is not None:
            self.events.append({"name": "gen_ai.content.prompt", "body": prompt})
        if completion is not None:
            self.events.append({"name": "gen_ai.content.completion", "body": completion})

    def to_json(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind,
            "start": _iso(self.start),
            "end": _iso(self.end),
            "duration_ms": round((self.end - self.start) * 1000, 1),
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
        }


@contextmanager
def span(name: str, kind: str = "INTERNAL", **attrs):
    """Open a span around a block of work.

        with span("generate", kind="CLIENT", **{"gen_ai.request.model": MODEL}) as s:
            answer = call_model(...)
            s.set("gen_ai.usage.input_tokens", 2820)

    The first span opened becomes the root and mints a new trace id; everything
    opened inside it nests automatically, which is what builds the tree.
    """
    parent = _state["stack"][-1] if _state["stack"] else None
    if parent is None:
        _state["trace_id"] = _new_id(32)  # root span starts a new trace

    current = Span(
        name=name,
        kind=kind,
        attributes=dict(attrs),
        trace_id=_state["trace_id"],
        span_id=_new_id(16),
        parent_span_id=parent.span_id if parent else None,
        start=time.time(),
    )
    _state["stack"].append(current)
    try:
        yield current
    except Exception as exc:  # noqa: BLE001 - recorded, then re-raised unchanged
        current.record_error(exc)
        raise
    finally:
        _state["stack"].pop()
        current.end = time.time()
        _emit(current)
        if not _state["stack"]:
            _state["trace_id"] = None  # trace finished; next span starts a fresh one


def _emit(s: Span) -> None:
    """Append one JSON line per span. This is the only I/O in the module."""
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / f"{s.trace_id}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(s.to_json()) + "\n")

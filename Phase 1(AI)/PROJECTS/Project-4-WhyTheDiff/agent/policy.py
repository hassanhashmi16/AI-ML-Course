"""Budgets and stopping rules: an investigation must end predictably.

Every limit comes from ``config.settings`` -- tool calls, sources, tokens, and
wall time -- and repeated identical tool calls count as no progress. The policy
returns a **reason**, so a stopped run can say why it stopped instead of
looking like a finished one (an exhausted budget must produce an honest
partial result, not a silent failure).
"""

from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.messages import AIMessage

from config import settings

# A source budget derived from the per-resource collection limits. One hub
# stop for "the investigation collected far more than the design intends".
SOURCE_BUDGET = (
    settings.max_files
    + settings.max_commits
    + settings.max_discussions
    + settings.max_comments
)


def elapsed_seconds(state) -> float:
    """Wall-clock seconds since the investigation started."""
    started = datetime.fromisoformat(state["started_at"])
    return (datetime.now(timezone.utc) - started).total_seconds()


def budget_stop(state) -> str | None:
    """Return the exhausted budget's reason, or None when there is headroom."""
    if state["tool_calls"] >= settings.max_tool_calls:
        return f"tool budget exhausted ({state['tool_calls']}/{settings.max_tool_calls})"
    if len(state["sources"]) >= SOURCE_BUDGET:
        return f"source budget exhausted ({len(state['sources'])}/{SOURCE_BUDGET})"
    if state["tokens_used"] >= settings.token_budget:
        return f"token budget exhausted ({state['tokens_used']}/{settings.token_budget})"
    if elapsed_seconds(state) >= settings.max_run_seconds:
        return f"time budget exhausted ({settings.max_run_seconds:.0f}s)"
    return None


def _tool_signature(message: AIMessage):
    """A comparable signature for one model turn's tool calls."""
    if not message.tool_calls:
        return None
    return tuple(
        (call["name"], tuple(sorted(call["args"].items()))) for call in message.tool_calls
    )


def repeated_action(state) -> str | None:
    """Detect two consecutive identical tool-call batches (no progress)."""
    signatures = [
        _tool_signature(message)
        for message in state["messages"]
        if isinstance(message, AIMessage)
    ]
    signatures = [signature for signature in signatures if signature]
    if len(signatures) >= 2 and signatures[-1] == signatures[-2]:
        return "repeated action: the last two tool attempts were identical"
    return None


def should_stop(state) -> tuple[bool, str]:
    """True when the investigation must stop; the second value says why."""
    reason = budget_stop(state) or repeated_action(state)
    if reason:
        return True, reason
    return False, ""

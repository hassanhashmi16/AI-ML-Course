"""Policy tests: budgets and repeated actions stop a run with a reason."""

from datetime import datetime, timezone

from langchain_core.messages import AIMessage

from agent.policy import should_stop
from agent.state import new_state
from config import settings
from models import InvestigationRequest, RepoSnapshot


def _state():
    snapshot = RepoSnapshot(
        repository="https://github.com/a/b",
        sha="a" * 40,
        commit_date=datetime.now(timezone.utc),
    )
    return new_state(
        InvestigationRequest(repository="https://github.com/a/b", question="why?"),
        snapshot,
    )


def test_headroom_does_not_stop():
    assert should_stop(_state()) == (False, "")


def test_tool_budget_stops_with_a_reason():
    state = _state()
    state["tool_calls"] = settings.max_tool_calls
    stopped, reason = should_stop(state)
    assert stopped and "tool budget" in reason


def test_repeated_identical_tool_calls_stop():
    state = _state()
    call = {"name": "search_evidence", "args": {"query": "same"}, "id": "call-1"}
    state["messages"] = [
        AIMessage(content="", tool_calls=[call]),
        AIMessage(content="", tool_calls=[call]),
    ]
    stopped, reason = should_stop(state)
    assert stopped and "repeated action" in reason

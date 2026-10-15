"""The stopping rules — when the agent must quit, and why.

Why this is its own module: an agent with no ceiling is a bug that spends money
in a loop. Step 33.6 names the failure modes — infinite loops, tool thrash,
runaway cost — and they all end identically: something outside the model has to
say "stop". This is that something.

The model gets a vote, not a veto. `write_brief` sets `done`, which is the
intended ending, but every rule here can end a run the model would happily keep
going. That asymmetry is deliberate: the model optimizes for finishing the task,
and cheap unbounded effort is not a cost it can feel.

The guards, cheapest first:

- **step budget** — crude, always works, catches anything that loops;
- **token budget** — the one that actually tracks spend;
- **no progress** — catches a spin before the budget has to, which matters
  because budgets are the expensive way to discover a model is stuck.
"""
from __future__ import annotations

import json

from agent.state import AgentState
from config import MAX_STEPS, TOKEN_BUDGET


def should_stop(state: AgentState) -> tuple[bool, str]:
    """Decide whether the run must end. Returns `(stop, reason)`.

    The loop calls this before every model call, not after: a run that is
    already out of budget should not spend one more token finding out.
    """
    if state["done"]:
        return True, "the agent finished"

    if state["step"] >= MAX_STEPS:
        return True, f"step budget reached ({MAX_STEPS})"

    if state["token_usage"] >= TOKEN_BUDGET:
        return True, f"token budget reached ({TOKEN_BUDGET})"

    if _is_spinning(state):
        return True, "no progress: the same tool call repeated twice in a row"

    return False, ""


def _is_spinning(state: AgentState) -> bool:
    """True when the last two tool calls are identical — a stall, not work.

    Same tool *and* same arguments means the second call cannot produce anything
    the first did not: its result is already sitting in the transcript, two
    messages above. The model has lost the thread, and without this rule the
    token budget pays for that discovery.

    Strictly consecutive on purpose. A repeated call with *different* arguments
    is ordinary work (refining a search), and a call repeated later in the run
    may be legitimate (a fact worth re-checking) — flagging either would stop
    healthy runs, which is worse than the loops this catches.
    """
    signatures = [
        json.dumps([message.get("tool_name"), message.get("tool_args") or {}], sort_keys=True)
        for message in state["messages"]
        # Only model turns carry the *request*; tool turns carry the result.
        if message.get("role") == "model" and message.get("tool_name")
    ]
    return len(signatures) >= 2 and signatures[-1] == signatures[-2]

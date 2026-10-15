"""The agent's state — the single object the whole loop reads and writes.

`AgentState` is a TypedDict: a plain dict with type hints, not a class with
methods (Step 34.1's idea, applied by hand instead of through LangGraph). It is
the contract between the loop, the tools, the checkpoint store, and the memory
store, so all four agree on the same shape.

The one rule that matters: **every value must be JSON-serializable.** The
checkpoint (Step 11) snapshots this dict with `json.dumps` after every turn, and
the resume path loads it back. Put an SDK object, a `datetime`, or a tuple in
here and crash-resume breaks silently — so keep it to dicts, lists, strings,
ints, and bools.

Design note: the transcript is stored in a *normalized* form (role + text +
optional tool fields), not as raw Gemini SDK objects. `agent/llm.py` (Step 9)
converts between this shape and the SDK's types. That keeps the state portable
and serializable, and it is the exact seam Project 4 swaps when it moves to
LangGraph.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, TypedDict

# Who produced a message. "model" is the assistant, "tool" is a tool's output
# fed back in. These mirror the roles the model API expects, so the conversion
# in llm.py stays mechanical.
Role = Literal["system", "user", "model", "tool"]

# The run's lifecycle. "running" while the loop is active; the other three are
# terminal outcomes that the CLI (Step 13) reports so you know how a run ended.
Status = Literal["running", "done", "stopped", "error"]


class Message(TypedDict, total=False):
    """One turn in the transcript.

    `total=False` because a message uses only the fields relevant to it: a plain
    user turn has just `role` and `text`, whereas a tool round-trip also sets
    `tool_name` / `tool_args` / `tool_result`.
    """
    role: Role
    text: str          # human-readable text for this turn (may be empty)
    tool_name: str     # set when role == "model" and it requested a tool
    tool_args: dict    # arguments the model passed to that tool
    tool_result: str   # set when role == "tool": what the tool returned
    # Gemini returns an opaque `thought_signature` with every function call and
    # requires it back when the call is replayed in the transcript. Dropping it
    # is a 400 error ("Function call is missing a thought_signature"). Stored
    # base64-encoded because state must stay JSON-serializable — the SDK's type
    # is `bytes`, which json.dumps cannot write.
    thought_signature: str


class Note(TypedDict):
    """A durable fact the agent chose to write down, tied to its source.

    Notes, not the message history, are what the brief is assembled from — and
    what survives a crash. Carrying `source_url` on every note is what makes
    citations nearly free later.
    """
    text: str
    source_url: str
    created_at: str    # ISO 8601 string, not a datetime (see the rule above)


class Source(TypedDict):
    """A page the agent fetched, recorded so the brief can cite it."""
    url: str
    title: str
    retrieved_at: str  # ISO 8601 string


class AgentState(TypedDict):
    """Everything a single run carries. Snapshotted after every turn."""
    topic: str                # what the user asked to research
    session_id: str           # groups runs that share memory (Step 8)
    run_id: str               # unique id for *this* run — the checkpoint key
    plan: str                 # the model's current plan, refined as it goes
    messages: list[Message]   # full transcript, oldest first
    notes: list[Note]         # facts gathered so far (Step 6)
    sources: list[Source]     # pages consulted so far (Step 5)
    step: int                 # count of model<->tool turns so far
    token_usage: int          # running token estimate, checked vs. the budget
    status: Status
    done: bool                # the model declared it finished
    brief_path: str           # where the written brief landed (Step 7)
    # Why the run ended. Set by the loop from policy.should_stop(). A run can
    # stop for reasons the model knows nothing about (budgets, a detected
    # spin), and "why did this stop?" is the first question you ask of a run
    # that did not finish — so it is recorded, checkpointed, and reported.
    stop_reason: str


def now_iso() -> str:
    """The canonical timestamp for this schema: UTC, ISO 8601, seconds precision.

    Every `created_at` / `retrieved_at` in state is produced here. A `datetime`
    object would be the natural Python value, but it is not JSON-serializable —
    and the checkpoint writes the state wholesale with `json.dumps` — so the
    conversion happens at the source, once, instead of at each call site.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_state(topic: str, session_id: str, run_id: str) -> AgentState:
    """Build the initial state for a run. Every field starts empty or zero.

    Having one constructor means the loop, the CLI, and the resume path all
    start from an identical shape — no field is ever forgotten or misspelled in
    one place and not another.
    """
    return AgentState(
        topic=topic,
        session_id=session_id,
        run_id=run_id,
        plan="",
        messages=[],
        notes=[],
        sources=[],
        step=0,
        token_usage=0,
        status="running",
        done=False,
        brief_path="",
        stop_reason="",
    )

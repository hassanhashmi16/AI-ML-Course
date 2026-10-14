"""The ReAct loop — reason, act, observe, repeat.

This is the project. Everything before it was a part; this is the file that
drives them: the model decides what to do, the registry executes it, the result
goes back into the transcript, and the model decides again — until it finishes
or a budget stops it.

The loop is deliberately a plain `while`. No framework, no graph runtime, no
hidden scheduling. Once you have read this file you know exactly what an agent
does on every turn, which is the thing Project 4 replaces with LangGraph — and
the reason you can judge what the framework is actually buying you.

One rule the whole file obeys: **the loop owns all mutation of `state`.** No
other module writes to it (`call_model` reads it, `dispatch` knows nothing about
it). One writer means one place where state can go wrong, and it is here.
"""
from __future__ import annotations

from agent.llm import call_model
from agent.state import AgentState
from config import MAX_STEPS, TOKEN_BUDGET
from memory.store import MemoryStore
from tools.brief import make_brief_tools
from tools.notes import make_note_tools
from tools.registry import dispatch, register

# Importing a stateless tool module *is* how it registers itself (Step 4).
# The `# noqa` markers say "this import is used for its side effect, on purpose"
# — a linter would otherwise call them unused and try to delete the tools.
import tools.fetch_page  # noqa: F401
import tools.web_search  # noqa: F401


def run(state: AgentState, memory: MemoryStore | None = None) -> AgentState:
    """Run the agent until it finishes or a budget stops it.

    Callers do not need to prep the state beyond `new_state(...)`: this function
    registers the run's tools, loads what it already knows, and seeds the first
    message. It returns the same state object it was given, mutated, so callers
    can inspect `brief_path`, `status`, and the transcript afterwards.
    """
    _register_tools(state)

    if not state["messages"]:
        # A fresh run. On a *resumed* run the transcript is already there (that
        # is the whole point of Step 11), so the opening message must not be
        # added twice — otherwise the model would read the topic twice.
        facts = memory.recall(state["session_id"], state["topic"]) if memory else []
        state["messages"].append({"role": "user", "text": _opening_message(state, facts)})

    while not state["done"]:
        # --- budget guards ------------------------------------------------
        # Both of these move into agent/policy.py in Step 12. They live here for
        # now so the loop is safe to run the moment it exists: an agent without
        # a ceiling is an agent that can loop and spend forever.
        if state["step"] >= MAX_STEPS:
            state["status"] = "stopped"
            break
        if state["token_usage"] >= TOKEN_BUDGET:
            state["status"] = "stopped"
            break

        # --- ask the model what to do next ---------------------------------
        reply = call_model(state)

        # Count the spend even on the last turn — the budget must reflect what
        # was actually used, not what was intended.
        state["token_usage"] += reply.get("tokens", 0)

        # The model's narrated reasoning is where its plan lives in practice, so
        # give `state["plan"]` a job: keep the latest thinking as explicit state
        # rather than leaving it to be inferred from the transcript.
        if reply.get("text"):
            state["plan"] = reply["text"]

        tool_name = reply.get("tool_name")
        if not tool_name:
            # The model replied with text and asked for nothing that exists.
            # For now that ends the run as "stopped" (not "done") — the brief
            # was never written. Step 12's policy will handle this better by
            # nudging the model instead of giving up.
            state["messages"].append({"role": "model", "text": reply.get("text", "")})
            state["status"] = "stopped"
            break

        # --- record the request, then execute it ---------------------------
        # Both halves go into the transcript: the model's call and the tool's
        # result. The model has no memory of this turn otherwise (llm.py resends
        # the transcript every call), so anything missing here is invisible to
        # it on the next turn.
        state["messages"].append(
            {
                "role": "model",
                "text": reply.get("text", ""),
                "tool_name": tool_name,
                "tool_args": reply.get("tool_args") or {},
                # Must be kept: Gemini requires this signature back when the call
                # is replayed on the next turn, or it rejects the request (400).
                # See the note on `Message.thought_signature` in state.py.
                "thought_signature": reply.get("thought_signature", ""),
            }
        )

        # `dispatch` never raises: failures come back as an error *string*,
        # which is simply the observation the model reads next.
        result = dispatch(tool_name, reply.get("tool_args") or {})
        state["messages"].append(
            {"role": "tool", "tool_name": tool_name, "tool_result": result}
        )

        state["step"] += 1

    # `write_brief` sets `done`; anything else that broke the loop is a stop.
    if state["done"]:
        state["status"] = "done"

    return state


def _register_tools(state: AgentState) -> None:
    """Wire up the run's tools: import-time ones plus this run's bound ones.

    Stateless tools registered themselves when their modules were imported above.
    The state-touching ones (`save_note`, `read_notes`, `write_brief`) need this
    run's state, so they are built here and registered for the duration of the
    run — the handoff described in `tools/notes.py`.
    """
    for spec in make_note_tools(state) + make_brief_tools(state):
        register(spec)


def _opening_message(state: AgentState, facts: list[dict]) -> str:
    """Build the first user turn: the topic, plus anything already known.

    Memory arrives as ordinary message text, not as part of the system prompt.
    The system prompt defines what the agent *is* and stays fixed; memory is
    per-run context and changes every time, so it belongs with the topic.
    """
    lines = [f"Research topic: {state['topic']}", ""]

    lines.append("What you already know from earlier sessions:")
    if facts:
        for fact in facts:
            lines.append(f"- {fact['content']}")
    else:
        lines.append("- (nothing yet)")

    lines += ["", "Start by planning your approach, then begin searching."]
    return "\n".join(lines)

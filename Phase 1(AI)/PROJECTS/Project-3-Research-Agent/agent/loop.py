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

from typing import Callable

from agent import tracing
from agent.checkpoint import CheckpointStore
from agent.llm import call_model
from agent.policy import should_stop
from agent.state import AgentState
from config import GEN_MODEL
from memory.store import MemoryStore
from tools.brief import make_brief_tools
from tools.notes import make_note_tools
from tools.registry import dispatch, register

# An observer for the run: `hook(event_name, data)`. The loop never prints —
# reporting is a caller's concern — so the CLI (Step 13) and the tracer (Step 16)
# both attach here instead of the loop growing an output concern.
EventHook = Callable[[str, dict], None]

# Importing a stateless tool module *is* how it registers itself (Step 4).
# The `# noqa` markers say "this import is used for its side effect, on purpose"
# — a linter would otherwise call them unused and try to delete the tools.
import tools.fetch_page  # noqa: F401
import tools.web_search  # noqa: F401


def run(
    state: AgentState,
    memory: MemoryStore | None = None,
    checkpoints: CheckpointStore | None = None,
    on_event: EventHook | None = None,
) -> AgentState:
    """Run the agent until it finishes or a budget stops it.

    Callers do not need to prep the state beyond `new_state(...)`: this function
    registers the run's tools, loads what it already knows, and seeds the first
    message. It returns the same state object it was given, mutated, so callers
    can inspect `brief_path`, `status`, and the transcript afterwards.

    Pass `checkpoints` to make the run crash-resumable: the state is snapshotted
    at the start and after every turn. Pass the state from `latest(run_id)` to
    continue a run that died — the transcript is already there, so the opening
    message is not added again.

    Pass `on_event` to watch the run as it happens (the CLI prints a trace with
    it; the tracer in Step 16 will attach the same way).
    """
    _register_tools(state)

    resumed = bool(state["messages"])
    recalled: list[dict] = []

    if not state["messages"]:
        # A fresh run. On a *resumed* run the transcript is already there (that
        # is the whole point of Step 11), so the opening message must not be
        # added twice — otherwise the model would read the topic twice.
        recalled = memory.recall(state["session_id"], state["topic"]) if memory else []
        state["messages"].append({"role": "user", "text": _opening_message(state, recalled)})
        # Snapshot before the first model call, so a crash on turn 1 still leaves
        # a resumable run rather than nothing at all.
        _snapshot(checkpoints, state)

    _emit(
        on_event,
        "start",
        run_id=state["run_id"],
        topic=state["topic"],
        session=state["session_id"],
        resumed=resumed,
        memories=len(recalled),
    )

    while True:
        # --- stopping rules -----------------------------------------------
        # Policy decides, the loop obeys — including the success case. Asking
        # here rather than in the `while` condition means there is exactly one
        # exit path, so no run can ever end without a reason recorded (a
        # `while not state["done"]` loop exits through the condition instead,
        # leaving `stop_reason` empty on every successful run — learned live).
        stop, reason = should_stop(state)
        if stop:
            state["stop_reason"] = reason
            break

        # --- ask the model what to do next ---------------------------------
        # Each model call is a CLIENT span: it leaves this process. The attribute
        # names are OpenTelemetry's GenAI conventions, so any backend can read
        # them without a translator (Step 31.5).
        with tracing.span(
            "call_model", kind="CLIENT", **{"gen_ai.request.model": GEN_MODEL}
        ) as model_span:
            reply = call_model(state)
            model_span.set("gen_ai.usage.input_tokens", reply.get("input_tokens", 0))
            model_span.set("gen_ai.usage.output_tokens", reply.get("output_tokens", 0))
            # Content is recorded only when capture is explicitly enabled: the
            # prompt is the whole transcript, and transcripts hold the user's
            # data (Step 31.6 — off by default).
            model_span.record_content(completion=reply.get("text") or None)

        # Count the spend even on the last turn — the budget must reflect what
        # was actually used, not what was intended.
        state["token_usage"] += reply.get("tokens", 0)

        # The model's narrated reasoning is where its plan lives in practice, so
        # give `state["plan"]` a job: keep the latest thinking as explicit state
        # rather than leaving it to be inferred from the transcript.
        if reply.get("text"):
            state["plan"] = reply["text"]

        turn = state["step"] + 1
        _emit(
            on_event,
            "model",
            turn=turn,
            text=reply.get("text", ""),
            tool_name=reply.get("tool_name", ""),
            tool_args=reply.get("tool_args") or {},
        )

        tool_name = reply.get("tool_name")
        if not tool_name:
            # The model replied with text and requested no tool, so there is
            # nothing to execute and nothing left to drive the loop. `done` is
            # set only by `write_brief`, so a run ending here produced no brief —
            # the reason records that rather than leaving a silent empty result.
            state["messages"].append({"role": "model", "text": reply.get("text", "")})
            state["stop_reason"] = "the model replied without calling a tool"
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
        #
        # The span is named per tool (`tool.web_search`, `tool.fetch_page`) rather
        # than all of them sharing `execute_tool`: the whole value of a waterfall
        # is telling stages apart at a glance, and four bars called `execute_tool`
        # tell you nothing about which one went wrong. Step 31 learned this with
        # `retrieve` vs `rerank`; here the equivalent is the tool name.
        with tracing.span(
            f"tool.{tool_name}", kind="INTERNAL", **{"gen_ai.tool.name": tool_name}
        ) as tool_span:
            result = dispatch(tool_name, reply.get("tool_args") or {})
            tool_span.set("tool.result_chars", len(result))
            if result.startswith("ERROR:"):
                # A tool failure is an outcome, so the span says so — a green span
                # with the error buried in an attribute is how you miss it.
                tool_span.status = "ERROR"
                tool_span.set("error.message", result[:160])

        state["messages"].append(
            {"role": "tool", "tool_name": tool_name, "tool_result": result}
        )

        _emit(on_event, "tool", turn=turn, name=tool_name, result=result)

        state["step"] += 1
        # Snapshot after every completed turn: the most a crash can cost is the
        # turn in flight, never the run.
        _snapshot(checkpoints, state)

    # `done` is set only by `write_brief`, so it means "a brief exists". Anything
    # else that left the loop is a stop, with its reason recorded above.
    state["status"] = "done" if state["done"] else "stopped"

    # One final snapshot. `status` and `stop_reason` are set here — *after* the
    # per-turn writes — so without this the newest row on disk would still say
    # "running" and the stored record could never say how the run ended.
    _snapshot(checkpoints, state)

    _emit(
        on_event,
        "stop",
        status=state["status"],
        reason=state["stop_reason"],
        step=state["step"],
        tokens=state["token_usage"],
        brief_path=state["brief_path"],
        notes=len(state["notes"]),
    )

    return state


def _emit(hook: EventHook | None, event: str, **data) -> None:
    """Send one event to the observer, if anyone is watching.

    Cheap and unconditional at the call sites: a run with no observer behaves
    exactly as it did before the hook existed, so watching never changes what is
    being watched (the observer effect would otherwise be a debugging hazard).
    """
    if hook is not None:
        hook(event, data)


def _snapshot(checkpoints: CheckpointStore | None, state: AgentState) -> None:
    """Save the state, if checkpointing is enabled for this run.

    Optional by design: a caller (like the quick live test in the README) may not
    want a database at all, and the loop should still run.
    """
    if checkpoints is not None:
        checkpoints.save(state)


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

"""The command line: one command to research a topic, resume it, and watch it work.

This file is the **composition root** — the only place that knows about all four
moving parts at once: memory (what the agent knows), checkpoints (what it was
doing), the loop (how it decides), and the brief (what it produced). Every other
module knows about one or two of them.

Keeping that wiring here is why `agent/` stays testable: nothing inside it
constructs its own database, reads `argv`, or prints. The CLI supplies the
objects and attaches the observer; the loop just runs.

Usage:

    python cli.py --topic "solid-state batteries"
    python cli.py --topic "solid-state recycling" --session batteries
    python cli.py --resume 20261014-2201-a1b2

Exit code is 0 when a brief was written, 1 otherwise — so a shell can tell
"finished" from "ran out of budget" without parsing output.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone

from agent.checkpoint import CheckpointStore
from agent.loop import run
from agent.state import AgentState, new_state
from config import DB_PATH
from console import make_stdout_safe
from memory.store import MemoryStore


def main(argv: list[str] | None = None) -> int:
    # Before anything can print: a stray em dash from a web page should not be
    # able to kill a run that has already spent its tokens (see console.py).
    make_stdout_safe()

    args = _parse_args(argv)

    # Both stores live in the same SQLite file but in different tables; each
    # opens its own connection, which is why they are separate objects.
    memory = MemoryStore(DB_PATH)
    checkpoints = CheckpointStore(DB_PATH)

    try:
        if args.resume:
            state = checkpoints.latest(args.resume)
            if state is None:
                print(f"No checkpoints found for run '{args.resume}'.")
                print("Runs that exist are the ones you started with this tool.")
                return 1
        else:
            # Resuming and starting are the same code path from here on: the only
            # difference is where the state came from.
            state = new_state(args.topic, args.session, _new_run_id())

        result = run(state, memory, checkpoints, on_event=_printer)

        _write_back(memory, result)
        _report(result)

        # A brief is the definition of success, so its absence is a failed exit
        # code even though the agent behaved correctly.
        return 0 if result["status"] == "done" else 1
    finally:
        memory.close()
        checkpoints.close()


def _new_run_id() -> str:
    """A short, readable, unique id: `20261014-2201-a1b2`.

    Sortable by time (so `ls`-style thinking works on a list of runs) and short
    enough to retype when resuming. The random suffix prevents two runs started
    in the same second from colliding.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:4]}"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Research a topic on the web and write a cited briefing.",
    )
    parser.add_argument("--topic", help="what to research (required for a new run)")
    parser.add_argument(
        "--session",
        default="default",
        help="memory bucket shared across runs; runs in one session remember each "
        "other (default: 'default')",
    )
    parser.add_argument(
        "--resume",
        metavar="RUN_ID",
        help="continue a run from its latest checkpoint instead of starting fresh; "
        "the topic and session come from the checkpoint",
    )
    args = parser.parse_args(argv)

    if not args.topic and not args.resume:
        # Fail loudly on an ambiguous invocation rather than guessing a topic.
        parser.error("pass --topic to start a run, or --resume RUN_ID to continue one")
    return args


def _printer(event: str, data: dict) -> None:
    """Print a live trace of the run. This is the loop's `on_event` observer.

    Deliberately terse — one line per thing that happened — because its job is to
    let you watch the agent decide, not to be a report. The final summary is
    `_report`, printed once at the end.
    """
    if event == "start":
        verb = "resuming" if data["resumed"] else "starting"
        print(f"\n{verb} '{data['topic']}'")
        print(f"  run {data['run_id']}  |  session '{data['session']}'")
        if data["memories"]:
            print(f"  recalled {data['memories']} item(s) from earlier runs")
    elif event == "model":
        text = " ".join((data.get("text") or "").split())
        if text:
            print(f"  [{data['turn']}] {_clip(text)}")
        if data.get("tool_name"):
            args = ", ".join(f"{k}={_clip(str(v), 40)}" for k, v in data["tool_args"].items())
            print(f"  [{data['turn']}] -> {data['tool_name']}({args})")
    elif event == "tool":
        print(f"  [{data['turn']}] <- {_clip(' '.join((data.get('result') or '').split()))}")


def _clip(text: str, limit: int = 96) -> str:
    """Collapse whitespace and cap length, so one long page cannot flood the trace.

    Plain ASCII "..." rather than an ellipsis character: the Windows console is
    cp1252 and renders it as a placeholder, which makes the trace look broken.
    """
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _write_back(memory: MemoryStore, state: AgentState) -> None:
    """Store what this run should still know next time.

    Two things, matching the store's two kinds of memory: an **episode** saying
    what happened, and the **facts** the run learned. The episode is what makes
    the next run's opening message able to say "you looked at this before".
    """
    outcome = state["brief_path"] or f"no brief ({state['stop_reason']})"
    memory.log_episode(
        state["session_id"], f"researched '{state['topic']}' -> {outcome}"
    )

    for note in state["notes"]:
        # provenance="tool" because every note traces to a page a tool fetched.
        # The store refuses model-asserted facts, and this is exactly why it can:
        # the write path knows where the evidence came from (Step 8).
        memory.remember(
            state["session_id"],
            _subject(note["text"]),
            note["text"],
            provenance="tool",
        )


def _subject(note_text: str) -> str:
    """Use a note's own opening words as its subject key.

    A real subject ("energy density", "pack cost") needs a model call to extract.
    This is the honest zero-cost version: an identical note found in two runs
    collapses into one row ("Already known"), while different notes coexist. The
    trade-off is that two differently-worded notes about the same thing stay
    separate rows — acceptable here, and the first thing to fix if recall starts
    looking redundant.
    """
    return " ".join(note_text.split())[:80]


def _report(state: AgentState) -> None:
    """One summary at the end, whether the run finished or stopped."""
    print("\n" + "-" * 60)
    print(f"  status   {state['status']}  ({state['stop_reason']})")
    print(f"  turns    {state['step']}   tokens {state['token_usage']:,}   notes {len(state['notes'])}")
    if state["brief_path"]:
        print(f"  brief    {state['brief_path']}")
    else:
        print("  brief    none written")
    print("-" * 60)


if __name__ == "__main__":
    sys.exit(main())

"""Kill a run mid-flight, then bring it back from the checkpoint.

This is the milestone's "resume after a crash", demonstrated rather than
asserted. It works by being **nasty on purpose**: it launches the real CLI as a
child process and terminates that process mid-run, so the agent gets no chance
to catch anything, flush anything, or clean up. Whatever survives is whatever
the checkpoint table already had on disk — which is the honest test.

Two phases, one command:

    python demo/demo_resume.py --topic "solid-state batteries" --crash-after 2

    1. start a run, watch the trace, and kill the process just after the
       requested number of turns have been checkpointed;
    2. reopen the database from *this* process, read the surviving snapshot, and
       relaunch the CLI with `--resume` to finish the job.

Why kill during the *next* turn rather than the one we care about: the trace
line for a tool result is printed just before the snapshot is written, so
killing on that line would race the database write. Waiting for the following
turn's request proves the snapshot for the turn before it has committed — no
sleeps, no flakiness.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

# The demo lives in demo/, but needs the project's own modules (config, console)
# and must launch cli.py from the project root. Put the root on the path first.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import DB_PATH  # noqa: E402  (import after sys.path is fixed)
from console import make_stdout_safe  # noqa: E402

# Matches the loop's own trace lines, e.g. "  [3] -> save_note(...)". Counting
# these is how the demo knows a turn has completed and been checkpointed.
TURN_LINE = re.compile(r"^\s*\[\d+\] -> ")


def main(argv: list[str] | None = None) -> int:
    make_stdout_safe()
    args = _parse_args(argv)

    print("=" * 66)
    print("PHASE 1 - start a run, then kill it mid-flight")
    print("=" * 66)
    killed = _run_and_kill(args.topic, args.session, args.crash_after)

    if not killed:
        print("\nThe run finished before it could be killed.")
        print("Use a smaller --crash-after, or a topic that needs more digging.")
        return 1

    run_id, last_step, notes, messages, tokens = _surviving_run()
    print("\nWhat survived on disk (read from the checkpoints table):")
    print(f"  run id          {run_id}")
    print(f"  last snapshot   step {last_step}")
    print(f"  turns completed {last_step}")
    print(f"  notes saved     {notes}   messages in transcript {messages}")
    print(f"  tokens spent    {tokens:,}")
    print("  (that work is not repeated - phase 2 continues from it)")

    print()
    print("=" * 66)
    print(f"PHASE 2 - resume run {run_id}")
    print("=" * 66)
    return _resume(run_id)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="demo_resume.py",
        description="Demonstrate crash-resume: kill a run, then continue it.",
    )
    parser.add_argument("--topic", required=True, help="what to research")
    parser.add_argument("--session", default="resume-demo", help="memory bucket for the demo")
    parser.add_argument(
        "--crash-after",
        type=int,
        default=2,
        metavar="N",
        help="kill the process during turn N+1, leaving N turns checkpointed (default: 2)",
    )
    return parser.parse_args(argv)


def _run_and_kill(topic: str, session: str, crash_after: int) -> bool:
    """Launch cli.py, stream its output, and terminate it mid-run.

    Returns True if the kill actually happened.
    """
    process = subprocess.Popen(
        [sys.executable, "-u", "cli.py", "--topic", topic, "--session", session],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        # The child prints UTF-8 (we tell it to); the demo reads it as such
        # rather than guessing the console code page.
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    turns_started = 0
    for line in process.stdout:            # type: ignore[union-attr]
        sys.stdout.write(line)
        if TURN_LINE.match(line):
            turns_started += 1
            if turns_started > crash_after:
                # Everything up to this point is already committed to SQLite.
                process.kill()
                print(f"\n>>> KILLED the process mid-run (turn {turns_started} was in flight)")
                process.wait()
                return True

    process.wait()
    return False


def _surviving_run() -> tuple[str, int, int, int, int]:
    """Read the newest run's last snapshot straight out of SQLite.

    Deliberately opens the database itself instead of importing the project's
    store: the point is showing that the state survived **as text on disk**, so
    any process — not just this codebase — can read it back.
    """
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT run_id, state_json FROM checkpoints ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    run_id, state_json = row
    state = json.loads(state_json)
    return run_id, state["step"], len(state["notes"]), len(state["messages"]), state["token_usage"]


def _resume(run_id: str) -> int:
    """Relaunch the CLI against the checkpoint and let it finish."""
    process = subprocess.run(
        [sys.executable, "-u", "cli.py", "--resume", run_id],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if process.returncode == 0:
        print("\n>>> the resumed run finished and wrote its brief.")
    else:
        print(f"\n>>> the resumed run ended without a brief (exit {process.returncode}).")
    return process.returncode


if __name__ == "__main__":
    sys.exit(main())

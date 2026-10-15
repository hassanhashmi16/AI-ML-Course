"""Two runs, one session: the second starts already knowing what the first learned.

The checkpoint demo (demo_resume.py) proves a run survives a crash. This one
proves the other half of the milestone: knowledge survives the *run*. They are
different mechanisms — a checkpoint is one run's state kept alive, memory is what
the agent carries forward — and conflating them is the classic mistake.

Two real CLI runs, same `--session`, different topics:

    python demo/demo_memory.py

    1. run 1 researches a topic. Its notes are written to memory when it ends.
    2. run 2 researches a *related* topic. The opening message it receives now
       contains run 1's facts — printed here straight out of the checkpoint, so
       you can read exactly what the second agent was told.

Between them the demo reads the `memories` table with plain `sqlite3`, because
the point is that this knowledge is rows on disk, not anything in a process.

Costs two full agent runs (tens of thousands of tokens). Nothing here is
destructive; re-running simply accumulates more memory in the session.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

# Lives in demo/, needs config + console from the project root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import DB_PATH  # noqa: E402
from console import make_stdout_safe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    make_stdout_safe()
    args = _parse_args(argv)

    _banner(f"PHASE 1 - run 1: '{args.topic_a}'  (session '{args.session}')")
    _run_cli("--topic", args.topic_a, "--session", args.session)

    rows = _memories(args.session)
    print(f"\nMemories stored for session '{args.session}' (read from SQLite):")
    if not rows:
        print("  none - run 1 produced no notes, so there was nothing to remember.")
        return 1
    for index, (kind, content) in enumerate(rows, start=1):
        print(f"  {index}. [{kind}] {_clip(content)}")

    _banner(f"PHASE 2 - run 2: '{args.topic_b}'  (same session)")
    print("(watch for the 'recalled ... item(s) from earlier runs' line below)\n")
    _run_cli("--topic", args.topic_b, "--session", args.session)

    print("\nWhat run 2 was told at the start - its opening message, verbatim,")
    print("read back from its checkpoint on disk:")
    for line in _latest_opening_message().splitlines():
        print(f"    {line}")

    other = _memories("some-other-session")
    print(f"\nIsolation check: session 'some-other-session' holds {len(other)} memories,")
    print("so memory is per-session, not a global pool.")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="demo_memory.py",
        description="Show memory surviving between two runs in one session.",
    )
    parser.add_argument(
        "--topic-a",
        default="solid-state batteries",
        help="what run 1 researches",
    )
    parser.add_argument(
        "--topic-b",
        default="solid-state battery manufacturing challenges",
        help="what run 2 researches; keep it related, or recall has nothing to match on",
    )
    parser.add_argument("--session", default="memory-demo", help="the memory bucket both runs share")
    return parser.parse_args(argv)


def _banner(title: str) -> None:
    print()
    print("=" * 66)
    print(title)
    print("=" * 66)


def _run_cli(*cli_args: str) -> int:
    """Run the real CLI. Output is not captured: it goes straight to the console.

    Unlike demo_resume.py there is nothing to interrupt here, so this needs no
    streaming loop and no process handle — just run it and wait.
    """
    result = subprocess.run(
        [sys.executable, "-u", "cli.py", *cli_args],
        cwd=ROOT,
    )
    return result.returncode


def _memories(session_id: str) -> list[tuple[str, str]]:
    """Live (non-superseded) memories for a session, oldest first.

    Plain sqlite3 rather than `MemoryStore`: the claim being demonstrated is that
    the knowledge is rows on disk, so reading it the boring way is the honest
    way to show it.
    """
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        """
        SELECT kind, content FROM memories
        WHERE session_id = ? AND superseded_by IS NULL
        ORDER BY id
        """,
        (session_id,),
    ).fetchall()
    conn.close()
    return [(row[0], row[1]) for row in rows]


def _latest_opening_message() -> str:
    """The first message of the most recent run, from its checkpoint.

    This is the strongest evidence the demo can offer: not "memory exists", but
    the exact text the second agent was handed, including the facts.
    """
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT state_json FROM checkpoints ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    state = json.loads(row[0])
    return state["messages"][0].get("text", "(no opening message recorded)")


def _clip(text: str, limit: int = 92) -> str:
    """Collapse whitespace and cap length. ASCII-only, for the cp1252 console."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


if __name__ == "__main__":
    sys.exit(main())

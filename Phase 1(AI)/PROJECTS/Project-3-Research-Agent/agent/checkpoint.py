"""Crash-resume: the run's state, surviving the process that made it.

While a run is in flight the state lives in RAM. Kill the process mid-run and all
of it goes: tokens already paid for, pages already read, notes already taken.
This module is what lets the run pick up where it stopped instead of starting
over — the milestone's "can resume after a crash".

The loop calls `save()` after every turn. A new process then calls
`latest(run_id)` and hands the result straight back to `run()`, which continues
from the transcript it finds.

Design: **append-only snapshots**, one row per turn, holding the whole state as
JSON. Append-only rather than one overwritten row, because:

- a torn or corrupt write can never destroy the last good state — `latest()`
  reads the newest row, and older ones are still there to fall back on;
- the rows are the run's history, which is what makes "replay from step N"
  possible without redesigning anything.

This is deliberately the same shape as LangGraph's checkpointer (Step 34.5): one
row per superstep, keyed by thread id, replayed to resume. Building it by hand
here is what makes it obvious what the framework does for you in Project 4.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from agent.state import AgentState, now_iso
from config import DB_PATH


class CheckpointStore:
    """Snapshots of run state, keyed by `run_id`.

    Lives in the same SQLite file as memory (`data/agent.db`) but in its own
    table: both are runtime state, but they have different shapes and very
    different lifetimes — memory outlives every run, checkpoints belong to one.
    """

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id     TEXT NOT NULL,
                step       INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            -- `latest()` always asks for one run's newest row; this index is
            -- exactly that lookup.
            CREATE INDEX IF NOT EXISTS idx_checkpoints_run
                ON checkpoints(run_id, step);
            """
        )
        self.conn.commit()

    def save(self, state: AgentState) -> None:
        """Snapshot the whole state. Called at run start and after every turn.

        `json.dumps` is the reason state may only contain JSON-safe values (see
        `agent/state.py`): a `datetime`, a tuple, or an SDK object anywhere in the
        dict would raise here — and it would raise mid-run, which is the worst
        possible time to discover it.
        """
        self.conn.execute(
            "INSERT INTO checkpoints (run_id, step, state_json, created_at) VALUES (?, ?, ?, ?)",
            (
                state["run_id"],
                state["step"],
                json.dumps(state, ensure_ascii=False),
                now_iso(),
            ),
        )
        self.conn.commit()

    def latest(self, run_id: str) -> AgentState | None:
        """The newest snapshot for a run, or None if the run is unknown.

        `ORDER BY step DESC, id DESC`: `step` is the logical position in the run,
        and `id` breaks ties when two snapshots share a step (the start-of-run
        snapshot and the one after turn 0 both sit at step 0).
        """
        row = self.conn.execute(
            """
            SELECT state_json FROM checkpoints
            WHERE run_id = ?
            ORDER BY step DESC, id DESC
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()

        if row is None:
            return None
        return json.loads(row["state_json"])

    def close(self) -> None:
        self.conn.close()

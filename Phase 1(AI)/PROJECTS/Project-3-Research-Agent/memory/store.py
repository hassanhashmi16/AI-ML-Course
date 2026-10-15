"""The memory store itself — schema, writes, and the recall policy.

The schema carries the three things Step 35 identified as the real content of a
memory system:

- **`provenance`** — where a fact came from. A claim the model invented and a
  claim that came back from a tool are not the same kind of thing, and a store
  that cannot tell them apart cannot defend itself.
- **`superseded_by`** — a pointer from an outdated fact to the one that replaced
  it. Corrections overwrite; they never accumulate as contradictions.
- **`created_at`** — time, so recall can prefer recent facts when relevance ties.

Recall is **keyword + recency**, scored locally in Python. No embeddings, so it
runs with zero API quota and stays inspectable: you can read the rows and see
exactly why something was remembered. Embedding-based recall is the upgrade path
once the store outgrows a few hundred facts.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from agent.state import now_iso
from config import DB_PATH, MEMORY_TOP_K

# Words too common to carry signal. Without this, "the battery" and "a battery"
# would score identically to "battery energy density", which is noise.
_STOPWORDS = {
    "the", "and", "for", "was", "were", "are", "with", "that", "this", "from",
    "what", "when", "which", "into", "about", "have", "has", "had", "its", "not",
}

# Provenances allowed to write a *semantic* fact. "model" is deliberately absent:
# a fact the model asserted with no tool evidence behind it is exactly how
# memory gets poisoned, so it is rejected at the door rather than stored and
# distrusted later (Step 35's write-policy lesson).
_TRUSTED_PROVENANCE = {"user", "tool"}


def _terms(text: str) -> set[str]:
    """Split text into comparable terms: lowercase, alphanumeric, no stopwords."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


class MemoryStore:
    """SQLite-backed memory for one or more sessions.

    A `session_id` is the unit of continuity: runs sharing a session share
    memory. Different sessions stay separate, which is what keeps one research
    topic from leaking into another.
    """

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        # The database lives under data/; create the directory on first run so
        # the store works on a fresh clone with no manual setup.
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        # Rows behave like dicts, so callers read row["content"] instead of
        # remembering column positions.
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        """Create the table on first use. `IF NOT EXISTS` makes this idempotent."""
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    TEXT NOT NULL,
                kind          TEXT NOT NULL CHECK (kind IN ('semantic', 'episodic')),
                subject       TEXT NOT NULL,
                content       TEXT NOT NULL,
                provenance    TEXT NOT NULL,
                superseded_by INTEGER REFERENCES memories(id),
                created_at    TEXT NOT NULL
            );

            -- Recall always filters by session and non-superseded rows, so this
            -- is the index that pays for itself.
            CREATE INDEX IF NOT EXISTS idx_memories_session
                ON memories(session_id, kind);
            """
        )
        self.conn.commit()

    def remember(
        self,
        session_id: str,
        subject: str,
        content: str,
        provenance: str = "tool",
    ) -> str:
        """Write a semantic fact, upserting on `(session_id, subject)`.

        Returns a short description of what happened. Three cases:

        - no existing fact on this subject -> insert;
        - identical content -> no-op (idempotent, so re-running a job is safe);
        - different content -> insert the new row and point the old one at it.
        """
        if not subject.strip() or not content.strip():
            raise ValueError("a memory needs both a subject and content")
        if provenance not in _TRUSTED_PROVENANCE:
            raise ValueError(
                f"provenance {provenance!r} may not write semantic memory "
                f"(allowed: {sorted(_TRUSTED_PROVENANCE)})"
            )

        existing = self.conn.execute(
            """
            SELECT id, content FROM memories
            WHERE session_id = ? AND kind = 'semantic' AND subject = ?
              AND superseded_by IS NULL
            """,
            (session_id, subject),
        ).fetchone()

        if existing is not None and existing["content"] == content:
            return "Already known."

        cursor = self.conn.execute(
            """
            INSERT INTO memories (session_id, kind, subject, content, provenance, created_at)
            VALUES (?, 'semantic', ?, ?, ?, ?)
            """,
            (session_id, subject, content, provenance, now_iso()),
        )

        if existing is not None:
            # The correction path: the old row stays for audit, but is marked as
            # replaced so recall never returns two contradictory facts.
            self.conn.execute(
                "UPDATE memories SET superseded_by = ? WHERE id = ?",
                (cursor.lastrowid, existing["id"]),
            )
            self.conn.commit()
            return "Updated: superseded the previous fact."

        self.conn.commit()
        return "Remembered."

    def log_episode(self, session_id: str, content: str, provenance: str = "tool") -> None:
        """Append an episodic entry. Events accumulate; they are never upserted."""
        if provenance not in _TRUSTED_PROVENANCE:
            raise ValueError(f"provenance {provenance!r} may not write episodic memory")
        self.conn.execute(
            """
            INSERT INTO memories (session_id, kind, subject, content, provenance, created_at)
            VALUES (?, 'episodic', '', ?, ?, ?)
            """,
            (session_id, content, provenance, now_iso()),
        )
        self.conn.commit()

    def recall(self, session_id: str, query: str, k: int = MEMORY_TOP_K) -> list[dict]:
        """Return the `k` most relevant live memories for this session.

        Scored by term overlap with `query`, with recency as the tiebreaker.
        Superseded rows are excluded — that is the whole point of keeping the
        pointer: the agent should never be shown a fact it already corrected.
        An empty query returns the most recent memories, which is what a fresh
        run wants when it has no topic-specific terms yet.
        """
        rows = self.conn.execute(
            """
            SELECT id, kind, subject, content, provenance, created_at
            FROM memories
            WHERE session_id = ? AND superseded_by IS NULL
            ORDER BY created_at DESC
            """,
            (session_id,),
        ).fetchall()

        wanted = _terms(query)

        def score(row: sqlite3.Row) -> int:
            return len(wanted & _terms(f"{row['subject']} {row['content']}"))

        # Sort by relevance first, then by the order we already have (newest
        # first) — Python's sort is stable, so recency survives as the tiebreak.
        if wanted:
            ranked = sorted(rows, key=score, reverse=True)
            ranked = [row for row in ranked if score(row) > 0]
        else:
            ranked = list(rows)

        return [dict(row) for row in ranked[:k]]

    def close(self) -> None:
        self.conn.close()

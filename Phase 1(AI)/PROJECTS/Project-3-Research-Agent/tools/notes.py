"""Agent notes — the write-down-early habit that makes briefs possible.

Why notes are a tool instead of just living in the message history: the
transcript is lossy and expensive. It gets trimmed as a run grows, and it charges
rent on every model call. Notes are the durable, cheap-to-read record of what the
agent actually learned — and because each one carries its source URL, citations
in the final brief come almost for free.

Architectural note — these tools differ from `web_search` / `fetch_page`:
those are *stateless* (input -> output), so they register themselves at import
time. These must write into a specific run's state, so they are *bound to a run*:
the loop (Step 10) calls `make_note_tools(state)` once at the start and registers
the returned specs. Same registry, same `fn(**args) -> str` contract — the state
dependency is made explicit by a closure instead of hidden in a global.
"""
from __future__ import annotations

from datetime import datetime, timezone

from agent.state import AgentState
from tools.registry import ToolSpec


def _now() -> str:
    """UTC timestamp as an ISO 8601 string.

    A `datetime` object would be the natural Python choice, but state must stay
    JSON-serializable for the checkpoint (Step 11), so it becomes a string here
    rather than at the serialization boundary.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_note_tools(state: AgentState) -> list[ToolSpec]:
    """Build the note tools bound to one run's state."""

    def save_note(text: str, source_url: str = "") -> str:
        """Append one note to the run's state and confirm it."""
        # Exact-duplicate guard. Models re-save the same fact constantly, and
        # every copy would otherwise ride along in the context window forever.
        for index, note in enumerate(state["notes"], start=1):
            if note["text"] == text and note.get("source_url", "") == source_url:
                return f"Already saved as note {index}. Nothing to do."

        state["notes"].append(
            {"text": text, "source_url": source_url, "created_at": _now()}
        )
        suffix = f" Source: {source_url}" if source_url else ""
        return f"Saved note {len(state['notes'])}.{suffix}"

    def read_notes() -> str:
        """Return every note saved so far, numbered, with sources."""
        if not state["notes"]:
            return "No notes yet."
        lines = []
        for index, note in enumerate(state["notes"], start=1):
            source = f" (source: {note['source_url']})" if note.get("source_url") else ""
            lines.append(f"{index}. {note['text']}{source}")
        return "\n".join(lines)

    return [
        {
            "name": "save_note",
            "description": (
                "Write down one fact or finding you want to appear in the final brief, "
                "together with the URL it came from. Save notes as you go — the "
                "conversation is not a reliable record of what you have read. Keep each "
                "note to a single idea, and always pass the source_url of the page it "
                "came from so it can be cited."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "One fact or finding, in a single sentence or two.",
                    },
                    "source_url": {
                        "type": "string",
                        "description": "The URL of the page this fact came from.",
                    },
                },
                "required": ["text"],
            },
            "fn": save_note,
        },
        {
            "name": "read_notes",
            "description": (
                "List every note saved so far, numbered, with their sources. Use this "
                "before deciding you are done, to check what you have actually collected."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
            "fn": read_notes,
        },
    ]

"""The brief writer — the terminal action that turns notes into a document.

This is the run's finish line. Calling `write_brief` means the agent is done, so
the tool also marks the run finished (`state["done"] = True`) and records where
the file landed (`state["brief_path"]`). That is why it is a *bound* tool like
the note tools: it writes into the run's state, not just to disk.

Design choice worth knowing — the model supplies a Markdown **body** rather than
a nested `sections` structure. Two reasons:

- Writing prose is what the model is best at; a deeply nested JSON argument is
  where constrained output starts to hurt quality (and our minimal validator
  only checks top-level scalars anyway).
- The parts that must be *correct* — the title, the metadata line, the source
  list — are generated here from real state, not by the model. Citations are
  therefore derived from what was actually read, never from what the model
  remembers reading.

The model cites inline as `[text](url)` links; the numbered Sources section is
assembled from the notes' `source_url`s.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from agent.state import AgentState, Note, Source
from config import BASE_DIR, BRIEFS_DIR
from tools.registry import ToolSpec


def _slugify(title: str) -> str:
    """Turn a title into a safe filename: 'Solid-State Batteries' -> 'solid-state-batteries'."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return (slug or "brief")[:60]  # cap length; leaves room for the extension


def _collect_sources(notes: list[Note]) -> list[Source]:
    """Build the de-duplicated source list from the notes, in first-seen order.

    Derived, not declared: a source appears in the brief only if a note actually
    cited it. That is the difference between a real citation list and a list of
    every URL the agent happened to open.
    """
    seen: dict[str, str] = {}
    for note in notes:
        url = note.get("source_url", "")
        # Only the first sighting of a URL is kept, so its `retrieved_at` is
        # when that page was first read.
        if url and url not in seen:
            seen[url] = note["created_at"]
    # `title` is deliberately empty: fetch_page extracts article text but not
    # page titles, so there is no honest value to put here.
    return [
        {"url": url, "title": "", "retrieved_at": retrieved_at}
        for url, retrieved_at in seen.items()
    ]


def _strip_leading_heading(body: str) -> str:
    """Drop a leading `# ...` line from the model's body.

    Found in the first live run: models habitually repeat the title as the body's
    first line, so every brief came out with the H1 twice. The title is owned by
    `_render`; the body is not allowed to declare it again.
    """
    lines = body.strip().splitlines()
    if lines and lines[0].lstrip().startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _render(title: str, body: str, sources: list[Source], state: AgentState) -> str:
    """Assemble the full Markdown document: title, metadata, body, sources."""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# {title}",
        "",
        f"*Research topic: {state['topic']} — generated {generated} (run {state['run_id']})*",
        "",
        _strip_leading_heading(body),
        "",
        "## Sources",
        "",
    ]
    for index, source in enumerate(sources, start=1):
        lines.append(f"{index}. {source['url']} (retrieved {source['retrieved_at']})")
    return "\n".join(lines) + "\n"


def make_brief_tools(state: AgentState) -> list[ToolSpec]:
    """Build the brief-writing tool bound to one run's state."""

    def write_brief(title: str, body: str) -> str:
        """Write the brief to disk, record it in state, and finish the run."""
        # Refuse to write an empty brief. Without this guard a model that
        # misreads its own progress produces a confident document built on
        # nothing — the worst possible output for a research agent.
        if not state["notes"]:
            return (
                "ERROR: no notes saved yet, so there is nothing to write a brief from. "
                "Search, read pages, and save_note what you learn first."
            )

        sources = _collect_sources(state["notes"])
        document = _render(title, body, sources, state)

        BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
        path = BRIEFS_DIR / f"{_slugify(title)}.md"
        path.write_text(document, encoding="utf-8")  # explicit: default encoding varies by OS

        # Record the outcome in state so the checkpoint carries it and the CLI
        # can report it. `done` is what the loop's policy reads to stop cleanly.
        state["sources"] = sources
        state["brief_path"] = str(path)
        state["done"] = True

        relative = path.relative_to(BASE_DIR)
        return (
            f"Brief written to {relative} "
            f"({len(body.split())} words, {len(sources)} sources). Run complete."
        )

    return [
        {
            "name": "write_brief",
            "description": (
                "Write the final briefing document and END the run. Call this exactly once, "
                "when you have saved enough notes to answer the topic. The `title` is the "
                "document's heading; the `body` is the full Markdown text, with sources "
                "cited inline as [text](url) links. The numbered source list is generated "
                "automatically from your saved notes, so every claim you make should be "
                "backed by a note you wrote."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "A short, descriptive title for the brief.",
                    },
                    "body": {
                        "type": "string",
                        "description": (
                            "The full Markdown body: headings and prose, with inline "
                            "[text](url) citations for every factual claim. Do not repeat "
                            "the title as a heading — the document's H1 is added for you."
                        ),
                    },
                },
                "required": ["title", "body"],
            },
            "fn": write_brief,
        }
    ]

"""Step 12 deliverable: answer exact-fact questions from the peaks table.

The lesson of this step is judgment: **RAG is not always the right tool.**

"How tall is K2?" is not a retrieval problem, it is a lookup. The answer is one
number in one row. Sending that through embedding search is slower, costs money,
and can be wrong: an embedding may hand back a passage about *climbing* K2 rather
than its height, because both are about K2.

So we route by question type:

  * Named peak + a known fact (height / country / range / first ascent)
        -> answer from the peaks table with one SQL query.
  * Anything else
        -> return None, and the caller falls back to the RAG pipeline.

Two safety properties, both deliberate:

  1. The routing is plain keyword matching, not an LLM, so it is deterministic and
     free. It is a router, not a parser; if it is unsure it returns None and the
     real pipeline handles the question.
  2. The SQL is a FIXED statement with a bound parameter. We never build SQL from
     the user's text, which is exactly how SQL injection happens.
"""
from __future__ import annotations

import json

from config import PEAKS_JSON
from console import make_stdout_safe
from ingest.store import connect

# Intent -> the phrases that signal it. Checked in order, so "first ascent" wins
# over "height" if a question somehow contains both.
_INTENTS: list[tuple[str, list[str]]] = [
    ("first_ascent", ["first climb", "first ascent", "first summit",
                      "who climb", "first to climb", "first reached"]),
    ("height", ["how tall", "how high", "height", "elevation", "metres", "meters"]),
    ("country", ["which country", "what country", "where is", "located in", "location"]),
    ("range", ["which range", "what range", "mountain range"]),
]


def _load_peaks() -> list[dict]:
    return json.loads(PEAKS_JSON.read_text(encoding="utf-8"))["peaks"]


def _find_peak(question: str, peaks: list[dict]) -> dict | None:
    """Return the peak the question is about, or None.

    Matches names AND aliases (so "Savage Mountain" resolves to K2), and picks the
    LONGEST match so "Annapurna I" is not shadowed by the alias "Annapurna".
    """
    lowered = question.lower()
    best: dict | None = None
    best_len = 0
    for peak in peaks:
        for term in [peak["name"], *peak.get("aliases", [])]:
            if term.lower() in lowered and len(term) > best_len:
                best, best_len = peak, len(term)
    return best


def _find_intent(question: str) -> str | None:
    lowered = question.lower()
    for intent, hints in _INTENTS:
        if any(hint in lowered for hint in hints):
            return intent
    return None


def structured_lookup(question: str, conn=None) -> str | None:
    """Answer an exact-fact question from the table, or None if it is not one.

    Returning None is the important part: it means "this is not my job", and the
    caller hands the question to the RAG pipeline instead.
    """
    peak = _find_peak(question, _load_peaks())
    if peak is None:
        return None
    intent = _find_intent(question)
    if intent is None:
        return None

    owns_connection = conn is None
    if owns_connection:
        conn = connect()
    try:
        with conn.cursor() as cur:
            # A fixed statement with ONE bound parameter. No user text is ever
            # concatenated into this string.
            cur.execute(
                """
                SELECT name, height_m, countries, mountain_range,
                       first_ascent_year, first_ascent_date, first_ascenters
                FROM peaks
                WHERE lower(name) = lower(%s)
                """,
                (peak["name"],),
            )
            row = cur.fetchone()
    finally:
        if owns_connection:
            conn.close()

    if row is None:
        return None

    name, height_m, countries, mountain_range, year, date, climbers = row

    if intent == "height":
        return f"{name} is {int(height_m):,} m high."
    if intent == "country":
        return f"{name} lies in {', '.join(countries)}."
    if intent == "range":
        return f"{name} is in the {mountain_range} range."
    if intent == "first_ascent":
        when = date.strftime("%d %B %Y").lstrip("0")
        return f"{name} was first climbed on {when} by {', '.join(climbers)}."
    return None


def main() -> None:
    """Show which questions the table answers and which fall through to RAG."""
    make_stdout_safe()

    questions = [
        "how tall is K2?",
        "who first climbed Annapurna?",
        "which country is Kangchenjunga in?",
        "how tall is Savage Mountain?",   # alias -> K2, then a height lookup
        "how difficult is K2 compared to Everest?",  # not an exact fact -> RAG
    ]

    for question in questions:
        answer = structured_lookup(question)
        tag = "TABLE" if answer else "RAG  "
        print(f"[{tag}] {question}")
        if answer:
            print(f"         {answer}")


if __name__ == "__main__":
    main()

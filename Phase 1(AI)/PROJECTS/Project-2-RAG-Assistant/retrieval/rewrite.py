"""Step 10 deliverable: rewrite the user's question before searching.

Input:  the raw question, exactly as the user typed it.
Output: a small list of search queries: the original, plus 1-2 rewrites.

Why this step exists: users and documents speak different languages.

  * A user asks "is Savage Mountain harder than Everest?" The corpus never writes
    "Savage Mountain"; it writes "K2". A search for the user's exact words finds
    nothing, no matter how good the retriever is. Rewriting maps the user's
    vocabulary onto the corpus's vocabulary, using the alias list in peaks.json.

  * A vague question ("what's the deadliest one?") is a poor search string but a
    fine *question*. Asking the model for a couple of sharper phrasings gives the
    retrievers more to work with.

This is the "rewrite -> retrieve" half of the production pattern. The retrieve
half (hybrid + rerank) is Step 11.

Design rule that matters more than the cleverness: **a rewrite is an optimisation,
so it must never be able to break a request.** Any failure here falls back to the
original question, and the user still gets an answer.
"""
from __future__ import annotations

import json

from google import genai
from google.genai import types
from pydantic import BaseModel

from config import GEMINI_API_KEY, GEMINI_MODEL, PEAKS_JSON

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env.")

_client = genai.Client(api_key=GEMINI_API_KEY)


class Rewrites(BaseModel):
    """The shape we ask the model to return. Structured output, not free text."""

    queries: list[str]


def _alias_lines() -> str:
    """The alias list, one peak per line, to put inside the prompt."""
    data = json.loads(PEAKS_JSON.read_text(encoding="utf-8"))
    lines = [
        f"{peak['name']}: {', '.join(peak['aliases'])}"
        for peak in data["peaks"]
        if peak["aliases"]
    ]
    return "\n".join(lines)


PROMPT = """You turn a user's question into search queries for a retrieval system
over Wikipedia articles about the 14 eight-thousanders.

Rules:
- Return 2 or 3 short search queries.
- Always include the user's original question as the first query.
- Translate nicknames to the canonical peak name using this list:
{aliases}
- Do not answer the question. Only produce search queries."""


def rewrite_query(question: str) -> list[str]:
    """Return search queries for a question: the original plus 1-2 rewrites.

    Never raises on an API problem. If anything goes wrong, the original question
    is returned unchanged, because a broken rewrite must not break the request.
    """
    try:
        response = _client.models.generate_content(
            model=GEMINI_MODEL,
            contents=PROMPT.format(aliases=_alias_lines()) + f"\n\nQuestion: {question}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Rewrites,
            ),
        )
        parsed = getattr(response, "parsed", None) or Rewrites.model_validate_json(
            response.text
        )
        rewrites = parsed.queries
    except Exception:
        return [question]

    # Keep order, de-duplicate (case-insensitively), and guarantee the original
    # is first so a rewrite can only ever ADD recall, never remove the user's words.
    queries: list[str] = []
    seen: set[str] = set()
    for candidate in [question, *rewrites]:
        candidate = candidate.strip()
        if candidate and candidate.lower() not in seen:
            seen.add(candidate.lower())
            queries.append(candidate)
    return queries


def main() -> None:
    """Show how a few questions get rewritten."""
    from console import make_stdout_safe

    make_stdout_safe()

    questions = [
        "is Savage Mountain harder than Everest?",  # nickname -> K2
        "who first climbed the killer mountain?",   # nickname -> Nanga Parbat
        "what's the deadliest eight-thousander?",    # vague -> sharper queries
    ]

    for question in questions:
        print(f"\nquestion: {question}")
        for i, query in enumerate(rewrite_query(question), start=1):
            print(f"  {i}. {query}")


if __name__ == "__main__":
    main()

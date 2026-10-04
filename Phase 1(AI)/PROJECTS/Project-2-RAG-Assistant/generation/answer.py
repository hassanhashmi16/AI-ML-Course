"""Step 13 deliverable: grounded answers with citations.

Input:  a question.
Output: a written answer PLUS the sources it was built from.

This is the step where the retrieval pipeline finally pays off. Everything up to
here found the right chunks; now the model reads them and writes an answer.

The whole design rests on one idea: **the model must answer from the sources, not
from its memory.** A model that "knows" about K2 will happily answer out of its own
training data, which is exactly what we are trying to avoid: it may be stale,
wrong, or impossible to verify. So the prompt:

  1. hands the model the numbered chunks,
  2. tells it to use ONLY them,
  3. tells it to say so when they do not contain the answer,
  4. asks it to name the chunk numbers it used.

Those numbers are the citations. They are what turn "trust me" into "check source
3 yourself". Asking for them as structured output (a Pydantic schema) means they
are validated data, not prose we have to parse.

Order of operations: exact facts (Step 12) are answered from the table and never
reach the model at all; everything else is retrieved, then generated.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from config import GEMINI_API_KEY, GEMINI_MODEL, RERANK_K
from retrieval.results import Retrieved
from retrieval.search import hybrid_search
from retrieval.structured import structured_lookup

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env.")

_client = genai.Client(api_key=GEMINI_API_KEY)

# 503s come from capacity, not from anything we did, and the fix is to wait briefly
# and ask again. Four attempts with doubling delay rides out a short busy spell.
_MAX_ATTEMPTS = 4


class LLMAnswer(BaseModel):
    """The structured shape we require from the model.

    `citations` are 1-based source numbers (the [1], [2], ... in the prompt).
    `confidence` is asked for, but treat it as decorative: language models are
    poorly calibrated about their own certainty, so never gate behaviour on it.
    """

    answer: str
    citations: list[int]
    confidence: float


@dataclass
class GroundedAnswer:
    """What the rest of the app gets back."""

    answer: str
    sources: list[Retrieved]  # the chunks actually cited (or the top ones)
    used_table: bool          # True if answered from peaks (Step 12), no LLM


PROMPT = """You answer questions about the 14 eight-thousanders using ONLY the
numbered sources below.

Rules:
- Use only the sources. Do not add facts from your own knowledge.
- If the sources do not contain the answer, say so plainly.
- In `citations`, list the numbers of the sources you actually used.

Sources:
{context}"""


def _generate(question: str, sources: list[Retrieved]) -> LLMAnswer:
    """Ask the model, grounded in the numbered sources.

    Retries on a 503. The model, and especially its structured-output path, goes
    through busy periods where it answers "high demand, try again later". Waiting a
    few seconds and asking again is the right response; handing the user an error is
    not. (Only 503 is retried here: a bad key or a malformed request is not going to
    fix itself, so those errors surface immediately.)
    """
    context = "\n\n".join(
        f"[{i}] ({source.label()})\n{source.content}"
        for i, source in enumerate(sources, start=1)
    )
    contents = PROMPT.format(context=context) + f"\n\nQuestion: {question}"
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=LLMAnswer,
        # Deterministic: the same sources should produce the same answer.
        temperature=0,
    )

    delay = 2.0
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = _client.models.generate_content(
                model=GEMINI_MODEL, contents=contents, config=config
            )
            return getattr(response, "parsed", None) or LLMAnswer.model_validate_json(
                response.text
            )
        except errors.ServerError:
            if attempt == _MAX_ATTEMPTS:
                raise
            time.sleep(delay)
            delay *= 2

    raise RuntimeError("unreachable")  # loop either returns or raises


def answer_question(question: str, k: int = RERANK_K) -> GroundedAnswer:
    """Answer a question: exact facts from the table, everything else by RAG."""
    # 1. Exact-fact questions (Step 12) never touch retrieval or the model.
    fact = structured_lookup(question)
    if fact is not None:
        return GroundedAnswer(answer=fact, sources=[], used_table=True)

    # 2. Everything else: retrieve the best chunks, then generate from them.
    sources = hybrid_search(question, k=k)
    if not sources:
        return GroundedAnswer(
            answer="I couldn't find anything relevant in the sources.",
            sources=[],
            used_table=False,
        )

    llm = _generate(question, sources)

    # Map the cited source numbers back to chunks. Ignore any out-of-range number
    # the model invents, and if it cited nothing, fall back to the retrieved set so
    # the user still sees what the answer could have come from.
    cited = [
        sources[number - 1]
        for number in dict.fromkeys(llm.citations)  # de-dupe, keep order
        if 1 <= number <= len(sources)
    ]
    return GroundedAnswer(answer=llm.answer, sources=cited or sources, used_table=False)


STREAM_PROMPT = """You answer questions about the 14 eight-thousanders using ONLY
the numbered sources below. Write a short, direct answer. Use only the sources; if
they do not contain the answer, say so plainly.

Sources:
{context}"""


def stream_answer(question: str, k: int = RERANK_K):
    """Yield the answer incrementally, for the streaming API endpoint.

    Yields ("sources", list[Retrieved]) once, then ("token", str) repeatedly.

    The streaming path cannot use a JSON schema (you cannot cleanly stream a JSON
    object at someone watching words appear), so it produces plain text and reports
    ALL retrieved sources rather than just the cited ones. The blocking /ask
    endpoint keeps the stricter, cited version. That is a real trade-off between the
    two endpoints, not an oversight.
    """
    fact = structured_lookup(question)
    if fact is not None:
        yield "sources", []
        yield "token", fact
        return

    sources = hybrid_search(question, k=k)
    yield "sources", sources
    if not sources:
        yield "token", "I couldn't find anything relevant in the sources."
        return

    context = "\n\n".join(
        f"[{i}] ({source.label()})\n{source.content}"
        for i, source in enumerate(sources, start=1)
    )
    contents = STREAM_PROMPT.format(context=context) + f"\n\nQuestion: {question}"
    for event in _client.models.generate_content_stream(
        model=GEMINI_MODEL, contents=contents
    ):
        text = getattr(event, "text", None)
        if text:
            yield "token", text


def main() -> None:
    """Ask a few questions and print the grounded answers with their sources."""
    from console import make_stdout_safe

    make_stdout_safe()

    questions = [
        "how tall is K2?",                              # table lookup
        "which eight-thousander is the deadliest?",     # grounded answer + citations
        "who made the first ascent of K2 and when?",
    ]

    for question in questions:
        result = answer_question(question)
        print(f"\nQ: {question}")
        print(f"A: {result.answer}")
        if result.used_table:
            print("   (answered from the peaks table, no retrieval)")
        else:
            print("   sources:")
            for source in result.sources:
                print(f"     - {source.label()}")


if __name__ == "__main__":
    main()

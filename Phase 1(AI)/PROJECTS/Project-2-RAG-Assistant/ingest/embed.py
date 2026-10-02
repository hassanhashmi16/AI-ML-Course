"""Step 6 deliverable: turn chunk text into embedding vectors.

Input:  a list of strings (in practice, the chunk texts from Step 4).
Output: a list of vectors, one per input string, ready for the `chunks.embedding`
        column from Step 5.

Embeddings are what make dense retrieval possible: a vector is the meaning of a
piece of text, positioned so that similar meanings sit close together. But this
step is not only "call the model." Three operational details are what make it
survive contact with reality:

  1. **Batching.** We send many chunks per request instead of one per request.
     Fewer round trips is good hygiene, though see the next point for why it is
     not the whole story.

  2. **Throttling on ITEMS, not requests.** The free tier allows 100 embed items
     per minute, and the count is per *item* (each chunk), not per HTTP request.
     So batching does not reduce the count at all: two calls of 20 chunks cost the
     same as one call of 40. A sliding-window limiter is what actually keeps us
     under the cap. (Two earlier versions of this module failed here: one added a
     home-made retry loop on top of the SDK's own retry and multiplied the request
     rate until it tripped the limit; the next still sent everything as fast as it
     could and tripped it again.)

  3. **Task types.** The model can embed text differently depending on whether it
     is a document being stored or a query being searched. Using the right task
     type is a real quality lever, and it costs nothing but a keyword.
"""
from __future__ import annotations

import time
from collections import deque

from google import genai
from google.genai import types

from config import EMBED_BATCH_SIZE, EMBED_DIM, EMBED_MODEL, GEMINI_API_KEY

# Fail loudly at import if the key is missing. A clear error here beats a
# confusing 401 halfway through embedding 252 chunks.
if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
    )

# One client for the process. Creating it per call would re-read credentials and
# rebuild HTTP connections every time. The SDK already retries transient 429/5xx
# responses internally, so we do NOT add our own retry on top.
_client = genai.Client(api_key=GEMINI_API_KEY)

# Free tier caps embedding at 100 items/minute. We aim for 85 to leave headroom.
_ITEM_BUDGET_PER_MINUTE = 85
_WINDOW_S = 60.0

# Timestamps of the items we have sent in the last window (sliding window).
_sent_at: deque[float] = deque()

# The two task types we use. Documents are embedded when we store the corpus;
# queries are embedded when the user asks something. Step 8 uses the query one.
DOCUMENT_TASK = "RETRIEVAL_DOCUMENT"
QUERY_TASK = "RETRIEVAL_QUERY"


def _throttle(item_count: int) -> None:
    """Block until sending `item_count` more items stays inside the 1-minute budget.

    A sliding window over "when did I send each item" is enough for a single
    process, which is all an ingest run is. A multi-worker deployment would need a
    shared limiter (Redis), but that is not this project.
    """
    now = time.monotonic()
    while _sent_at and now - _sent_at[0] >= _WINDOW_S:
        _sent_at.popleft()

    if _sent_at and len(_sent_at) + item_count > _ITEM_BUDGET_PER_MINUTE:
        # Sleep until the oldest item in the window ages out.
        time.sleep(_WINDOW_S - (now - _sent_at[0]) + 0.5)
        now = time.monotonic()
        while _sent_at and now - _sent_at[0] >= _WINDOW_S:
            _sent_at.popleft()

    for _ in range(item_count):
        _sent_at.append(time.monotonic())


def _embed_batch(texts: list[str], task_type: str) -> list[list[float]]:
    """Embed one batch. The SDK handles retrying transient failures for us."""
    config = types.EmbedContentConfig(
        task_type=task_type,
        # Truncate the 3072-dim native output to EMBED_DIM. `gemini-embedding-001`
        # is trained so that truncation like this stays accurate (Matryoshka), so
        # we get a 4x smaller index for very little quality loss.
        output_dimensionality=EMBED_DIM,
    )
    response = _client.models.embed_content(
        model=EMBED_MODEL, contents=texts, config=config
    )
    return [embedding.values for embedding in response.embeddings]


def embed_texts(
    texts: list[str], task_type: str = DOCUMENT_TASK
) -> list[list[float]]:
    """Embed a list of strings, batching and throttling internally.

    Returns vectors in the same order as the input, so results can be zipped
    straight back onto the chunks they came from.
    """
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        _throttle(len(batch))  # stay under the per-minute item budget
        vectors.extend(_embed_batch(batch, task_type))
    return vectors


def main() -> None:
    """Smoke test: embed a few real chunks and confirm the shape."""
    # Imported here, not at module top, so this module stays a leaf: the rest of
    # the codebase can use embed_texts without pulling in the chunking pipeline.
    from ingest.chunk import chunk_corpus

    chunks = chunk_corpus()
    sample = [chunk.text for chunk in chunks[:3]]

    vectors = embed_texts(sample)

    print(f"corpus has {len(chunks)} chunks; embedded the first {len(vectors)}")
    print(f"dims: {len(vectors[0])}  (expected {EMBED_DIM})")
    print(f"first 4 values of vector 0: {[round(v, 4) for v in vectors[0][:4]]}")
    print(f"each vector is {type(vectors[0][0]).__name__}-valued, length {len(vectors[0])}")


if __name__ == "__main__":
    main()

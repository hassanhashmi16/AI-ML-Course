"""Step 8 deliverable: dense (semantic) retrieval.

Input:  a question (plain text).
Output: the k chunks whose stored embeddings are closest to the question's meaning.

Dense retrieval matches on MEANING, not on words. "Which 8000er is the most
dangerous?" should find a chunk about Annapurna's death rate even though the chunk
never says "dangerous". That is the whole point, and it is exactly what keyword
search cannot do.

Two details make this correct rather than merely working:

  * **The query is embedded with the QUERY task type**, not the document one. The
    model treats a question and a stored passage differently on purpose. Using the
    wrong task type still returns vectors, they are just worse matched: a silent
    quality loss, no error.

  * **Cosine distance (`<=>`)** is the operator the HNSW index was built for
    (`vector_cosine_ops`). Distance is "lower is better", so we report
    `1 - distance` as a similarity score where higher is better, keeping it
    consistent with the sparse retriever.
"""
from __future__ import annotations

from config import RETRIEVE_K
from console import make_stdout_safe
from ingest.embed import QUERY_TASK, embed_texts
from ingest.store import connect
from retrieval.results import Retrieved


def dense_search(
    query: str,
    k: int = RETRIEVE_K,
    peak: str | None = None,
    conn=None,
) -> list[Retrieved]:
    """Return the k chunks closest in meaning to `query`.

    `peak` optionally restricts the search to one mountain (e.g. "K2"), which is
    the metadata filter every real RAG query ends up needing.
    """
    owns_connection = conn is None
    if owns_connection:
        conn = connect()

    try:
        # Embed the QUERY (not a document) - the task type matters.
        query_vector = embed_texts([query], task_type=QUERY_TASK)[0]

        # The same vector is used twice: once in the SELECT to report the
        # similarity, once in ORDER BY where it drives the index. Wrapping it in
        # `1 - ...` inside ORDER BY would stop the HNSW index being used, so the
        # arithmetic stays out of the ORDER BY.
        where = "WHERE d.peak = %s" if peak else ""
        sql = f"""
            SELECT c.id, c.content, c.section, d.source, d.peak,
                   1 - (c.embedding <=> %s::vector) AS score
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            {where}
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        """

        # Placeholders are filled in the order they appear in the text:
        # SELECT vector, [peak], ORDER BY vector, LIMIT.
        params: list = [query_vector]
        if peak:
            params.append(peak)
        params += [query_vector, k]

        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        if owns_connection:
            conn.close()

    return [
        Retrieved(
            chunk_id=row[0],
            content=row[1],
            section=row[2],
            source=row[3],
            peak=row[4],
            score=float(row[5]),
        )
        for row in rows
    ]


def main() -> None:
    """Ask a few questions and print what dense retrieval pulls back."""
    make_stdout_safe()

    queries = [
        "which eight-thousander is the deadliest?",
        "who made the first ascent of Annapurna and when?",
        "how difficult is K2 compared to Everest?",
    ]

    for query in queries:
        print(f"\nquery: {query}")
        for rank, result in enumerate(dense_search(query, k=5), start=1):
            print(f"  {rank}.  {result.score:.3f}  {result.label()}")
            print(f"       {result.preview()}")


if __name__ == "__main__":
    main()

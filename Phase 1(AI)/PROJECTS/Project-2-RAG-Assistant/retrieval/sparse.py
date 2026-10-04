"""Step 9 deliverable: sparse (keyword) retrieval with Postgres full-text search.

Input:  a question (plain text).
Output: the k chunks that best match the question's WORDS.

Dense retrieval (Step 8) matches meaning and misses exact strings. Sparse
retrieval is the mirror image: it matches exact words and numbers, and has no idea
that "dangerous" and "deadly" are related. The two fail in opposite directions,
which is the entire reason Step 11 combines them.

Why Postgres full-text search instead of a separate BM25 library:

  * It is already here. The `tsv` column was generated in Step 5 and indexed with
    GIN, so sparse search is one SQL query with no second system to run, sync, or
    pay for.
  * `websearch_to_tsquery` gives users a familiar grammar for free: quoted phrases,
    `OR`, and `-exclude`, parsed safely with no injection risk.
  * Ranking uses `ts_rank_cd` (cover density), which rewards query terms that
    appear close together in the text, not just present somewhere.

This retriever makes NO API call. It is pure SQL, so it costs nothing and adds no
latency beyond the database round trip.
"""
from __future__ import annotations

from config import RETRIEVE_K
from console import make_stdout_safe
from ingest.store import connect
from retrieval.results import Retrieved


def sparse_search(
    query: str,
    k: int = RETRIEVE_K,
    peak: str | None = None,
    conn=None,
) -> list[Retrieved]:
    """Return the k chunks whose text best matches `query` as keywords.

    Matching is done in the WHERE clause (`tsv @@ query`) so the GIN index can be
    used; ranking is done in ORDER BY. An unmatched query simply returns nothing.
    """
    owns_connection = conn is None
    if owns_connection:
        conn = connect()

    try:
        # Two placeholders for the same query string: one in the SELECT to compute
        # the score, one in the WHERE to filter. (Websearch syntax is parsed into a
        # proper tsquery, so the text is never interpolated into SQL.)
        where = "c.tsv @@ websearch_to_tsquery('english', %s)"
        if peak:
            where += " AND d.peak = %s"

        sql = f"""
            SELECT c.id, c.content, c.section, d.source, d.peak,
                   ts_rank_cd(c.tsv, websearch_to_tsquery('english', %s)) AS score
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE {where}
            ORDER BY score DESC
            LIMIT %s
        """

        # Placeholder order = the order they appear in the SQL text:
        # SELECT query, WHERE query, [peak], LIMIT.
        params: list = [query, query]
        if peak:
            params.append(peak)
        params.append(k)

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
    """Show dense vs sparse side by side on queries that favour each."""
    make_stdout_safe()
    from retrieval.dense import dense_search

    queries = [
        "which eight-thousander is the deadliest?",  # thematic: dense should win
        "Krzysztof Wielicki winter",                 # a person's name: sparse should win
        "Gasherbrum I 1958",                          # exact name + year: sparse should win
    ]

    for query in queries:
        print(f"\nquery: {query}")
        print("  dense (by meaning):")
        for result in dense_search(query, k=3):
            print(f"    {result.score:.3f}  {result.label()}")
        print("  sparse (by keywords):")
        for result in sparse_search(query, k=3):
            print(f"    {result.score:.3f}  {result.label()}")


if __name__ == "__main__":
    main()

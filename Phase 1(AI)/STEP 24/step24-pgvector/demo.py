"""Step 24 deliverable: store and search vectors in Postgres with pgvector.

Run it against any local Postgres with pgvector enabled:

    pip install "psycopg[binary]"
    python demo.py "postgresql://user:pass@localhost/dbname"

The vectors are only 3-D so you don't need a real embedding model — the point
is to see the SQL (distance operators, index, filtering), not the embeddings.
"""
import sys

import psycopg  # the Postgres driver; psycopg 3

# Small seed data. Each row is (content, category, embedding).
# Note the embeddings already group by meaning: "puppy"/"kitten" point along the
# x-axis, "car"/"truck" along the y-axis, "apple" along the z-axis. That makes
# the nearest-neighbor results easy to eyeball.
ROWS = [
    ("puppy",  "animals",  [1.0, 0.0, 0.0]),
    ("kitten", "animals",  [0.9, 0.1, 0.0]),
    ("car",    "vehicles", [0.0, 1.0, 0.0]),
    ("truck",  "vehicles", [0.0, 0.9, 0.1]),
    ("apple",  "food",     [0.0, 0.0, 1.0]),
]

# The SQL we run to set up the table + index. Inline here so the whole demo
# is one file and idempotent (IF NOT EXISTS lets you run it repeatedly).
SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS items (
    id         bigserial PRIMARY KEY,
    content    text NOT NULL,
    category   text NOT NULL,
    embedding  vector(3)
);
CREATE INDEX IF NOT EXISTS items_embedding_idx
    ON items USING hnsw (embedding vector_cosine_ops);
"""


def main(url: str) -> None:
    # `with` closes the connection automatically when the block ends.
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:  # a cursor is how you run SQL and read results

            cur.execute(SCHEMA_SQL)  # create the table + index

            # Insert each seed row. `%s` is a *parameter placeholder*, not
            # string formatting: psycopg sends the values separately, so this
            # can never be a SQL-injection hole. Never f-string raw values in.
            for content, category, emb in ROWS:
                cur.execute(
                    "INSERT INTO items (content, category, embedding) VALUES (%s, %s, %s)",
                    (content, category, emb),
                )

            # (1) Top-3 nearest to [1,0,0] by COSINE distance.
            # `<=>` is the cosine-distance operator; smaller = closer.
            # ORDER BY <distance> + LIMIT is the whole vector-search pattern,
            # and it's also what lets Postgres use the HNSW index.
            cur.execute(
                "SELECT content, embedding <=> %s AS dist FROM items "
                "ORDER BY embedding <=> %s LIMIT 3",
                ("[1,0,0]", "[1,0,0]"),
            )
            print("nearest to [1,0,0]:", cur.fetchall())

            # (2) Cosine SIMILARITY of the closest animal.
            # cosine similarity = 1 - cosine distance, so we wrap `<=>` in `1 - (...)`.
            # (Wrapping it here is fine because we only read ONE row, but doing
            # it in ORDER BY would disable the index — see the note in 24.4.)
            cur.execute(
                "SELECT content, 1 - (embedding <=> %s) AS sim FROM items "
                "WHERE category = %s ORDER BY embedding <=> %s LIMIT 1",
                ("[1,0,0]", "animals", "[1,0,0]"),
            )
            print("closest animal:", cur.fetchall())

            # (3) Filtered search: nearest VEHICLE to [0,1,0].
            # This combines a normal WHERE filter with vector search — the
            # pattern every real RAG query uses (Step 24.5).
            cur.execute(
                "SELECT content FROM items WHERE category = %s "
                "ORDER BY embedding <=> %s LIMIT 1",
                ("vehicles", "[0,1,0]"),
            )
            print("closest vehicle:", cur.fetchall())


if __name__ == "__main__":
    # Expect the connection URL as the only argument; print usage otherwise.
    if len(sys.argv) != 2:
        sys.exit("usage: python demo.py 'postgresql://user:pass@localhost/dbname'")
    main(sys.argv[1])

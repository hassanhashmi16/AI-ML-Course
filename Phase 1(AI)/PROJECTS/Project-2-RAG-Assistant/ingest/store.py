"""Step 7 deliverable (part 1): write documents and chunks into Postgres.

This is the only module that talks to the database, so SQL never leaks into the
pipeline or the retrieval code.

The important idea here is **idempotency**: running the pipeline twice must leave
the database exactly as running it once did. That is what lets you re-run ingest
after every change without fear of duplicates. Two hashes make it work:

  * documents.file_hash   - a fingerprint of the whole raw file. If it is
                            unchanged, we skip the file entirely and, crucially,
                            never call the (paid) embedding API for it.
  * chunks.content_hash   - a fingerprint of each chunk, the UNIQUE key that stops
                            the same text being stored twice.

The write strategy is "replace per document": upsert the document row, delete its
old chunks, insert the new ones. Deleting first means a file that got *shorter*
does not leave orphan chunks behind, which an upsert alone would miss.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from config import DATABASE_URL


def connect() -> psycopg.Connection:
    """Open a connection with the pgvector type adapter registered.

    register_vector teaches psycopg how to send a Python list as a `vector` and
    read one back as a list. Without it, passing a list to the embedding column
    fails with a type error.
    """
    conn = psycopg.connect(DATABASE_URL)
    register_vector(conn)
    return conn


def file_hash(path: Path) -> str:
    """Fingerprint of a whole file's bytes. Drives the skip-or-refresh decision."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_document(conn: psycopg.Connection, source: str) -> dict | None:
    """Return {'id', 'file_hash'} for a source file, or None if never ingested."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, file_hash FROM documents WHERE source = %s", (source,))
        row = cur.fetchone()
    return {"id": row[0], "file_hash": row[1]} if row else None


def upsert_document(
    conn: psycopg.Connection,
    *,
    source: str,
    peak: str | None,
    title: str | None,
    url: str | None,
    file_hash: str,
) -> int:
    """Insert the document row, or update it if this source already exists.

    ON CONFLICT makes this a single statement that works for both cases, so there
    is no "check then insert" race. `source` is the UNIQUE column it keys on.
    Returns the document id either way.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (source, peak, title, url, file_hash)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source) DO UPDATE SET
                peak        = EXCLUDED.peak,
                title       = EXCLUDED.title,
                url         = EXCLUDED.url,
                file_hash   = EXCLUDED.file_hash,
                ingested_at = now()
            RETURNING id
            """,
            (source, peak, title, url, file_hash),
        )
        return cur.fetchone()[0]


def delete_chunks(conn: psycopg.Connection, document_id: int) -> int:
    """Remove every chunk for a document (the 'replace' half of replace-per-doc)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
        return cur.rowcount


def insert_chunks(
    conn: psycopg.Connection, document_id: int, chunks: list, vectors: list
) -> int:
    """Insert every chunk with its embedding in one batched round trip.

    Chunks and vectors are zipped positionally: embed_texts() preserves order, so
    vector[i] always belongs to chunks[i].
    """
    rows = [
        (document_id, chunk.index, chunk.section, chunk.text,
         chunk.tokens, chunk.content_hash, vector)
        for chunk, vector in zip(chunks, vectors)
    ]
    with conn.cursor() as cur:
        # DO NOTHING guards the UNIQUE (document_id, content_hash) constraint, so a
        # repeated paragraph splits quietly instead of crashing the whole run.
        cur.executemany(
            """
            INSERT INTO chunks
                (document_id, chunk_index, section, content, token_count,
                 content_hash, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (document_id, content_hash) DO NOTHING
            """,
            rows,
        )
        return cur.rowcount


def counts(conn: psycopg.Connection) -> tuple[int, int]:
    """(number of documents, number of chunks) currently in the database."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM documents")
        documents = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM chunks")
        chunks = cur.fetchone()[0]
    return documents, chunks

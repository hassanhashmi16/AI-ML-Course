"""Step 7 deliverable (part 2): one command to build the whole index.

    python -m ingest.run_ingest

It runs the full pipeline for every cached article:

    parse (Step 3) -> chunk (Step 4) -> embed (Step 6) -> store (store.py)

and it is safe to run as many times as you like. A file whose bytes are unchanged
is skipped before it costs a single embedding request; a file that changed is
re-ingested and its old chunks are replaced.

Requires the raw corpus to already be on disk (Step 2) and Postgres to be running
(Step 5). If the raw files are missing it says so instead of failing obscurely.
"""
from __future__ import annotations

import json
import sys

from config import PEAKS_JSON, RAW_DIR
from ingest.chunk import chunk_section
from ingest.embed import embed_texts
from ingest.parse import parse_document
from ingest.store import (
    connect,
    counts,
    delete_chunks,
    file_hash,
    get_document,
    insert_chunks,
    load_peaks,
    upsert_document,
)


def load_manifest() -> dict[str, dict]:
    """Map filename -> manifest entry, so we can fill in peak/title/url.

    The manifest comes from Step 2. If it is absent we fall back to an empty dict
    and the document row simply has no metadata, which is not fatal.
    """
    path = RAW_DIR / "manifest.json"
    if not path.exists():
        return {}
    entries = json.loads(path.read_text(encoding="utf-8"))
    return {entry["file"]: entry for entry in entries}


def ingest_file(conn, path, meta: dict) -> tuple[str, int]:
    """Ingest one raw file. Returns (action, chunk_count) where action is
    'skipped' | 'added' | 'updated'."""
    new_hash = file_hash(path)
    existing = get_document(conn, path.name)

    # The idempotency check, and the reason we put it first: if the file has not
    # changed we return before parsing, chunking, or paying for embeddings.
    if existing and existing["file_hash"] == new_hash:
        return "skipped", 0

    sections = parse_document(path)
    chunks = [chunk for section in sections for chunk in chunk_section(section)]
    vectors = embed_texts([chunk.text for chunk in chunks])

    document_id = upsert_document(
        conn,
        source=path.name,
        peak=meta.get("peak"),
        title=meta.get("title"),
        url=meta.get("url"),
        file_hash=new_hash,
    )
    delete_chunks(conn, document_id)
    insert_chunks(conn, document_id, chunks, vectors)
    conn.commit()  # commit per file, so one bad file cannot undo the whole run

    return ("added" if existing is None else "updated"), len(chunks)


def main() -> None:
    paths = sorted(RAW_DIR.glob("*.txt"))
    if not paths:
        sys.exit("no raw files in data/raw - run `python -m ingest.fetch_corpus` first")

    manifest = load_manifest()

    conn = connect()
    tally = {"added": 0, "updated": 0, "skipped": 0}
    try:
        for path in paths:
            action, chunk_count = ingest_file(conn, path, manifest.get(path.name, {}))
            tally[action] += 1
            print(f"{action:8} {path.name:<28} {chunk_count:>4} chunks")

        # The structured facts live in peaks.json; load them into the peaks table
        # too, so Step 12 can answer exact-fact questions without touching retrieval.
        peaks = json.loads(PEAKS_JSON.read_text(encoding="utf-8"))["peaks"]
        peak_count = load_peaks(conn, peaks)
        conn.commit()

        documents, chunks = counts(conn)
    finally:
        conn.close()

    print("-" * 46)
    print(f"added {tally['added']}, updated {tally['updated']}, skipped {tally['skipped']}")
    print(f"database now holds {documents} documents, {chunks} chunks, {peak_count} peaks")


if __name__ == "__main__":
    main()

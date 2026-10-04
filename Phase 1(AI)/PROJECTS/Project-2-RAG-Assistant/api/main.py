"""Step 14 deliverable: the HTTP API.

Run it from the project root:

    uvicorn api.main:app --reload

Endpoints:
    GET  /health      liveness, plus a quick database reachability check
    GET  /peaks       the 14 peaks, straight from the table (no model involved)
    POST /ask         answer a question -> {answer, used_table, sources, latency_ms}
    POST /ask-stream  the same, but streams the answer token by token

This is the surface everything else attaches to: the React UI (Step 15), and later
the agent (Project 4) and monitoring (Project 8). Keeping it thin on purpose - it
does no retrieval or generation itself, it just calls the pipeline and logs the
result.
"""
from __future__ import annotations

import json
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from generation.answer import answer_question, stream_answer
from ingest.store import connect, list_peaks, log_query

app = FastAPI(title="Eight-Thousanders RAG Assistant")

# The React dev server runs on a DIFFERENT origin ("port"), and the browser refuses
# to let JavaScript there read our responses unless we explicitly allow it. This is
# CORS. List the exact origin rather than "*": "*" works but is sloppy once real
# data is involved.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite's default dev port
    allow_methods=["*"],
    allow_headers=["*"],
)


class Question(BaseModel):
    """Request body. `min_length=1` means an empty question is rejected with a 422
    before our code ever runs."""

    question: str = Field(min_length=1)


@app.get("/health")
def health() -> dict:
    """Is the service up, and can it reach the database?"""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM chunks")
            chunks = cur.fetchone()[0]
    finally:
        conn.close()
    return {"status": "ok", "chunks": chunks}


@app.get("/peaks")
def peaks() -> list[dict]:
    """The 14 peaks, from the table. No retrieval, no model, no cost."""
    conn = connect()
    try:
        return list_peaks(conn)
    finally:
        conn.close()


@app.post("/ask")
def ask(body: Question) -> dict:
    """Answer a question and log it.

    Blocking: the client waits for the whole answer. Simple, and fine for short
    answers; /ask-stream is the version that feels alive.
    """
    started = time.perf_counter()
    result = answer_question(body.question)
    latency_ms = int((time.perf_counter() - started) * 1000)

    # Log every query. Nothing reads it yet, but it is what makes monitoring a later
    # plugin instead of a rewrite.
    conn = connect()
    try:
        log_query(
            conn,
            question=body.question,
            used_table=result.used_table,
            retrieved_ids=[source.chunk_id for source in result.sources],
            latency_ms=latency_ms,
            answer_chars=len(result.answer),
        )
    finally:
        conn.close()

    return {
        "answer": result.answer,
        "used_table": result.used_table,
        "sources": [
            {"source": source.source, "section": source.section}
            for source in result.sources
        ],
        "latency_ms": latency_ms,
    }


@app.post("/ask-stream")
def ask_stream(body: Question) -> StreamingResponse:
    """Stream the answer as newline-delimited JSON (one object per line).

    Line shapes:
        {"type": "sources", "sources": [{"source": ..., "section": ...}, ...]}
        {"type": "token", "text": "..."}      (repeated)
        {"type": "done"}

    NDJSON (rather than raw text) is what lets us send the sources FIRST and the
    words after, so the UI can show citations immediately while the answer types
    out. A browser reads it from a fetch() stream, line by line.
    """

    def events():
        for kind, payload in stream_answer(body.question):
            if kind == "sources":
                yield json.dumps(
                    {
                        "type": "sources",
                        "sources": [
                            {"source": s.source, "section": s.section} for s in payload
                        ],
                    }
                ) + "\n"
            else:
                yield json.dumps({"type": "token", "text": payload}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")

"""Step 29 deliverable: the FastAPI side of a React <-> FastAPI connection.

Run it:

    pip install "fastapi[standard]"
    uvicorn main:app --reload     # serves http://localhost:8000

This backend does NOT connect to a real LLM (databases/LLM wiring come later).
It simulates token generation with `asyncio.sleep`, so you can watch the
frontend stream tokens in real time. The frontend lives in `../frontend/Chat.jsx`.
"""
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


app = FastAPI(title="Step 29 backend")


# ---------------------------------------------------------------------------
# CORS: let the React dev server (localhost:5173) read our responses.
# Without this, the BROWSER blocks the request — not FastAPI, the browser.
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite's default origin
    allow_credentials=True,
    allow_methods=["*"],                      # GET, POST, etc.
    allow_headers=["*"],
)


# The shape of the JSON body the frontend will send: {"question": "..."}.
class Question(BaseModel):
    question: str


# ---------------------------------------------------------------------------
# Blocking endpoint: returns the WHOLE answer at once.
# The frontend sends a question, waits, then renders the full answer.
# ---------------------------------------------------------------------------

@app.post("/ask")
async def ask(q: Question):
    # In real life this would call your RAG pipeline / LLM and return its text.
    answer = f"Blocking answer to: {q.question}"
    return {"answer": answer}


# ---------------------------------------------------------------------------
# Streaming endpoint: pushes raw text chunks as they're "generated".
# The frontend reads these chunks one at a time and appends them live.
# (This is the endpoint the frontend actually uses — it's how LLM UIs feel.)
# ---------------------------------------------------------------------------

@app.post("/ask-stream")
async def ask_stream(q: Question):
    # The tokens a real LLM would emit one by one. Here we fake them.
    tokens = ["Hello", ", ", "world", "!"]

    async def generate():
        # `yield` pushes each token to the client as soon as it's ready.
        for token in tokens:
            yield token
            await asyncio.sleep(0.1)   # simulate slow token generation

    # media_type="text/plain" -> raw text stream (read with fetch + reader).
    # Use "text/event-stream" instead if the frontend uses EventSource (GET).
    return StreamingResponse(generate(), media_type="text/plain")


# ---------------------------------------------------------------------------
# A GET streaming endpoint, for the EventSource (SSE) pattern.
# NOTE: EventSource can only GET, so it can't carry a JSON body — that's why
# the real streaming endpoint above uses POST + fetch/ReadableStream.
# ---------------------------------------------------------------------------

@app.get("/stream")
async def stream():
    async def generate():
        for token in ["Hi", " from ", "SSE", "!"]:
            # SSE format: each message is "data: <chunk>\n\n".
            yield f"data: {token}\n\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(generate(), media_type="text/event-stream")

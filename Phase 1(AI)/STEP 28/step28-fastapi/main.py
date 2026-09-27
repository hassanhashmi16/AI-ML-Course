"""Step 28 deliverable: a FastAPI app exercising every subtopic.

Run it (from this directory) with:

    pip install "fastapi[standard]"
    uvicorn main:app --reload

Then open the AUTO-GENERATED interactive docs at:

    http://127.0.0.1:8000/docs

Each section below maps to a roadmap subtopic (28.1 .. 28.8). The whole point
of FastAPI is that your type hints do the validation, parsing, and docs for you
— so most of these endpoints are just annotated Python functions.
"""
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Header, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


app = FastAPI(title="Step 28 demo")


# ---------------------------------------------------------------------------
# 28.3 — Pydantic models: the shapes for request and response BODIES.
# ---------------------------------------------------------------------------

class Item(BaseModel):
    """The request body for POST /items (validated automatically)."""
    name: str
    price: float = Field(gt=0)          # must be > 0, else 422
    is_offer: bool = False              # has a default -> optional field


class ItemResponse(BaseModel):
    """The response shape — only these fields are ever returned."""
    name: str
    price: float


# ---------------------------------------------------------------------------
# 28.1 — Routing: "HTTP method + path -> function".
# ---------------------------------------------------------------------------

@app.get("/")                            # GET /  -> plain root
def root():
    return {"message": "hello from FastAPI"}


# ---------------------------------------------------------------------------
# 28.2 — Path parameter with validation. {item_id} comes from the URL,
# and `int` makes FastAPI convert "42" -> 42 and reject "abc" with a 422.
# ---------------------------------------------------------------------------

@app.get("/items/{item_id}")
def read_item(item_id: int):
    # 28.7 — return a real HTTP error, not a 200 with {"error": ...}.
    if item_id not in {1, 2, 3}:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"item_id": item_id}


# ---------------------------------------------------------------------------
# 28.2 — Query parameters with validation. These come after a '?' in the URL:
#   GET /items?category=books&limit=5
# ---------------------------------------------------------------------------

@app.get("/items")
def list_items(category: str = "all", limit: int = Field(10, ge=1, le=100)):
    return {"category": category, "limit": limit}


# ---------------------------------------------------------------------------
# 28.3 + 28.4 — POST with a validated body AND a dependency + response model.
# ---------------------------------------------------------------------------

def get_database():
    """A reusable provider. In real code this returns a DB connection; here it
    returns a fake one so the demo has no external dependency."""
    return {"connection": "fake-db-connection"}


@app.post("/items", response_model=ItemResponse)
def create_item(item: Item, db: dict = Depends(get_database)):
    # `item` is already a validated Item object; `db` was injected by Depends.
    # response_model=ItemResponse filters the return to only {name, price}.
    return {"name": item.name, "price": item.price, "db": db}  # extra field dropped


# ---------------------------------------------------------------------------
# 28.5 — Background task: do work AFTER the response is sent.
# ---------------------------------------------------------------------------

def write_log(message: str):
    # Stand-in for slow, non-critical work (email, analytics, re-index job).
    print(f"[background log] {message}")


@app.post("/items/notify")
def create_and_notify(item: Item, background: BackgroundTasks):
    background.add_task(write_log, f"created item: {item.name}")
    return {"status": "queued", "name": item.name}   # returns immediately


# ---------------------------------------------------------------------------
# 28.6 — Streaming response (SSE): push pieces as they're ready instead of
# buffering. This is the mechanism you'd wire an LLM token stream into.
# ---------------------------------------------------------------------------

def token_generator():
    # `yield` pushes each chunk to the client as soon as it's produced.
    for token in ["Hello", ", ", "world", "!"]:
        yield token


@app.get("/stream")
def stream_tokens():
    return StreamingResponse(token_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# 28.8 — Security: an API-key check expressed as a DEPENDENCY (28.4).
# Any route that declares `Depends(verify_api_key)` is gated by it.
# ---------------------------------------------------------------------------

def verify_api_key(x_api_key: str = Header(None)):
    # Read the "X-Api-Key" header; raise 401 if it's wrong/missing.
    if x_api_key != "secret-token":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
    return x_api_key


@app.get("/secure")
def secure_route(api_key: str = Depends(verify_api_key)):
    # This function only runs if verify_api_key passed (returned without raising).
    return {"access": "granted", "key": api_key}

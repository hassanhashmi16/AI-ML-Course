# Step 28: FastAPI

> **Covers:** path operations & routing, path/query parameters + validation, request/response models (Pydantic), dependency injection, background tasks, streaming responses (SSE/WebSocket), error handling, and security basics. This is the backend you'll serve every LLM feature through — and streaming responses are how you push tokens to a frontend.

---

## The Problem

Up to now, everything you've built — the RAG pipeline, the retrieval, the chains — lives inside a Python script or notebook. But a real product is an *API*: something a frontend, a mobile app, or another service can call over HTTP. You need a way to say "when someone `POST`s a question to `/ask`, run my RAG pipeline and return the answer" — with validation, error handling, and the ability to stream tokens back. FastAPI is the standard Python framework for that, and it's the layer that finally turns your AI work into something other people can actually use.

---

## Foundational Concepts

### What a web API actually is

A web API is just a set of rules for HTTP requests and responses:

- A request has a **method** (GET, POST, PUT, DELETE) and a **path** (`/items/42`).
- A response has a **status code** (200 = OK, 404 = not found, 422 = validation failed) and a **body** (usually JSON).

FastAPI's job is to connect a Python function to an HTTP route — "run *this function* when a request comes in at *that* path" — and to automatically handle the boring parts: parsing the request into Python types, validating it, and serializing your return value back to JSON.

### The type-hint magic (this is the whole trick)

FastAPI's defining feature is that it **reads your Python type hints** and uses them to do validation, parsing, and documentation *for free*:

```python
@app.get("/items/{item_id}")
def read_item(item_id: int):
    return {"item_id": item_id}
```

Because you wrote `item_id: int`, FastAPI automatically: (1) extracts `item_id` from the URL path, (2) converts the string `"42"` into the integer `42`, (3) returns a `422` error if someone passes `/items/abc`, and (4) documents the parameter in the auto-generated docs. You write a type hint; FastAPI does the rest. This is why FastAPI feels like writing ordinary Python with annotations, not like configuring a web server.

### The docs write themselves

FastAPI auto-generates interactive API docs at `/docs` (Swagger UI) and `/redoc`, derived from your type hints and Pydantic models. You get a clickable, testable UI for every endpoint without writing a line of documentation. That's a huge productivity win and a reason FastAPI is the default.

---

## 28.1 — Path operations & routing

A **route** is "HTTP method + path → function." You register one with a decorator:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")                    # GET / -> hello
def root():
    return {"message": "hello"}

@app.post("/items")              # POST /items -> create
def create_item():
    return {"created": True}
```

- The decorator name (`@app.get`, `@app.post`, `@app.put`, `@app.delete`) is the HTTP method.
- The path is the URL after your domain.
- The function's return value is automatically serialized to JSON.

**`def` vs `async def`:** an endpoint can be a normal function (`def`) or an async function (`async def`). Use `async def` when you're `await`ing something async inside — like an async LLM client call — so the server isn't blocked while it waits. FastAPI runs `def` endpoints in a threadpool and `async def` endpoints on the event loop, so both work; the rule is simply "use `async def` if you `await` async work inside."

**Routing** just means "which function handles which path." FastAPI matches the most specific path first, and path parameters (28.2) let one function handle many URLs like `/items/1`, `/items/2`, ….

---

## 28.2 — Path & query parameters, validation

There are two ways to pass data in a URL:

- **Path parameters** — embedded in the path itself (`/items/42`, where `42` is the `item_id`).
- **Query parameters** — after a `?` (`/items?category=books&limit=10`).

Both are declared as function arguments with type hints, and both get validated automatically:

```python
@app.get("/items/{item_id}")                      # path param: {item_id}
def read_item(item_id: int):                       # typed -> validated
    return {"item_id": item_id}

@app.get("/items")                                 # query params
def list_items(category: str = "all", limit: int = 10):
    return {"category": category, "limit": limit}
```

In the second example, `category` and `limit` are **query parameters with defaults** — `GET /items?category=books` fills `category="books"` and leaves `limit=10`. You can also mark parameters optional (`category: str | None = None`) or enforce constraints with Pydantic's `Field` (e.g., `limit: int = Field(10, ge=1, le=100)`). If a client sends `limit=abc`, FastAPI returns `422` automatically — you never have to hand-write that check.

---

## 28.3 — Request & response models (Pydantic)

URL parameters are fine for simple values, but when a client sends a JSON *body* (the normal case for POST), you want a typed object, not a raw dict. That's a **Pydantic model**:

```python
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    price: float
    is_offer: bool = False          # default -> optional field

@app.post("/items")
def create_item(item: Item):         # FastAPI parses + validates the body
    return {"item_name": item.name, "price": item.price}
```

Because `item: Item`, FastAPI reads the request body, validates it against the model (wrong type → `422`), and hands you a validated `Item` object. **Response models** work the other direction: declare `response_model=ItemResponse` on the decorator, and FastAPI filters/serializes your return value to that shape — so you never accidentally leak a field you didn't mean to expose. This is the same Pydantic you'll use for structured LLM output (Step 27's output parsers) and tool schemas (Step 32).

---

## 28.4 — Dependency injection (Depends)

**Dependency injection (DI)** means "give my function what it needs, rather than making it create it." The function declares a dependency, and FastAPI provides it. In FastAPI you declare dependencies with `Depends()`:

```python
from fastapi import Depends

def get_database():                 # a reusable "provider"
    return {"connection": "fake-db-connection"}

@app.get("/users")
def list_users(db = Depends(get_database)):   # db injected automatically
    return {"db": db}
```

Why this matters, in practice:

- **Reuse** — `get_database` is written once and injected everywhere, instead of copy-pasted.
- **Testing** — swap the real dependency for a fake one in tests.
- **Auth/security** — the single most common use (28.8): an endpoint declares `Depends(require_user)`, and FastAPI runs the auth check *before* the endpoint body, so protected endpoints are one line.

Dependencies can themselves have dependencies, and FastAPI caches them within a single request — so a "get current user" dependency that hits the DB runs once, not on every use.

---

## 28.5 — Background tasks

Sometimes you want to do work *after* you've already returned a response — send a confirmation email, log analytics, kick off an indexing job. Blocking the response to do that is wasteful. FastAPI's `BackgroundTasks` runs the work after the response is sent:

```python
from fastapi import BackgroundTasks

def write_log(message: str):
    print(f"[log] {message}")          # slow, non-critical work

@app.post("/items")
def create_item(item: Item, background: BackgroundTasks):
    background.add_task(write_log, f"created {item.name}")
    return {"status": "queued"}         # returns immediately; log written after
```

The AI-specific use case: after you return an answer, you might *asynchronously* log the query, store feedback, or trigger a re-embedding job — without making the user wait. (For genuinely long-running jobs that need retries and durability, you'd graduate to a task queue like Celery or Redis Queue — background tasks are for "finish this after responding," not "run this reliably at scale.")

---

## 28.6 — Streaming responses (SSE / WebSocket)

This is the most AI-relevant section. LLM responses are slow — they generate token by token — and blocking until the whole answer is done makes the user stare at a blank screen. Instead, you **stream** tokens back as they're produced. The standard tool is **Server-Sent Events (SSE)**: a one-way stream from server to client over a normal HTTP connection.

```python
from fastapi.responses import StreamingResponse

def generate():
    for token in ["Hello", ", ", "world", "!"]:
        yield token                    # send each piece as it's ready

@app.get("/stream")
def stream():
    return StreamingResponse(generate(), media_type="text/event-stream")
```

The `generate()` function is a **generator** (it uses `yield`), so each `yield` pushes a chunk to the client as soon as it's produced, instead of waiting to assemble the whole response. This is exactly the mechanism you'd wire a real LLM's token stream into — `yield` each token as the model emits it.

- **SSE** = one-way (server → client), simplest, ideal for streaming tokens and progress.
- **WebSocket** = two-way, persistent connection, needed when the client must also send messages mid-stream (e.g., a live voice/chat UI that needs to cancel or interrupt).

Here's the WebSocket shape — note it's `async`, because the connection stays open and you wait on each message:

```python
from fastapi import WebSocket

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()                       # accept the connection
    while True:
        data = await websocket.receive_text()      # block until a message arrives
        await websocket.send_text(f"echo: {data}") # send a reply back
```

For most LLM apps, SSE is all you need; reach for WebSockets only when you need bidirectional communication.

---

## 28.7 — Error handling (HTTPException)

When something goes wrong, you return a proper HTTP error with a status code and a message — not a `200` with `{"error": ...}` stuffed in it. FastAPI gives you `HTTPException` for that:

```python
from fastapi import HTTPException

@app.get("/items/{item_id}")
def read_item(item_id: int):
    if item_id not in {1, 2, 3}:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"item_id": item_id}
```

Raising `HTTPException` tells FastAPI to return the right status code and a structured `{"detail": "Item not found"}` body. The rules of thumb:

- `404` — resource doesn't exist.
- `422` — request failed validation (FastAPI raises this automatically).
- `401`/`403` — auth problems (28.8).
- `500` — something crashed in *your* code (don't raise this by hand; it means an unhandled exception).

For app-wide handling, you can register custom exception handlers, but `HTTPException` covers most cases.

---

## 28.8 — Security basics (API keys / OAuth2)

Security in FastAPI is usually a **dependency** (28.4) that checks credentials and raises `401` if they fail. Two common patterns:

**API key** (simplest — a secret in a header):

```python
from fastapi import Header, Depends, HTTPException, status

def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != "secret-token":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad key")
    return x_api_key

@app.get("/secure")
def secure(api_key: str = Depends(verify_api_key)):
    return {"access": "granted"}
```

**OAuth2 password flow** (the standard "log in with username/password → get a token"):

```python
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@app.post("/token")
def login(form: OAuth2PasswordRequestForm = Depends()):
    # verify form.username / form.password, then return a token
    return {"access_token": "the-token", "token_type": "bearer"}

@app.get("/users/me")
def me(token: str = Depends(oauth2_scheme)):
    return {"token": token}
```

The key idea: **security is a dependency.** You write one `verify_*` function, attach it with `Depends()`, and every protected endpoint is automatically gated — and FastAPI even documents the auth requirement in `/docs`. (The OAuth2 helpers handle the plumbing; the actual token verification is something you plug in, usually with a library like `python-jose` or `PyJWT`.)

---

## Pitfalls

1. **Returning `200` with `{"error": ...}`.** Use `HTTPException` and the real status code — clients and monitoring tools depend on it.
2. **Blocking on slow work in the endpoint.** That makes every request wait. Use `BackgroundTasks` for post-response work, or a task queue for long jobs.
3. **Buffering LLM output instead of streaming.** If you call the LLM and `return` the whole answer, the user waits for the full generation. Use `StreamingResponse`/SSE to push tokens as they arrive.
4. **Not declaring `response_model`.** Without it, you can leak fields you didn't mean to expose. Declare the shape you return.
5. **Re-implementing validation by hand.** FastAPI already validates from your type hints and Pydantic models — hand-written `if not isinstance(...)` checks are redundant.
6. **Putting secrets in code.** API keys and tokens belong in environment variables/secret stores, not hardcoded (even in demos).

---

## Quick Reference

| Goal | FastAPI idiom |
|---|---|
| Define a route | `@app.get("/path")` / `@app.post(...)` |
| Path param | `def f(item_id: int)` with `{item_id}` in path |
| Query param | `def f(limit: int = 10)` |
| Request body | `def f(item: Item)` (Pydantic model) |
| Response shape | `response_model=Item` on the decorator |
| Dependency | `def f(x = Depends(provider))` |
| Background work | `BackgroundTasks.add_task(fn, ...)` |
| Stream tokens | `StreamingResponse(generator(), media_type="text/event-stream")` |
| Return an error | `raise HTTPException(status_code=404, detail="...")` |
| Protect a route | `def f(token = Depends(verify))` |
| API key | header param + `Depends` check |

---

## Theory Summary

- **FastAPI turns annotated Python functions into a validated, documented HTTP API.** The type hints aren't decoration — they *are* the validation, parsing, and docs.
- **An endpoint is just "route → function," and everything else is a dependency.** Path/query/body = inputs; Pydantic models = shapes; `Depends` = reusable providers (auth, DB, config); `HTTPException` = errors.
- **Stream, don't buffer, for LLM output.** The one FastAPI feature that's genuinely AI-specific is streaming responses — that's how you push tokens to a user instead of making them wait.
- **Security is a dependency, not a feature bolted onto each route.** One `verify_*` function, attached with `Depends`, gates every protected endpoint consistently.

---

## Deliverable

**`Phase 1(AI)/STEP 28/step28-fastapi/`**

- **`main.py`** — a single, runnable FastAPI app that exercises every subtopic: routing, path/query params with validation, a Pydantic request/response model, dependency injection, a background task, an SSE streaming endpoint, an `HTTPException` error path, and an API-key-protected route. Heavily commented so each piece maps back to 28.1–28.8.

**Run it:** `pip install "fastapi[standard]"`, then `uvicorn main:app --reload` (from the `step28-fastapi/` directory), and open `http://127.0.0.1:8000/docs` for the auto-generated interactive docs.

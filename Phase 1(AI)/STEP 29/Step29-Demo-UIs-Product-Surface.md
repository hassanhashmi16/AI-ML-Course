# Step 29: Demo UIs & the Product Surface (React edition)

> **Covers:** the product-judgment decisions that turn an API into a trustworthy product (stream vs. block, show sources, expose cost, loading/error states), and a step-by-step guide to wiring a FastAPI backend (Step 28) to a React frontend — including token streaming. You know React, so this step skips Streamlit/Gradio and does the interesting version: connecting your AI backend to a real React UI.

---

## The Problem

Step 28 gave you a FastAPI API — but an API endpoint is not usable by a stranger. A hiring manager won't `curl` your `/ask` route; they want something to click. You know React, so the frontend itself isn't the hard part. The hard parts are: (1) the *product decisions* that make an AI UI trustworthy, and (2) the *concrete wiring* — CORS, streaming tokens from the backend into React, and handling loading/error states. This step covers both. (Databases come later; this step is frontend + backend only.)

---

## Foundational Concepts

### The browser never talks to the AI directly

The architecture is always three layers:

```
React (browser)  →  HTTP  →  FastAPI  →  your AI pipeline (embeddings, retrieval, LLM)
```

The React app never imports your model or calls the LLM API directly. It sends an HTTP request to *your* backend, and *your backend* runs the AI pipeline (Steps 20–28) and returns the result. Why? Your backend holds the API keys, the vector store, and the logic — none of which belong in a browser. The frontend is just a thin shell that sends questions and displays answers.

### Two ways to get a response: request/response vs. streaming

- **Request/response (blocking):** React sends a request, waits for the *entire* answer, then displays it. Simple, but the user stares at a spinner while the LLM generates for seconds.
- **Streaming:** the backend pushes pieces of the answer as they're generated, and React appends them to the screen in real time. Feels alive — this is how ChatGPT/Claude UIs work. Slightly harder to build (Step 28.6's SSE/generators).

### CORS: why the browser blocks you

By default, a browser will *refuse* to let JavaScript on one origin (say `localhost:5173`, your React dev server) read a response from a different origin (`localhost:8000`, your FastAPI server). That's a browser security rule called **CORS** (Cross-Origin Resource Sharing). It's not FastAPI rejecting you — it's the browser. The fix is either to tell FastAPI to allow the React origin, or to use a dev proxy so the browser never sees a cross-origin request at all (both shown below).

---

## Part 1 — The product judgment

These decisions are framework-agnostic. They're the difference between "a demo that works" and "a product a stranger trusts."

### Stream tokens, or block?

| | Block (wait for full answer) | Stream (tokens as they arrive) |
|---|---|---|
| What the user sees | A spinner, then the full answer | The answer typing out live |
| Implementation | `fetch`, one state update | SSE/streaming, many small updates |
| Feel | Slow, especially for long answers | Responsive, "alive" |
| When | Short, fast responses; internal tools | Chat UIs, anything with a slow LLM |

**The rule:** for any LLM response that takes more than ~1 second, stream. Perceived latency matters more than actual latency — watching tokens appear feels fast; waiting on a spinner feels broken. The implementation cost is low once you've done it once (it's the bulk of Part 2).

### Show sources, or hide them?

When you surface *where* an answer came from (the retrieved chunks from Step 26), you give the user a reason to trust the answer — and a way to verify it. Hiding sources is cleaner, but it makes the product a black box that says "trust me."

**The rule:** show sources for anything where accuracy matters (RAG over documents, customer support, research). Users click them to verify, and when the AI *is* wrong, they can see *why*. The cost is a small UI element — a collapsible "Sources" list — which is almost always worth it.

### Expose cost, or not?

Every answer has a token/$$ cost. You can show it ("this answer cost $0.002") or hide it.

**The rule:** hide it for end users (noise), expose it for *yourself* — log cost per query server-side so you can monitor spend. If your product *bills* per query or the user is a developer, surface it; otherwise keep it internal. The point is that cost is a *measured, monitored* thing even when it's not *shown*.

### Loading, error, and empty states

A UI that only handles the happy path is broken. You need four states for every AI interaction:

1. **Idle** — nothing asked yet (show a prompt/placeholder).
2. **Loading** — request in flight (spinner, or "thinking…").
3. **Success** — answer + sources.
4. **Error** — the request failed (network down, backend 500, timed out). Show a retry button, not a blank screen.

Most of the code in Part 2 is just managing these four states with React's `useState`.

---

## Part 2 — Connecting FastAPI to React, step by step

Here's the full path from "two empty folders" to "React streams an answer from FastAPI." Each step has the actual code.

### Step 1: Project layout

Two separate apps that run side by side:

```
my-app/
├── backend/          # FastAPI (Python), runs on http://localhost:8000
│   └── main.py
└── frontend/         # React (Vite), runs on http://localhost:5173
    └── src/
        └── App.jsx
```

### Step 2: Enable CORS on the FastAPI side

In `backend/main.py`, allow your React origin:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # your Vite dev server origin
    allow_credentials=True,
    allow_methods=["*"],                      # GET, POST, etc.
    allow_headers=["*"],
)
```

`allow_origins=["*"]` works too but is sloppy for anything real — list the specific origin(s) you trust. (Alternative in Step 6: use Vite's proxy to avoid CORS entirely.)

### Step 3: A couple of endpoints to talk to

Add a simple blocking endpoint and a streaming endpoint (the streaming one is what you'll actually use for an LLM):

```python
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio

class Question(BaseModel):
    question: str

# Blocking: returns the whole answer at once.
@app.post("/ask")
async def ask(q: Question):
    answer = f"You asked: {q.question}"   # in real life: call your RAG pipeline
    return {"answer": answer}

# Streaming: pushes raw text chunks as they're "generated".
@app.post("/ask-stream")
async def ask_stream(q: Question):
    async def generate():
        for token in ["Hello", ", ", "world", "!"]:   # real life: yield each LLM token
            yield token
            await asyncio.sleep(0.1)                  # simulate slow token generation
    return StreamingResponse(generate(), media_type="text/plain")
```

### Step 4: Run both dev servers

```bash
# terminal 1 (backend)
cd backend
uvicorn main:app --reload          # http://localhost:8000

# terminal 2 (frontend)
cd frontend
npm run dev                        # http://localhost:5173 (Vite default)
```

### Step 5: A simple fetch from React (blocking)

In `frontend/src/App.jsx`:

```jsx
import { useState } from "react";

function App() {
  const [answer, setAnswer] = useState("");

  const ask = async () => {
    const res = await fetch("http://localhost:8000/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: "hi" }),
    });
    const data = await res.json();
    setAnswer(data.answer);   // one update, after the full response
  };

  return (
    <div>
      <button onClick={ask}>Ask</button>
      <p>{answer}</p>
    </div>
  );
}
```

That's the whole request/response pattern: `fetch` → parse JSON → set state. The blocking version is this simple.

### Step 6: Streaming tokens into React (the important part)

Two ways, depending on your HTTP method. **This is the subtle part most people get wrong.**

**`EventSource` — GET only.** The browser's built-in `EventSource` streams SSE, but it can only send GET requests, so it can't carry your question in a body. Use it for a GET streaming endpoint:

```jsx
useEffect(() => {
  const es = new EventSource("http://localhost:8000/stream");  // GET
  es.onmessage = (e) => setText((prev) => prev + e.data);       // append each chunk
  return () => es.close();                                       // cleanup
}, []);
```

**`fetch` + `ReadableStream` — POST (the one you actually need).** To send a question *and* stream the answer, `EventSource` won't work (can't POST). You use `fetch` with a stream reader instead:

```jsx
const [answer, setAnswer] = useState("");
const [loading, setLoading] = useState(false);

const askStream = async () => {
  setLoading(true);
  setAnswer("");                          // clear previous answer
  const res = await fetch("http://localhost:8000/ask-stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: "hi" }),
  });

  const reader = res.body.getReader();    // read the response as a stream
  const decoder = new TextDecoder();      // turn bytes into text
  while (true) {
    const { done, value } = await reader.read();   // grab the next chunk
    if (done) break;
    setAnswer((prev) => prev + decoder.decode(value));  // append tokens live
  }
  setLoading(false);
};
```

This is the canonical "stream an LLM answer into React" loop: read chunks, decode them, append to state. Each `setAnswer` triggers a re-render, so the text appears to type itself out.

### Step 7: Manage the four states (loading / error / success / idle)

Wrap the above in explicit state handling — this is what makes it a *product* and not a script:

```jsx
const [status, setStatus] = useState("idle");   // idle | loading | error | success
const [answer, setAnswer] = useState("");

const ask = async () => {
  setStatus("loading");
  try {
    // ... the fetch + stream loop from Step 6 ...
    setStatus("success");
  } catch (err) {
    setStatus("error");                 // network down, backend 500, timeout
  }
};

return (
  <div>
    {status === "loading" && <p>Thinking…</p>}
    {status === "error" && <button onClick={ask}>Retry</button>}
    {answer && <p>{answer}</p>}
  </div>
);
```

### Step 8 (optional): use Vite's proxy instead of CORS

Instead of `allow_origins` on the backend, you can make the browser *think* everything is same-origin. In `frontend/vite.config.js`:

```js
export default {
  server: {
    proxy: {
      "/api": "http://localhost:8000",   // forward /api/* to FastAPI
    },
  },
};
```

Then in React, fetch `"/api/ask"` (relative) instead of `"http://localhost:8000/ask"`. The Vite dev server forwards the request, so the browser never makes a cross-origin call and CORS is moot. Either approach works; the proxy is cleaner in dev, but in production (separate domains) you'll need real CORS config.

---

## Pitfalls

1. **Forgetting CORS.** The browser blocks the request, and it looks like the backend is broken. Always check for a CORS error in the browser console first.
2. **Using `EventSource` for POST.** `EventSource` only does GET — if you need to send a question and stream the answer, use `fetch` + `ReadableStream`.
3. **Not handling the error state.** A failed request should show a retry button, not a frozen spinner. Wrap `fetch` in `try/catch`.
4. **Cleaning up streams/connections.** Close `EventSource` (and abort in-flight `fetch`) in the `useEffect` cleanup, or you'll leak connections when the component unmounts.
5. **Buffering the answer and calling it "streaming."** Streaming means the *backend* yields chunks and the *frontend* appends them incrementally — not "wait for the whole thing, then render."
6. **Hiding sources on a trust-sensitive feature.** If accuracy matters, show the user what the answer was grounded in.
7. **Hardcoding the backend URL.** Use an environment variable or the Vite proxy, so the same frontend works in dev and production.

---

## Quick Reference

| Goal | How |
|---|---|
| Allow React to call FastAPI | `CORSMiddleware` with `allow_origins` (or Vite proxy) |
| Blocking request | `fetch(url).then(res => res.json())` |
| Stream (GET) | `EventSource` + `es.onmessage` |
| Stream (POST) | `fetch` + `res.body.getReader()` + `TextDecoder` |
| Four UI states | `useState` for idle/loading/error/success |
| Show sources | render retrieved chunks in a collapsible list |
| Cost | log server-side; show only if it's a user-facing feature |

---

## Theory Summary

- **The frontend is a thin shell over your backend.** React sends questions and displays answers; FastAPI holds the AI logic, keys, and vector store. Never put AI logic or secrets in the browser.
- **Stream for anything slow.** Perceived latency is what users feel, and token streaming turns "waiting" into "watching." The mechanism (Step 28's generators → `fetch`/`ReadableStream` in React) is the one piece of real plumbing in this step.
- **Product judgment is part of the job.** Stream vs. block, show vs. hide sources, and cost are decisions an AI engineer is expected to have opinions about — they change whether users trust and use the product.
- **A UI is a state machine.** Every interaction has idle/loading/error/success states; a frontend that only handles success is broken.

---

## Deliverable

**`Phase 1(AI)/STEP 29/step29-product/`**

- **`backend/main.py`** — FastAPI app with CORS enabled, a blocking `POST /ask`, and a streaming `POST /ask-stream` (raw text chunks) — heavily commented.
- **`frontend/Chat.jsx`** — a React component that posts a question and streams the answer back via `fetch` + `ReadableStream`, with explicit idle/loading/error/success states.

**Run it:** start the backend (`uvicorn main:app --reload`) and a Vite React app, then use `Chat.jsx` to stream an answer.

# Step 19: Production LLM Plumbing

> **What it covers:** Retries with exponential backoff and jitter, rate limits and request queuing, timeouts/circuit breakers/model fallbacks, token counting and cost accounting, idempotent retries of side-effecting calls, and provider abstraction via gateways — the difference between a demo that works in a notebook and a product that survives a Tuesday.

---

## The Problem

Every LLM call you've written since Step 15 is a network request to a third-party service that *will* fail on you: it rate-limits you at the worst moment, times out mid-stream, returns a 500 because the provider had an incident, or burns your budget because nobody was counting tokens. A demo can afford to crash when that happens; a product cannot.

Without this step's plumbing, you get the specific failure modes that kill real systems: a burst of 20 concurrent calls all hammering the API at once and triggering a 429, a retry loop that retries the *wrong* errors and makes the outage worse, a "fallback" that isn't wired up so a single provider outage takes your whole app down, and a bill that's 3x what you planned because you never measured cost per request. The skill isn't calling an LLM — it's calling it *reliably and affordably* when things are going wrong.

---

## Foundational Concepts

### The central insight: every LLM call is a network call

Once you stop thinking of `client.messages.create()` as "run the model" and start thinking of it as "send a request to a remote server over the internet," all of this chapter's machinery becomes obvious. Remote servers are slow, occasionally down, and shared by many customers. So you need the same tools a database or payment system needs: retry transient failures, limit your own load, time out when a response is hopeless, and account for what each call cost.

### Failure taxonomy: what you should *not* retry

This is the single most important mental model in the step, and it drives everything else. Failures split into three buckets:

| Class | Meaning | Retry? | Examples |
|---|---|---|---|
| **Transient** | The provider can likely succeed if you try again | Yes — with backoff | `429` (rate limit), `500`, `502`, `503`, `504`, network timeout, `ConnectionError` |
| **Permanent** | Retrying cannot help, and you'll get the same result every time | No — fail fast | `401` (bad key), `403` (permission), `404`, invalid request (`400`) |
| **Ambiguous** | The request may or may not have completed before the failure | Only with idempotency (19.5) | Timeout on a side-effecting tool call, connection dropped after send |

The classic beginner error is retrying everything. Retrying a `401` doesn't help — the key is wrong, and you'll just burn five more requests discovering the same fact. Retrying a `429` immediately doesn't help either — the provider is telling you to slow down, and hammering harder makes it worse.

### Idempotency: at-least-once vs. at-most-once

A retry turns a single logical operation into potentially *multiple* executions. That's fine when the operation is "generate text and send it back" — worst case you pay for two generations. It's a disaster when the operation is "send the email" or "deduct the payment," because a retry could send the email twice.

- **At-least-once** means "the operation ran one or more times" — safe for read-only operations, dangerous for side effects.
- **At-most-once** means "the operation ran zero or one times" — what you want for side effects, and it requires an **idempotency key**: a unique ID you generate per *logical* operation, so the receiving system can recognize "I've seen this request before" and skip the duplicate.

Retrying a pure text completion is at-least-once and mostly fine. Retrying a tool call that writes to a database is the place you *must* think about idempotency (Section 19.5).

### Token counts and cost are two separate things

Tokens are a unit of input/output size; cost is tokens × price. You can count tokens *before* a call (to estimate, to decide which model, to stay under a budget) and *after* a call (the provider tells you the exact `usage`). Price is per-token and differs wildly by model and provider — as of September 2026, hosted models are priced per 1M tokens (e.g., cheap models around $0.10–$0.50 per 1M input tokens, frontier models $3–$15 per 1M input and more on output), and it changes without notice, so hardcoding a price table is a bug.

---

## 19.1 — Retries, Exponential Backoff & Jitter

### The failure you're fixing

Your first version of "make it robust" looks like this:

```python
import time

def ask(client, prompt):
    for _ in range(5):
        try:
            return client.messages.create(model="claude-sonnet-5", messages=[{"role": "user", "content": prompt}])
        except Exception:
            time.sleep(2)          # fixed delay
    raise RuntimeError("failed")
```

This is better than nothing and wrong in two specific ways. First, `except Exception` catches *everything*, including the `401` that no amount of retrying will fix — you'd wait 10 seconds and fail slowly on a mistake you could have caught instantly. Second, a fixed 2-second delay means every one of your (say) 50 workers retries at exactly the same rhythm, so they all pile back onto the provider at the same instant — the **thundering herd** problem that can *cause* the next 429.

### Exponential backoff

The fix for the herd is to back off *exponentially*: each attempt waits longer than the last, so load spreads out over time.

```
attempt 1: fail → wait 2s
attempt 2: fail → wait 4s
attempt 3: fail → wait 8s
attempt 4: fail → wait 16s   (often capped)
```

The delay is `base × 2^attempt`, capped at a maximum. The idea is simple: if the service is overloaded, waiting longer gives it time to recover. But pure exponential backoff still has a flaw — if 50 workers all start at the same time, they all compute the *same* sequence of 2s, 4s, 8s, and stay synchronized forever. That's where jitter comes in.

### Jitter: randomness that breaks synchronization

**Jitter** is a random component added to each delay. The widely-cited recipe (from AWS's architecture guidance) is **full jitter**:

```python
import random

def backoff(attempt, base=2, cap=60):
    return random.uniform(0, min(cap, base * (2 ** attempt)))
```

Instead of everyone waiting exactly 4s, each worker waits a random amount between 0 and 4s. Some retry almost immediately, some wait the full 4s, and the load smears out across the interval instead of arriving in a synchronized spike.

### `tenacity`: the standard tool

You *could* hand-write the loop, but **tenacity** (the roadmap's linked library, Apache 2.0) is the standard Python way to express retry policy declaratively. It's a decorator that separates "when to retry," "how long to wait," and "when to stop" into three independent knobs:

```python
import random
from tenacity import (
    retry, retry_if_exception_type, stop_after_attempt,
    wait_exponential, RetryError,
)

def wait_with_jitter(multiplier=1, max_wait=30):
    # wait_exponential yields base * multiplier; we add full jitter on top
    return wait_exponential(multiplier=multiplier, max=max_wait) + wait_random(0, 2)
```

Let me walk through a real, minimal production-grade retry for an LLM call:

```python
import httpx
from tenacity import (
    retry, retry_if_exception_type, stop_after_attempt,
    wait_exponential, retry_if_exception, before_sleep_log,
)
import logging

logger = logging.getLogger(__name__)

# Retry ONLY on the errors that can succeed on a second try.
RETRYABLE = (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)

@retry(
    retry=retry_if_exception_type(RETRYABLE),
    stop=stop_after_attempt(4),                    # 1 initial + 3 retries
    wait=wait_exponential(multiplier=1, min=2, max=30),  # 2s, 4s, 8s, ... capped at 30s
    reraise=True,                                   # after 4 tries, raise the original error
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def call_llm(client, prompt):
    return client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
```

Reading the decorator line by line:

- `retry=retry_if_exception_type(RETRYABLE)` — the *retry predicate*. Only retry if the raised exception is a network-level error we expect to be transient. A `ValueError` or an SDK `AuthenticationError` (`401`) will *not* match, so it propagates immediately — no slow failure on a permanent error.
- `stop=stop_after_attempt(4)` — the *stop condition*. Four total attempts, then give up. Without a stop condition, tenacity's default is to retry *forever*, which is how you get a hung worker that never reports failure.
- `wait=wait_exponential(multiplier=1, min=2, max=30)` — the *wait strategy*. 2s, then 4s, 8s, 16s, then cap at 30s. Notice this has *no* jitter; adding it is the `+ wait_random(...)` trick, or use `wait_random_exponential` which randomizes the whole range.
- `reraise=True` — after exhausting retries, raise the *original* exception (the `TimeoutException`) rather than tenacity's wrapper `RetryError`. This matters: your caller's `except httpx.TimeoutException` should still catch what it expects.
- `before_sleep=before_sleep_log(...)` — a hook that logs "retrying in Xs" right before each nap, so a stuck request is visible in your logs (Step 14) instead of silent.

### What the SDKs already do for you — and what they don't

This is where most people get confused. The **OpenAI and Anthropic Python SDKs already retry** some failures by default: the OpenAI SDK retries up to 2 times on connection errors and on `429`/`5xx`, and honors the `Retry-After` header when the provider sends one. You can tune it via `max_retries` (both SDKs expose it) or disable it with `max_retries=0`.

So the real question is: *when do you need tenacity at all?*

| Situation | Use |
|---|---|
| You only use the SDK's `max_retries`, and the built-in policy is enough | Nothing extra |
| You need to retry *your own orchestration* — a pipeline that calls the SDK *and* writes to a DB, or a tool call, or a custom client | tenacity |
| You need to retry on a *specific* provider error, cap total time (not just attempts), or log each retry | tenacity |
| You're hitting an API that has no SDK (an internal proxy, a self-hosted vLLM endpoint) | tenacity |

The rule of thumb: the SDK retries are a floor, not a ceiling. The moment your retry logic has to span more than one API call — which is every real pipeline — you own it, and tenacity is how you express it.

---

## 19.2 — Rate Limits, Quotas & Request Queuing

### What a 429 actually means

A **rate limit** is the provider telling you "you're sending requests faster than your tier allows." Two distinct limits exist, and they cause different symptoms:

- **RPM** (requests per minute) — how many HTTP calls you can make.
- **TPM** (tokens per minute) — how many tokens flow through, in or out. You can hit TPM with *one* request if it's a huge document.

Both return HTTP `429 Too Many Requests`, and the response almost always carries a `Retry-After` header (either seconds or an HTTP date) telling you how long to wait. **Honoring `Retry-After` is the single most important rate-limit behavior** — it's the provider saying "wait this long and you'll be fine," and ignoring it and retrying immediately is how you get repeatedly 429'd.

### Backoff already handles single-request retries; queuing handles *concurrency*

Backoff (19.1) spaces out the *retries of one request*. But the more common production problem is *your* concurrency being too high: 50 async tasks (Step 18) all fire at once, and you blow through the RPM limit in the first second. Backoff alone doesn't fix that — you need to **limit how many requests are in flight at once**.

The tool is a **semaphore** — a counter that only lets N tasks proceed at a time and makes the rest wait:

```python
import asyncio

SEMAPHORE = asyncio.Semaphore(8)   # never more than 8 concurrent LLM calls

async def ask(client, prompt):
    async with SEMAPHORE:           # waits here if 8 are already running
        return await client.messages.create(
            model="claude-sonnet-5", max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
```

This is the async counterpart to the concurrency cap you'd do with threads, and it turns a burst of 100 requests into a smooth queue: 8 run, the rest wait, and as each finishes the next one starts. Combined with backoff-on-retry, this is how you stay *under* the rate limit instead of reacting to it after the fact.

### A request queue: when a semaphore isn't enough

A semaphore bounds concurrency but doesn't order or persist work. If you need more — retrying later, surviving a process restart, prioritizing some requests — you introduce an actual **queue** (Redis, Celery, an SQS topic, or the `asyncio.Queue` in-process). The pattern:

```
producer → queue → workers (each capped by a semaphore + backoff) → provider
```

The queue decouples "submitting work" from "doing work," so a spike doesn't hit the provider at all — it just sits in the queue until a worker is free. For a single-process tool you rarely need more than a semaphore; reach for a real queue when work has to outlive a process or be spread across machines.

### Quotas vs. rate limits

A **quota** is the *budget* — your plan allows X tokens/month, or your key is capped at $Y. Rate limits are the per-minute speed; quotas are the monthly ceiling. Both return `429` but the fix differs: a rate-limit 429 means "wait and retry," a quota-exceeded 429 means "you're done until you pay or the month rolls over — retrying is pointless." In practice, you distinguish them by the error message/code, and quota exhaustion is one of the few `429`s you should *not* hammer with backoff forever.

---

## 19.3 — Timeouts, Circuit Breakers & Model Fallbacks

### Timeouts: don't wait forever

A hung request holds a worker hostage. If the provider is slow (or down, and the failure manifests as silence rather than an error), your caller blocks indefinitely, and with enough of them your whole pipeline freezes. Every LLM call needs a timeout:

```python
# Anthropic — timeout in seconds on the client
client = anthropic.Anthropic(timeout=30.0)

# OpenAI — timeout on the client or per-call
client = openai.OpenAI(timeout=30.0)
response = client.chat.completions.create(..., timeout=30.0)
```

The subtlety: a timeout on the *connect* is different from a timeout on the *read*. Connecting should be fast (seconds); reading a full response should be much longer (a big generation can legitimately take minutes). The SDKs let you pass a `httpx.Timeout` object for fine-grained control:

```python
import httpx
client = openai.OpenAI(
    timeout=httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)
)
```

`read` is the one that matters most for LLMs — it's how long you'll wait for the model to finish generating. Set `read` to comfortably exceed your slowest expected generation; set `connect` short so a dead provider fails fast.

### Circuit breakers: stop sending requests to something that's down

Retries and backoff assume the service will recover. A **circuit breaker** assumes it might *not*, and protects you from repeatedly waiting through timeouts when the provider has been down for 20 minutes. The pattern, borrowed from electrical engineering:

```
        closed ──(too many failures)──> open ──(cooldown elapsed)──> half-open
          ▲                                                             │
          └────────────────(success)───────────────────────────────────┘
```

- **Closed** — normal state. Requests flow through; failures are counted.
- **Open** — after N failures in a window, the breaker trips. Requests now fail *immediately* (no network call, no 30-second timeout) — a "fast fail" that lets the rest of your system degrade gracefully instead of piling up.
- **Half-open** — after a cooldown, the breaker lets one trial request through. If it succeeds, back to closed. If it fails, back to open.

Here's a minimal one (this is the kind of thing that's worth writing once and reusing):

```python
import time
from enum import Enum

class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold=5, cooldown=60):
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self.state = State.CLOSED
        self.failures = 0
        self.opened_at = 0

    def call(self, fn):
        if self.state == State.OPEN:
            if time.monotonic() - self.opened_at >= self.cooldown:
                self.state = State.HALF_OPEN          # allow one trial
            else:
                raise CircuitOpenError("provider marked down")
        try:
            result = fn()
        except Exception:
            self._record_failure()
            raise
        self._record_success()
        return result

    def _record_failure(self):
        self.failures += 1
        if self.state == State.HALF_OPEN or self.failures >= self.failure_threshold:
            self.state = State.OPEN
            self.opened_at = time.monotonic()

    def _record_success(self):
        self.failures = 0
        self.state = State.CLOSED
```

The key judgment: a circuit breaker wraps the *provider* (or a specific model deployment), and its `call` is what you invoke instead of calling the client directly. Combine it with tenacity so that *within* the closed state you still retry transient errors, but once the breaker opens you stop trying altogether for a while.

### Model fallbacks: when one model is down, use another

A **fallback** is a list of models to try in order. If the primary fails (or times out, or trips the breaker), you transparently try the next. This is how you survive a provider outage without your users noticing:

```python
FALLBACKS = [
    {"provider": "anthropic", "model": "claude-sonnet-5"},
    {"provider": "openai",   "model": "gpt-4o"},
    {"provider": "anthropic", "model": "claude-haiku-4-5"},   # cheaper, lower quality
]

def ask_with_fallback(prompt):
    last_err = None
    for cfg in FALLBACKS:
        try:
            return call_model(cfg, prompt)
        except (TransientError, TimeoutError) as e:
            last_err = e
            continue    # try the next one
    raise last_err
```

Two decisions worth being explicit about:

- **Quality can degrade down the chain.** A fallback from `claude-sonnet-5` to `claude-haiku-4-5` is not free — the cheaper model may be worse. Log which model actually served each request (Step 14) so you can see if you're silently serving lower-quality output.
- **Fallback vs. circuit breaker are complementary.** The breaker stops you hammering a dead primary; the fallback redirects traffic while it's open. Together: breaker trips on the primary → request goes to the fallback → after cooldown, half-open probes the primary.

LiteLLM's `Router` (Section 19.6) gives you this for free with a `fallbacks` list, but understanding the pattern matters because you'll debug it when the fallback chain does something surprising.

---

## 19.4 — Token Counting & Per-Request Cost Accounting

### Why you count tokens

You can't control a budget you can't measure. Token counting answers three practical questions: *will this fit* in the model's context window (Step 35), *how much will this cost*, and *which model should I route this to*. Two of those are pre-call estimates, one is post-call accounting, and they use different tools.

### Post-call: the provider already tells you

Every response includes a `usage` object with the exact token counts. This is ground truth — always record it:

```python
# Anthropic
response = client.messages.create(...)
print(response.usage.input_tokens, response.usage.output_tokens)

# OpenAI
response = client.chat.completions.create(...)
print(response.usage.prompt_tokens, response.usage.completion_tokens)
```

With those two numbers, cost is one multiplication each way:

```python
input_cost  = input_tokens  / 1_000_000 * INPUT_PRICE_PER_1M
output_cost = output_tokens / 1_000_000 * OUTPUT_PRICE_PER_1M
total = input_cost + output_cost
```

### Pre-call: estimating before you spend

Sometimes you need to know the cost *before* sending (e.g., to route a big request to a cheaper model, or to reject a request that would blow the budget). Two approaches:

**Anthropic has a dedicated endpoint** — `count_tokens` — which returns the exact count without running the model:

```python
count = client.messages.count_tokens(
    model="claude-sonnet-5",
    messages=[{"role": "user", "content": "..."}],
)
print(count.input_tokens)
```

**OpenAI's `tiktoken`** library counts locally (no API call, offline, free), using a model's tokenizer:

```python
import tiktoken

enc = tiktoken.encoding_for_model("gpt-4o")
n_tokens = len(enc.encode("your text here"))
```

The caveat that catches people: **different models use different tokenizers**, so a token count for `gpt-4o` is *not* the same as for `claude-sonnet-5` for the same text. If you're routing across providers, use each provider's own counter — or LiteLLM's, which abstracts this.

### LiteLLM unifies counting and cost

Rather than hand-maintaining a price table (which, again, changes), LiteLLM exposes helpers that know each model's tokenizer *and* current price:

```python
from litellm import token_counter, completion_cost

# Count tokens for a specific model's tokenizer
n = token_counter(model="gpt-4o", messages=messages)

# Cost of an actual completed call
response = completion(model="anthropic/claude-sonnet-5", messages=messages)
cost = completion_cost(completion_response=response)
```

`completion_cost` reads the response's `usage` and multiplies against a community-maintained price list — so your cost numbers stay current without you tracking provider pricing by hand. For self-hosted models (Step 82) you register your own cost map.

### Accounting vs. estimation — don't conflate them

| | Pre-call estimate | Post-call accounting |
|---|---|---|
| **Purpose** | Route, budget-gate, warn | Bill, track, alert |
| **Tool** | `count_tokens`, `tiktoken`, `token_counter` | `response.usage` |
| **Precision** | Approximation (tokenizer differences) | Exact (provider-reported) |
| **Use** | "This request is huge, use the cheap model" | "This month we spent $412 on output tokens" |

The two together give you a real cost pipeline: estimate to make routing decisions, then *record* the actual cost on every call so a month later you can explain the bill — which is the whole "a bill you can explain" idea from the roadmap.

---

## 19.5 — Idempotency & Safe Retry of Side-Effecting Calls

### The specific danger

A retry (19.1) re-executes your function. For a text completion that's harmless-ish. But once your LLM calls are wrapped in a loop that *executes tools* (Step 32) — sending an email, writing a DB row, charging a card — a retry can execute the side effect twice. A timeout is the classic trigger: the provider *might* have completed the call before the connection dropped, so you genuinely don't know whether the email went out, and retrying "to be safe" sends it again.

### What idempotency means

An operation is **idempotent** if running it twice has the same effect as running it once. `SET user.email = 'x'` is idempotent (running it twice leaves 'x'); `INSERT INTO emails ...` is not (two rows); "send this email" is not (two emails).

The standard mechanism is an **idempotency key**: a unique ID your system generates for each *logical* operation, attached to the request, so the receiver can deduplicate. The flow:

```
1. Generate a key (UUID) for this logical operation, e.g. request_id = uuid4()
2. Send the request with the key attached
3. Receiver stores key → result
4. If the same key arrives again, return the stored result instead of re-executing
```

```python
import uuid
import hashlib

def send_email_idempotent(to, subject, body, dedupe_store):
    # The key is deterministic per logical operation — same (to, subject, body)
    # means "same email", so a retry reuses the same key and is deduped.
    key = hashlib.sha256(f"{to}|{subject}|{body}".encode()).hexdigest()

    if dedupe_store.get(key):
        return dedupe_store.get(key)     # already sent, return stored result
    result = actually_send_email(to, subject, body)
    dedupe_store.set(key, result)
    return result
```

The crucial design point: the key must be **deterministic per logical operation**, not a fresh UUID per attempt. If you generate a new UUID on each retry, the receiver sees a *different* key and can't dedupe — which defeats the entire purpose.

### Where the LLM world stands (as of September 2026)

OpenAI and Anthropic do **not** currently expose a general `Idempotency-Key` header on their chat/completions endpoints the way Stripe-style APIs do. So for the LLM call *itself*, you can't rely on provider-side dedupe — retrying a text generation is at-least-once (you might get billed twice if the first attempt actually completed but the response was lost, though in practice that's rare and cheap).

The idempotency problem really lives in *your* side-effecting tools, not in the model call. The rule:

- **Read-only LLM calls** (generate text, classify, summarize) — retry freely; at-least-once is fine.
- **Side-effecting tool calls** (write, send, charge) — make the *tool* idempotent with a key, then retry the whole loop safely.

This is also why Step 39's guardrail of "least-privilege tools + human approval gates" matters: a tool that can only do one idempotent thing is far easier to make retry-safe than a general-purpose "run arbitrary code" tool.

---

## 19.6 — Provider Abstraction & Gateways (LiteLLM, OpenRouter)

### The problem abstraction solves

You wrote against Anthropic's SDK in Step 15. Now you want to try OpenAI, or a cheap open model on Bedrock, or swap the primary for a fallback when it's down. Each provider has its own SDK, its own message format, its own error types, its own way of reporting tokens. If you call them directly, swapping models means rewriting your app — the exact coupling this step exists to remove.

The fix is an **abstraction layer**: a single interface you call, with providers plugged in underneath. Two levels exist:

| Level | What it is | When to use |
|---|---|---|
| **SDK abstraction (LiteLLM)** | A Python library with one `completion()` function that talks to 100+ providers | You're building the app, want to swap models in code |
| **Gateway (LiteLLM Proxy, OpenRouter)** | A *separate service* that fronts many providers behind one OpenAI-compatible URL | Multiple apps/teams share model access; centralize keys, budgets, logging |

### LiteLLM: one interface, many providers

**LiteLLM** is the de facto open-source standard for this. You call one function and name the provider in the model string; everything else — message format, error mapping, token/cost reporting — is normalized to the OpenAI shape:

```python
from litellm import completion

# Same call, four different providers — your code doesn't change
completion(model="anthropic/claude-sonnet-5", messages=messages)
completion(model="openai/gpt-4o", messages=messages)
completion(model="bedrock/anthropic.claude-haiku-4-5-20251001:0", messages=messages)
completion(model="ollama/llama3", messages=messages, api_base="http://localhost:11434")
```

It maps every provider's errors to a single exception hierarchy, so your error handling is provider-agnostic:

```python
import litellm

try:
    completion(model="anthropic/claude-sonnet-5", messages=messages)
except litellm.AuthenticationError as e:   # 401 across any provider
    ...
except litellm.RateLimitError as e:        # 429 across any provider
    ...
except litellm.APIError as e:              # 5xx across any provider
    ...
```

And it folds the whole chapter into one `Router` — retries, fallbacks, and load balancing:

```python
from litellm import Router

router = Router(
    model_list=[
        {"model_name": "primary", "litellm_params": {"model": "anthropic/claude-sonnet-5"}},
        {"model_name": "fallback", "litellm_params": {"model": "openai/gpt-4o"}},
    ],
    fallbacks=[{"primary": ["fallback"]}],   # try fallback if primary fails
    num_retries=3,                           # built-in retries
    timeout=30,
)
response = router.completion(model="primary", messages=messages)
```

This doesn't mean you skip understanding 19.1–19.5 — when the router's behavior surprises you (and it will), you need the mental models to debug it. It means you don't *reimplement* those patterns for every project.

### OpenRouter and the gateway model

**OpenRouter** is a *hosted* gateway: one API key, one endpoint, access to hundreds of models (hosted and open) with unified pricing and usage. It's the "buy" alternative to LiteLLM Proxy's "build." The trade-off: you hand a third party your traffic and pay their margin, in exchange for never maintaining the routing layer yourself.

### The honest caveat: abstraction has a cost

LiteLLM normalizes 100+ providers to one interface — which means it necessarily hides the differences that make providers distinct (Anthropic's content blocks vs. OpenAI's strings, from Step 15; different tool-call formats from Step 32). When you need a provider-specific feature, or when the abstraction misbehaves, you read the layer's source (a skill Step 27 makes explicit) rather than fighting it. The rule of thumb: **abstract at the seam where you actually expect to swap.** If you're certain you'll only ever use one provider, calling its SDK directly is simpler and you can add LiteLLM later; the moment you want fallbacks, cost-normalized reporting, or "maybe I'll swap models," the abstraction earns its keep.

---

## Pitfalls

1. **Retrying everything.** `except Exception: retry` turns a `401` (permanent) into a slow, expensive failure. Retry only transient errors, and let permanent ones fail fast.
2. **Ignoring `Retry-After`.** The 429 response tells you exactly how long to wait. Retrying immediately instead is how a single rate limit becomes a sustained outage.
3. **No jitter.** Pure exponential backoff with many concurrent workers keeps them synchronized — they all retry at the same instant and re-trigger the problem. Add randomness.
4. **Retrying side-effecting tool calls without idempotency.** A timeout on "send email" + an automatic retry = duplicate emails. Make side effects idempotent (19.5) *before* you make them retryable.
5. **No timeout on the client.** A hung provider blocks your worker forever; set `connect` short and `read` long enough for your slowest real generation.
6. **Confusing retry count with attempts.** `stop_after_attempt(3)` means 3 *total* attempts, not 3 *retries*. Off-by-one here makes you give up one retry early.
7. **Hardcoding a price table.** Token prices change without notice. Use the provider's `usage` for actuals and LiteLLM's price list (or a dated, updatable config) for estimates — don't bake "$0.003/1K" into code.
8. **Token-counting with the wrong tokenizer.** `tiktoken` on `gpt-4o` doesn't give the count for `claude-sonnet-5`. Count per provider, or use a layer that does.
9. **Confusing the queue with the semaphore.** A semaphore bounds concurrency but doesn't persist or order work; if you need "retry this later, across restarts," you need a real queue, not a bigger semaphore.
10. **Assuming fallbacks are free.** Falling back from a frontier model to a cheap model silently degrades quality. Log which model served each request, or you'll never know.

---

## Quick Reference

| Concept | Key point |
|---|---|
| **Transient vs. permanent errors** | Retry 429/5xx/timeouts; fail fast on 401/403/400 |
| **Exponential backoff** | Delay = `base × 2^attempt`, capped; spreads load over time |
| **Jitter** | Random component (e.g. full jitter) that breaks synchronized retries |
| **tenacity** | `@retry(retry=..., stop=..., wait=..., reraise=True)` — declarative retry policy |
| **`reraise=True`** | Re-raise the original error after retries, not tenacity's `RetryError` |
| **SDK built-in retries** | OpenAI/Anthropic SDKs retry some 429/5xx by default; tune via `max_retries` |
| **RPM / TPM** | Requests-per-minute and tokens-per-minute; both return 429 |
| **`Retry-After`** | Header telling you how long to wait; honor it |
| **Semaphore** | Caps concurrent in-flight calls (e.g. `asyncio.Semaphore(8)`) |
| **Request queue** | Decouples submit from execute; persists work across spikes/restarts |
| **Quota vs. rate limit** | Quota = monthly budget (retry pointless); rate limit = per-minute speed (retry with wait) |
| **Timeout** | Set `connect` short, `read` long; every call needs one |
| **Circuit breaker** | closed → open → half-open; fast-fails when a provider is down |
| **Model fallback** | Ordered list of models to try; log which one actually served |
| **`count_tokens` / `tiktoken`** | Anthropic endpoint and OpenAI local counter for pre-call estimates |
| **`response.usage`** | Exact post-call token counts — always record it |
| **Cost formula** | `tokens / 1M × price_per_1M`, input and output separately |
| **LiteLLM helpers** | `token_counter`, `completion_cost` — normalized across providers |
| **Idempotency key** | Deterministic key per *logical* operation; receiver dedupes |
| **At-least-once vs at-most-once** | Text gen = at-least-once (fine); side effects = at-most-once (needs key) |
| **LiteLLM `completion()`** | One interface, 100+ providers, OpenAI-normalized errors/usage |
| **LiteLLM `Router`** | Retries + fallbacks + load balancing in one object |
| **OpenRouter** | Hosted gateway: one key, many models, unified pricing |

---

## Theory Summary

**Treat the LLM API like any other remote system.** The moment you stop seeing `client.messages.create()` as "magic that returns text" and start seeing it as a network call to a shared, occasionally-down service, all of this becomes ordinary distributed-systems practice. Retries, timeouts, circuit breakers, and rate limiting aren't LLM-specific — they're what every database driver and payment library already does, applied to a provider that just happens to also bill by the token.

**Classify the failure before you decide what to do.** Every error is transient, permanent, or ambiguous, and that classification *fully determines* the correct response: back off and retry, fail fast, or check idempotency. Most of the bugs in this space come from applying one response to the wrong class — usually "retry" applied to everything.

**Backoff is about protecting the *provider*, not just waiting politely.** Exponential backoff and jitter exist so that an overloaded service isn't hit by a synchronized wall of retries from every customer at once. You're not just making your own code more patient; you're participating correctly in a shared system where everyone's behavior affects everyone else's reliability.

**Concurrency and retry are two different levers.** A semaphore/queue controls how many requests you *start*; backoff controls how you *space the repeats of one request*. Rate limits are violated by the first lever (too much concurrency) and recovered by the second (backoff + honoring `Retry-After`). Production systems need both.

**A circuit breaker is a bet that "down" is not "temporarily slow."** Retries assume recovery within seconds; a breaker assumes it might be minutes and refuses to keep paying the timeout cost. The half-open probe is how you reconcile the two — you stop trusting the provider, but leave a door open to check whether it's back.

**Cost is tokens × price, and price is someone else's mutable data.** Record actual `usage` from every response as ground truth, and treat any price you hardcode as a stale snapshot. The accounting pipeline — estimate before to route, record after to bill — is what turns "the bill is a surprise" into "here's exactly why we spent this."

**Abstraction trades provider-specific control for swap-ability.** LiteLLM and gateways give you fallbacks, unified errors, and normalized cost at the price of hiding provider differences. The right boundary is "where do I actually expect to swap?" — abstract there, and no further, or you'll be debugging the abstraction more than the provider.

**Idempotency is a property of the *side effect*, not the retry.** You don't make retries safe by being clever with the retry loop; you make them safe by designing each side-effecting tool so that running it twice is harmless, then attaching a deterministic key so the receiver can recognize the duplicate.

---

## Deliverable

**`Phase 1(AI)/step19-plumbing/`** — a reusable resilience module plus a provider-abstraction demo, built to drop into Project 1 and every later project that calls an LLM:

- **`resilience.py`** — the four patterns, each small and dependency-light:
  - `@llm_retry` — a tenacity-based decorator that retries only transient errors (timeouts, connection errors, `429`/`5xx`), uses `wait_exponential + jitter`, caps attempts, and re-raises the original exception. Takes `max_attempts` and `max_wait` as arguments.
  - `CircuitBreaker` — the class from Section 19.3 (closed/open/half-open with `failure_threshold` and `cooldown`), raising `CircuitOpenError` when open.
  - `RateLimiter` — an `asyncio.Semaphore` wrapper exposing `async with limiter:` to cap concurrency, plus a helper that parses `Retry-After` from a response and sleeps accordingly.
  - `count_and_cost` — takes a provider, model, and messages; returns `(input_tokens, output_tokens, estimated_cost)` using `count_tokens`/`tiktoken` for pre-call estimates and `response.usage` for post-call actuals, with the price table in a single dated `prices.py` constant (not scattered inline).
- **`provider.py`** — a thin LiteLLM wrapper exposing `ask(model, messages, fallbacks=...)` that uses `Router` with fallbacks, `num_retries`, and a timeout, and logs which model actually served each request.
- **`idempotent_tool.py`** — a demo side-effecting tool (e.g., `write_row`) wrapped with a deterministic idempotency key and an in-memory dedupe store, showing that a retried call produces one row, not two.
- **`test_resilience.py`** — pytest tests (Step 13) covering: transient errors are retried and permanent errors are not (using a `Mock` client), the circuit breaker opens after N failures and lets a trial request through in half-open, the semaphore never exceeds its concurrency cap, and the idempotent tool dedupes a duplicate key. No live network calls.

**Prove it:** write a small script that points `ask()` at a deliberately flaky fake client (raises `TimeoutError` twice, then succeeds), run it with and without the breaker, and show the fallback engaging when the primary "fails" — then run `pytest -v` green.

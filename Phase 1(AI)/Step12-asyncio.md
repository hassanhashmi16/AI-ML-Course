# Step 12: asyncio

> **What it covers:** async/await syntax, asyncio.gather, the event loop concept, and when NOT to use async — running multiple LLM calls at once instead of waiting one by one.

---

## Foundational Concepts

### What is concurrency?

**Concurrency** is the ability to handle multiple tasks that start, run, and complete in overlapping time periods — not necessarily at the exact same instant. Think of a single chef cooking three dishes: they don't cook all three simultaneously. They chop vegetables for dish A, put it in the oven, then while it bakes, they start chopping for dish B. Tasks make progress in overlapping chunks.

**Parallelism** (doing multiple things at the exact same time) requires multiple CPU cores. Concurrency only requires smart scheduling of a single worker.

### The problem: I/O-bound work is mostly waiting

Your Python code spends a lot of time waiting for things that are not the CPU:
- Waiting for an HTTP response (LLM API call)
- Waiting for a database query
- Waiting for a file to be read from disk

These are called **I/O-bound** tasks — dominated by input/output time rather than computation time. During that waiting, your CPU is idle. If you make three LLM API calls synchronously, the timeline looks like:

```
send call 1 → wait 3s → get response
               → send call 2 → wait 3s → get response
                                → send call 3 → wait 3s → get response
Total: ~9 seconds
```

With async, while waiting for call 1's response, you can send call 2 and call 3:

```
send call 1 → wait 3s → get response
send call 2 → wait 3s → get response
send call 3 → wait 3s → get response
Total: ~3 seconds
```

The CPU is doing the same amount of work. You just stopped sitting idle.

### The chess analogy

This is the classic explanation from Miguel Grinberg's PyCon talk:

Chess master Judit Polgár plays 24 amateur players simultaneously.
- **Synchronously:** She plays one game to completion, then the next. Each game takes 30 minutes. Total: 12 hours.
- **Asynchronously:** She makes one move at table 1, then moves to table 2, makes one move, then table 3, etc. While she's at table 3, the opponent at table 1 is thinking about their response. Total: 1 hour.

There's still only one Judit making one move at a time. She just doesn't sit idle waiting for opponents to think. Async I/O is the same: the event loop makes a move (starts an I/O operation), then immediately goes to the next task while waiting for the result.

### How Python does async: cooperative multitasking

Python's async model is **cooperative**, not preemptive. This means:
- A task runs until it *voluntarily* yields control by using `await`.
- No task can be interrupted mid-computation by another task.
- This is different from threading, where the OS can interrupt any thread at any instruction.

This is why you must explicitly `await` — it's the signal that says "I'm about to wait for something, go do something else in the meantime."

### Three concurrency models compared

| Model | Good for | How it works | Overhead |
|---|---|---|---|
| **Async I/O** (asyncio) | I/O-bound, many concurrent tasks | Single thread, tasks yield with `await` | Very low |
| **Threading** | I/O-bound, moderate tasks | Multiple threads, OS scheduling | Medium |
| **Multiprocessing** | CPU-bound tasks | Multiple processes, separate memory | High |

For AI Engineering, async is almost always the right choice because:
- You're making network calls (I/O-bound).
- You might want hundreds of concurrent LLM calls.
- The GIL doesn't affect async at all (single thread).

---

## 12.1 — async / await Syntax

### The two keywords

- **`async def`** — defines a **coroutine function**. Calling it returns a **coroutine object**, which doesn't do anything until you schedule it on an event loop.
- **`await`** — suspends the current coroutine and passes control back to the event loop. The event loop can run other tasks while waiting.

### A coroutine does nothing on its own

```python
import asyncio

async def say_hello():
    print("Hello")
    await asyncio.sleep(1)
    print("World")

result = say_hello()       # returns a coroutine object, does NOT run
print(result)               # <coroutine object say_hello at ...>
```

There are only three ways to actually run a coroutine:

1. **`asyncio.run()`** — run a top-level coroutine
2. **`await` it** from within another coroutine
3. **`asyncio.create_task()`** — schedule it for concurrent execution

### The basic pattern

```python
import asyncio

async def main():
    print("Hello...")
    await asyncio.sleep(1)
    print("World!")

asyncio.run(main())
```

`asyncio.run(main())` does three things: creates the event loop, runs `main()` until it completes, then closes the loop. You should only call `asyncio.run()` once in your program.

### The key thing to understand about `await`

There are two completely different scenarios, and confusing them is what causes the "does await block or not?" question.

**Scenario 1: Sequential (two separate `await` lines)**

```python
result_a = await task_a()   # pauses here until task_a finishes
result_b = await task_b()   # then starts task_b
```

This IS sequential. `task_b` does NOT start until `task_a` is 100% done. Same as writing `await a` then `await b` in JavaScript.

**Scenario 2: Concurrent (gather or create_task)**

```python
task_a_obj = asyncio.create_task(task_a())  # starts running NOW
task_b_obj = asyncio.create_task(task_b())  # starts running NOW
# Both are now running in the background
await task_a_obj   # wait for a to finish
await task_b_obj   # wait for b to finish
```

Now both run at the same time. Same as `Promise.all()` in JavaScript.

**So `await` itself always does the same thing:** it pauses the current coroutine until the thing you're awaiting finishes. The key is: if you started the other tasks BEFORE the await (using `create_task` or `gather`), they're already running in the background. If you didn't, nothing else runs.

### The mental model: like a coffee shop

You're at a coffee shop counter. You order a latte and step aside.

- **`await` = you step aside and wait for your drink.** The barista can serve other customers while you wait. *But* — if you ordered *after* stepping aside, and no one else is in line, you just stand there.
- **`create_task` = you order, then immediately call your friend and tell them to order too.** Now both drinks are being made concurrently. When you `await` your drink, yours might be ready, or your friend's might be ready first.

So whether things run in parallel depends on whether you *started* them before the `await`, not on the `await` itself.

### Concrete example: sequential vs concurrent in Python

**Sequential (takes ~4 seconds total):**

```python
import asyncio

async def fetch(url: str, delay: int):
    print(f"Starting {url}")
    await asyncio.sleep(delay)      # simulate network call
    print(f"Done {url}")
    return f"data from {url}"

async def main():
    r1 = await fetch("api1.com", 2)  # START → wait 2s → DONE
    r2 = await fetch("api2.com", 2)  #          then START → wait 2s → DONE
    print(r1, r2)

asyncio.run(main())
# Starting api1.com    (t=0s)
# Done api1.com        (t=2s)
# Starting api2.com    (t=2s)
# Done api2.com        (t=4s)
```

Same as `const r1 = await fetchA(); const r2 = await fetchB();` in JS.

**Concurrent (takes ~2 seconds total):**

```python
async def main():
    # Start both tasks NOW — they run in the background
    t1 = asyncio.create_task(fetch("api1.com", 2))
    t2 = asyncio.create_task(fetch("api2.com", 2))

    # Now wait for both to finish
    r1 = await t1
    r2 = await t2
    print(r1, r2)

asyncio.run(main())
# Starting api1.com    (t=0s)
# Starting api2.com    (t=0s)  ← both started before any await!
# Done api1.com        (t=2s)
# Done api2.com        (t=2s)
```

Same as `const [r1, r2] = await Promise.all([fetchA(), fetchB()])` in JS.

Or use `gather` which does the same thing:

```python
async def main():
    r1, r2 = await asyncio.gather(
        fetch("api1.com", 2),
        fetch("api2.com", 2),
    )
    print(r1, r2)
```

### What `await` does internally in Python

When Python runs `await some_coro()`:

1. The current coroutine is **suspended** at this exact line.
2. Control returns to the **event loop**.
3. The event loop checks: "are there any other coroutines or tasks that are ready to run?"
4. If yes → runs one of them.
5. If no → just waits until the thing we're awaiting finishes.
6. When it finishes → the event loop resumes the suspended coroutine at the line after the `await`.

So `await` is NOT "block everything until done." It's "**I specifically can't move forward until this is done, but you (the event loop) can do other things while I wait.**"

But if there are no other things to do (because you didn't start any other tasks), the event loop just sits there too.

### Rules of async/await

- `await` can only be used **inside** an `async def` function.
- `await` outside `async def` raises `SyntaxError`.
- `async def` functions cannot use `yield from` (raises `SyntaxError`).
- Calling a coroutine function does NOT execute it — you must `await` it or schedule it.

---

## 12.2 — asyncio.gather

### Running multiple coroutines concurrently

`asyncio.gather()` takes multiple awaitables and runs them concurrently. It waits for ALL of them to complete and returns a list of their results in the same order they were passed.

```python
import asyncio

async def fetch_data(user_id: int) -> dict:
    print(f"Fetching user {user_id}...")
    await asyncio.sleep(2)          # simulate API call
    return {"id": user_id, "name": f"User{user_id}"}

async def main():
    results = await asyncio.gather(
        fetch_data(1),
        fetch_data(2),
        fetch_data(3),
    )
    print(results)
    # [{'id': 1, 'name': 'User1'}, {'id': 2, 'name': 'User2'}, {'id': 3, 'name': 'User3'}]

asyncio.run(main())
# All three calls run concurrently — takes ~2s total, not ~6s
```

### The order is preserved

`gather()` returns results in the same order as the input, regardless of which finishes first. So `results[0]` corresponds to `fetch_data(1)`, even if `fetch_data(2)` finished first.

### Error handling with gather

```python
async def good():
    await asyncio.sleep(1)
    return "ok"

async def bad():
    await asyncio.sleep(0.5)
    raise ValueError("something went wrong")

async def main():
    # Default: first exception propagates immediately
    results = await asyncio.gather(good(), bad())
    # This raises ValueError after 0.5s
```

With `return_exceptions=True`, exceptions are returned as values instead of being raised:

```python
async def main():
    results = await asyncio.gather(good(), bad(), return_exceptions=True)
    print(results)
    # ["ok", ValueError("something went wrong")]
    # You can check which ones are exceptions
    for r in results:
        if isinstance(r, Exception):
            print(f"Task failed: {r}")
```

### gather vs. create_task

```python
async def main():
    # Option 1: gather (simpler)
    results = await asyncio.gather(task1(), task2())

    # Option 2: create_task (more control)
    t1 = asyncio.create_task(task1())
    t2 = asyncio.create_task(task2())
    result1 = await t1
    result2 = await t2
```

Use `create_task()` when you need to:
- Start a task but await it later
- Cancel individual tasks
- Track task state (`task.done()`, `task.cancelled()`)

### The AI Engineering use case

```python
import asyncio
import anthropic

client = anthropic.Anthropic()

async def ask_llm(prompt: str) -> str:
    response = client.messages.create(  # Note: this is sync
        model="claude-sonnet-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text

# If using the sync SDK, wrap in asyncio.to_thread
async def ask_llm_async(prompt: str) -> str:
    return await asyncio.to_thread(ask_llm, prompt)

async def main():
    prompts = [
        "Summarize this document...",
        "Extract key entities...",
        "Generate three questions...",
    ]
    results = await asyncio.gather(
        *(ask_llm_async(p) for p in prompts)
    )
    print(results)
```

**Important:** The Anthropic and OpenAI Python SDKs have both sync and async clients. Use `async def` versions when available:

```python
import anthropic

client = anthropic.AsyncAnthropic()  # Note: AsyncAnthropic, not Anthropic

async def ask_llm(prompt: str) -> str:
    response = await client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
```

Similarly, OpenAI has `AsyncOpenAI()`.

---

## 12.3 — The Event Loop Concept

### What is the event loop?

The **event loop** is the core of asyncio — an infinite loop that:
1. Checks which tasks are ready to run.
2. Runs them one at a time until they hit an `await`.
3. Suspends them and moves to the next ready task.
4. When a task's awaited operation completes, it marks that task as ready.
5. Repeats until all tasks are done.

You never interact with it directly — `asyncio.run()` handles it for you. But understanding it explains *why* async works the way it does.

### The event loop in detail

```
Event loop iteration:
1. Look at all scheduled tasks.
2. Pick one that's ready (not waiting on anything).
3. Run it until it hits `await`.
4. When await is reached, the task says "I'm waiting for X."
5. The loop suspends that task and goes back to step 1.
6. When X completes (e.g., network response arrives), the task moves back to "ready."
```

This is why `await` is required — it's the only way a task can tell the loop "I'm done for now, run something else."

### Getting the running loop (rarely needed)

```python
loop = asyncio.get_running_loop()
```

Useful when you need to schedule a callback or check `loop.time()` for timeouts, but in most code you never call this.

### Default event loop implementations

| Platform | Default | Notes |
|---|---|---|
| Linux/macOS | `SelectorEventLoop` | Uses `select`/`epoll`/`kqueue` |
| Windows | `ProactorEventLoop` | Uses I/O completion ports |

You can swap implementations (e.g., `uvloop` which is faster), but the default is fine for most use cases.

### How create_task works internally

```python
task = asyncio.create_task(some_coro())
```

This wraps the coroutine in a `Task` object and registers it with the event loop. The task is now scheduled to run. It will execute as soon as the event loop gets a chance, but NOT immediately — only on the next iteration where no other task is actively running.

This is why you sometimes need `await asyncio.sleep(0)` — it yields control and lets other scheduled tasks run.

---

## 12.4 — When NOT to Use Async

### CPU-bound work blocks the event loop

If you run a CPU-heavy operation inside a coroutine, it blocks the **entire event loop** — no other tasks can run until it finishes.

```python
import asyncio

async def bad():
    # This blocks EVERYTHING for 5 seconds
    total = sum(range(10_000_000))
    return total

async def main():
    # These won't run concurrently because bad() doesn't yield
    results = await asyncio.gather(bad(), bad(), bad())
```

**Solution:** Use `asyncio.to_thread()` to offload CPU work to a thread:

```python
import asyncio

def cpu_heavy(n):
    return sum(range(n))

async def good():
    return await asyncio.to_thread(cpu_heavy, 10_000_000)
```

### Sync I/O (like time.sleep) blocks the event loop

```python
import time

async def wrong():
    time.sleep(1)         # BLOCKS event loop — nothing else runs
    print("Done")

async def right():
    await asyncio.sleep(1) # YIELDS — other tasks can run
    print("Done")
```

Always use `await asyncio.sleep()` instead of `time.sleep()` in async code. Similarly, use async libraries for file I/O (`aiofiles`), HTTP (`aiohttp`, `httpx`), and database access.

### When async gives you nothing

Async does not help when:
- **Your program is sequential by nature.** If step B depends on step A's result, and step C depends on step B's result, async adds complexity with zero benefit.
- **You only have one I/O operation.** A single `await` with nothing else to run concurrently is just overhead.
- **The task is CPU-bound.** Async doesn't make your CPU faster. For CPU-heavy work, use multiprocessing.

### The decision tree

```
Is your code mostly waiting on I/O (network, disk, database)?
├── Yes → Is there only ONE operation at a time?
│         ├── Yes → Async not needed. Just write sync code.
│         └── No → Async is a good fit.
└── No (CPU-bound) → Async will NOT help.
                      ├── Use threading for light CPU work
                      └── Use multiprocessing for heavy CPU work
```

### Async adds cognitive overhead

Async code is harder to debug, harder to reason about, and harder to profile than synchronous code. If you don't need it, don't use it. For AI Engineering, the pattern is usually: wrap your LLM calls in a thin async layer, and keep the rest sync.

---

## Additional Concepts

### Creating tasks with create_task

```python
import asyncio

async def main():
    # Create a task that runs in the background
    task = asyncio.create_task(slow_operation())

    # Do other work while it runs
    print("Doing other things...")

    # Wait for the task to complete
    result = await task
    print(f"Got: {result}")
```

**Important:** The event loop only holds *weak* references to tasks. If you don't save the task reference, it can be garbage collected mid-execution:

```python
# ❌ BAD — task may be garbage collected
asyncio.create_task(some_coro())

# ✅ GOOD — keep a reference
task = asyncio.create_task(some_coro())
await task

# Or for fire-and-forget, keep in a set
background_tasks = set()
task = asyncio.create_task(some_coro())
background_tasks.add(task)
task.add_done_callback(background_tasks.discard)
```

### TaskGroup (Python 3.11+)

A safer alternative to `gather()` with better error handling:

```python
async def main():
    async with asyncio.TaskGroup() as tg:
        t1 = tg.create_task(fetch(1))
        t2 = tg.create_task(fetch(2))
        t3 = tg.create_task(fetch(3))
    # All tasks are guaranteed complete here
    print(t1.result())
```

If any task raises an exception, all other tasks are cancelled and the exception is raised in an `ExceptionGroup`.

### Timeouts

```python
async def main():
    try:
        async with asyncio.timeout(5):
            result = await slow_api_call()
    except TimeoutError:
        print("Request timed out")
```

### async with and async for

```python
# Async context manager — for connections, sessions, files
async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.json()

# Async iterator — for streaming data
async for chunk in stream_data():
    process(chunk)
```

These are just the `with` and `for` keywords extended for async code. They yield control to the event loop when waiting for setup/teardown (for `async with`) or the next item (for `async for`).

---

## Theory Summary

**Async is about waiting efficiently.** The fundamental insight is that most of your program's time is spent waiting — on a database, a file read, or a network response. Async doesn't make those operations faster. It prevents your program from sitting idle during the wait.

**The event loop is a traffic cop.** It decides which task runs next based on what's ready. Tasks that are waiting on something get deprioritized. Tasks that are ready to compute get the CPU. This is cooperative: no task is ever interrupted. They must voluntarily yield with `await`.

**`await` is a surrender, not a request.** When you write `await some_coro()`, you're not asking the event loop nicely to please maybe run something else. You're saying "I literally cannot proceed until this result is available." The event loop takes that as "ok, I'll run literally anything else until you're ready."

**Coroutines are not threads.** A coroutine is a function that can pause itself. A thread is an OS-level execution context that can be preempted at any instruction. Coroutines are far lighter — you can create tens of thousands without issue. Threads are system resources with hard limits.

**The sync SDKs work fine with async.** If the SDK you're using doesn't have an async client, wrap it with `asyncio.to_thread()`. The overhead of a thread pool is negligible for a handful of concurrent calls. But if you're making 100+ concurrent calls, use the async client.

**Not everything needs to be async.** If you have one LLM call per request, there's nothing to gain from async. The value appears when you have multiple independent calls — summarizing three documents, classifying ten chunks, generating five different responses from the same input.

---

## Quick Reference

| What you want | How to do it |
|---|---|
| Define a coroutine | `async def my_coro():` |
| Run a top-level coroutine | `asyncio.run(my_coro())` |
| Wait for a result (sequential) | `result = await another_coro()` |
| Run many concurrently | `await asyncio.gather(t1(), t2(), t3())` |
| Start background task | `task = asyncio.create_task(my_coro())` |
| Wait for task later | `result = await task` |
| Sleep without blocking | `await asyncio.sleep(n)` |
| Timeout a coroutine | `async with asyncio.timeout(n):` |
| Run sync function in async | `await asyncio.to_thread(sync_func, arg)` |
| Group tasks with safety | `async with asyncio.TaskGroup() as tg:` |

---

## What to Practice

1. Write a sync function that calls `time.sleep(1)` three times. Then write the async version using `asyncio.sleep()`. Compare runtimes.
2. Use `asyncio.gather()` to run three coroutines concurrently. Pass different delays and observe when each starts/finishes.
3. Write a coroutine that makes three API calls using `AsyncAnthropic()`. Time it with and without `gather()`.
4. Create a background task with `create_task()`, do other work, then `await` it.
5. Use `asyncio.to_thread()` to offload a CPU-heavy calculation.
6. Use `async with asyncio.timeout(2)` to implement a timeout on a slow coroutine.
7. Intentionally write a blocking `time.sleep()` inside a coroutine and observe how it stalls all concurrent tasks.

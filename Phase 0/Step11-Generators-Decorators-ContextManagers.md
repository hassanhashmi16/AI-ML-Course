# Step 11: Generators, Decorators & Context Managers

> **What it covers:** Iterators and the iteration protocol, generators with `yield`, decorators that wrap and extend functions, custom context managers with both class-based and `contextlib` approaches, and the `dataclasses` and `enum` modules — the Python features every AI library leans on.

---

## Foundational Concepts

### The function-as-object model

Everything here builds on one idea: **functions are first-class objects in Python.** You can pass them as arguments, return them from other functions, assign them to variables, and store them in data structures. This isn't academic — it's the mechanism behind decorators, context managers, and much of the standard library.

```python
def greet(name):
    return f"Hello, {name}"

# A function is just an object
print(type(greet))          # <class 'function'>
print(greet.__name__)       # "greet"

# You can assign it, pass it, return it
f = greet
print(f("Alice"))           # "Hello, Alice"
```

Without this concept, none of the rest of this step works.

### What is a protocol?

A **protocol** in Python is a set of methods that an object can implement to enable a specific behavior. The `for` loop doesn't care what type you give it — it only cares that the object follows the **iterator protocol** (`__iter__` and `__next__`). This is "duck typing": if it walks like a duck (implements the right methods), it's treated as a duck.

Protocols are the informal interfaces behind `for` loops, the `with` statement, and many built-in functions. You've already used several: iterator protocol (for), context manager protocol (`with`), and callable protocol (`()`).

### The problem generators solve: lazy vs. eager computation

**Eager** computation builds everything in memory up front. Python 2's `range(10_000_000)` created a list of 10 million integers — ~80 MB of RAM. **Lazy** computation produces values one at a time, on demand, never storing the whole sequence.

```python
# Eager: builds the entire list in memory (could be hundreds of MB)
squares = [x**2 for x in range(10_000_000)]

# Lazy: produces one value at a time (just a single object)
squares = (x**2 for x in range(10_000_000))
```

The second is a **generator expression**. It computes nothing until you iterate. For large datasets, LLM output streams, or infinite sequences, lazy evaluation isn't an optimization — it's the difference between code that works and code that crashes.

### What problem do decorators solve?

**Cross-cutting concerns** — behavior that applies across many functions. Without decorators, you repeat the same boilerplate (logging, timing, auth, caching) inside every function. With decorators, you define the extra behavior once and attach it with `@`. This is analogous to middleware in web frameworks: one piece of code runs before/after every request without each route handler knowing about it.

### What problem do context managers solve?

Resource pairs that must happen together (open → read → close, acquire lock → work → release) are fragile as separate try/finally blocks. The **context manager protocol** bundles setup and teardown into one reusable construct that Python guarantees will run cleanup even if an exception occurs.

### How all three connect

- **Generators** are the implementation mechanism behind `@contextmanager` from the standard library.
- **Decorators** can wrap generators and context managers to add behavior.
- **Context managers** (`with` blocks) manage resources; generators produce lazy sequences; decorators modify functions. All three rely on Python's function-as-object model and protocol system.
- FastAPI route decorators, pytest fixtures, LLM streaming, and database session management are all built on these three features.

---

## 5.1 — Iterators & the Iteration Protocol

### The protocol

Every `for` loop in Python does two things under the hood:

1. Calls `iter(obj)` to get an **iterator** object (which calls `obj.__iter__()`).
2. Calls `next(iterator)` repeatedly (which calls `iterator.__next__()`) until `StopIteration` is raised.

```python
# What "for x in my_list" actually does
my_list = [10, 20, 30]
it = iter(my_list)          # Step 1: get an iterator

while True:
    try:
        x = next(it)        # Step 2: get next value
        print(x)
    except StopIteration:   # Step 3: stop when exhausted
        break
```

Any object that implements `__iter__` and `__next__` is **iterable** and can be used in `for` loops.

### Making your own iterable

You can write a class with `__iter__` returning an iterator object that has `__next__`. But the idiomatic modern approach is to make `__iter__` itself a generator function — no separate iterator class needed:

```python
class Countdown:
    def __init__(self, start):
        self.start = start

    def __iter__(self):
        current = self.start
        while current > 0:
            yield current
            current -= 1

for n in Countdown(5):
    print(n, end=" ")   # 5 4 3 2 1
```

### Key distinction: iterable vs. iterator

| | Iterable | Iterator |
|---|---|---|
| Has `__iter__` | Yes | Yes |
| Has `__next__` | No | Yes |
| Can be used in `for` | Yes | Yes |
| Can iterate multiple times | Yes (creates new iterator) | No (gets consumed) |

```python
my_list = [1, 2, 3]          # iterable
it = iter(my_list)           # iterator

for x in my_list: ...        # works fine repeatedly
for x in it: ...             # first time: works
for x in it: ...             # second time: nothing — it's spent
```

**The key insight:** An iterable produces fresh iterators. An iterator is one-pass — once you've consumed it, it's done. This is why you can loop over a list twice but not over an iterator twice.

---

## 5.2 — Generators & `yield` (Lazy Streams)

### Generator functions

A **generator function** looks like a regular function but contains `yield` instead of `return`. When called, it returns a generator object **without executing the function body**. The function runs only when you iterate over the generator.

```python
def fibonacci(limit):
    a, b = 0, 1
    while a < limit:
        yield a
        a, b = b, a + b

gen = fibonacci(100)
print(gen)                    # <generator object fibonacci at 0x...>

for n in gen:
    print(n, end=" ")         # 0 1 1 2 3 5 8 13 21 34 55 89
```

**What happens at each `yield`:** The current value is returned to the caller, the function's entire state (local variables, instruction pointer) is frozen, and on the next `next()` call, execution resumes right after the `yield`. This state preservation is what makes generators fundamentally different from regular functions — they're resumable.

### Generator expressions

Like list comprehensions but with parentheses instead of brackets — they create a generator lazily rather than building a list eagerly:

```python
squares_list = [x**2 for x in range(1000)]     # 1000 ints in memory
squares_gen = (x**2 for x in range(1000))       # just a generator object

print(sum(squares_list))   # 332833500 — same result
print(sum(squares_gen))    # 332833500 — different memory profile
```

### The real-world payoff: memory

For LLM streaming, document processing, or any large dataset, generators are the difference between feasible and crashing:

```python
# Don't — loads the entire file into memory
def load_all_lines(filename):
    with open(filename) as f:
        return [line.strip() for line in f]

# Do — yields one line at a time
def stream_lines(filename):
    with open(filename) as f:
        for line in f:
            yield line.strip()

# Processing 10 GB: one line in memory at a time
for line in stream_lines("massive_log.txt"):
    process(line)
```

### `yield from` — delegating to sub-generators

`yield from` lets one generator delegate part of its work to another generator. This is useful for flattening nested structures, chaining sequences, or composing generators:

```python
def flatten(nested):
    for item in nested:
        if isinstance(item, list):
            yield from flatten(item)   # delegate recursively
        else:
            yield item

nested = [1, [2, [3, 4], 5], 6]
print(list(flatten(nested)))  # [1, 2, 3, 4, 5, 6]
```

### Generator `.send()` — two-way communication

Generators aren't just one-way pipelines. The `.send()` method lets you pass values **into** a generator — it resumes the generator and makes `yield` evaluate to the sent value:

```python
def running_average():
    total = 0
    count = 0
    while True:
        value = yield total / count if count else 0
        total += value
        count += 1

avg = running_average()
next(avg)                  # prime the generator
print(avg.send(10))        # 10.0
print(avg.send(20))        # 15.0
```

This is how coroutines work under the hood and what powers `@contextmanager`.

### Common pitfalls

1. **Single-use.** Once consumed, a generator is empty. Create a new one for each pass.
2. **No length.** `len(gen)` raises `TypeError`. Convert to a list first — but that defeats the memory advantage.
3. **Resource cleanup.** A generator paused at `yield` won't release resources until garbage collected or `.close()` is called. Use `try/finally` inside generators that hold resources.

---

## 5.3 — Decorators (Functions That Wrap Functions)

### The core idea

A **decorator** is a function that takes a function as input and returns a modified function as output — pure function-as-object mechanics. The `@` syntax is syntactic sugar applied at **function definition time**, not call time:

```python
# What @ does behind the scenes:
def logger(func):
    def wrapper(*args, **kwargs):
        print(f"[LOG] Calling {func.__name__} with {args}")
        result = func(*args, **kwargs)
        print(f"[LOG] {func.__name__} returned {result}")
        return result
    return wrapper

@logger
def add(a, b):
    return a + b

# The decoration happened when add was defined.
# Now every call to add is transparently logged:
add(3, 5)
# [LOG] Calling add with (3, 5)
# [LOG] add returned 8
```

Without a decorator, you'd have to add those print statements **inside** `add` itself — cluttering the function's real job with cross-cutting concern noise. With the decorator, `add` stays clean and the logging is defined once, reusable anywhere with `@logger`.

The decoration itself happens once (when the function is defined), not on every call — so the wrapping overhead is a one-time cost.

### The standard template

Every well-behaved decorator follows this pattern:

```python
import functools

def my_decorator(func):
    @functools.wraps(func)                   # preserves func's metadata
    def wrapper(*args, **kwargs):            # accepts any arguments
        # Do something before the call
        result = func(*args, **kwargs)       # call the original function
        # Do something after the call
        return result                        # return the original result
    return wrapper
```

**`@functools.wraps`** copies `__name__`, `__doc__`, `__module__`, and other metadata from the original function to the wrapper. Without it, every decorated function would report its name as "wrapper", breaking introspection and debugging — tools like `help()`, documentation generators, and debuggers would show the wrapper instead of your function.

### Practical example: timer

The timer decorator measures execution time — useful for profiling LLM calls, database queries, or any performance-sensitive code:

```python
import functools
import time

def timer(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"{func.__name__} took {elapsed:.4f}s")
        return result
    return wrapper
```

### Decorator factories (parameterized decorators)

When a decorator needs arguments (like `retry(max_attempts=3)`), you need a **decorator factory** — an outer function that takes the parameters and returns the actual decorator:

```python
def retry(max_attempts=3, delay=1.0):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    print(f"Attempt {attempt + 1} failed: {e}")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator

@retry(max_attempts=3, delay=0.5)
def call_llm_api(prompt):
    ...  # network call that might fail
```

**Plain decorator:** `@timer` — no parentheses. **Decorator factory:** `@retry(max_attempts=3)` — parentheses with arguments.

### Stacking decorators

Decorators apply **bottom-up** (the one closest to the function runs first):

```python
@timer        # outer: measures total time
@retry(max_attempts=3)   # inner: retries on failure
def unstable_api_call():
    ...
```

This is `timer(retry(max_attempts=3)(unstable_api_call))`. The inner decorator wraps the original function first, then the outer wraps that result. So retry handles failures internally, and timer measures the total time including retries.

### Decorators you already use

- `@property` — makes a method look like an attribute
- `@classmethod` / `@staticmethod` — changes method binding
- `@dataclass` — auto-generates `__init__`, `__repr__`, `__eq__`
- `@functools.cache` / `@functools.lru_cache` — memoization
- FastAPI `@app.get("/path")` — route registration with metadata
- `@pytest.fixture` — test dependency management

---

## 5.4 — Custom Context Managers (`contextlib`)

### The protocol

A **context manager** implements `__enter__` and `__exit__`. The `with` statement calls `__enter__` when the block starts and **guarantees** `__exit__` is called when the block exits — even if an exception occurs, a return statement, or a break:

```python
class ManagedFile:
    def __init__(self, filename, mode="r"):
        self.filename = filename
        self.mode = mode

    def __enter__(self):
        self.file = open(self.filename, self.mode)
        return self.file   # bound to the "as" variable

    def __exit__(self, exc_type, exc_value, traceback):
        self.file.close()
        return False       # False propagates exceptions; True suppresses

with ManagedFile("data.txt", "w") as f:
    f.write("Hello")       # file is closed even if this crashes
```

**The three parameters of `__exit__`:** `exc_type` (exception class or None), `exc_value` (exception instance or None), `traceback` (traceback object or None).

**Return values:** `False`/`None` propagates exceptions (normal behavior). `True` suppresses exceptions — use with extreme care, as it silently hides bugs.

### The `@contextmanager` decorator

Writing a class with `__enter__`/`__exit__` for every simple resource manager is verbose. The `@contextmanager` decorator lets you write a context manager as a **single generator function**:

```python
from contextlib import contextmanager

@contextmanager
def managed_file(filename, mode="r"):
    # __enter__ phase: runs before yield
    file = open(filename, mode)
    try:
        yield file   # value bound to "as" variable
    finally:
        # __exit__ phase: runs when block exits
        file.close()

with managed_file("data.txt", "w") as f:
    f.write("Hello")
```

**How it works:** `@contextmanager` wraps a generator. Code before `yield` runs as `__enter__`. The `yield` value becomes the `as` target. Code after `yield` (inside `finally`) runs as `__exit__`. If the `with` block raises, the exception is re-raised at the `yield` point so `finally` still runs — this is why try/finally is mandatory.

### Practical patterns

**Database transaction** — commit on success, rollback on failure:

```python
@contextmanager
def transaction(db):
    print("BEGIN")
    try:
        yield db
    except Exception:
        db.rollback()
        print("ROLLBACK")
        raise          # don't suppress — let the caller know
    else:
        db.commit()
        print("COMMIT")

with transaction(database) as db:
    db.execute("UPDATE accounts SET balance = balance + 100 WHERE id = 1")
```

**LLM cost tracking:**

```python
@contextmanager
def track_cost(model_name):
    start = time.time()
    yield                     # LLM call happens here
    elapsed = time.time() - start
    print(f"{model_name}: {elapsed:.2f}s")

with track_cost("claude-sonnet-5"):
    response = client.messages.create(...)
```

### `contextlib.suppress` — ignoring expected errors

A cleaner alternative to `try/except pass` for expected, harmless errors:

```python
from contextlib import suppress

with suppress(FileNotFoundError):
    os.remove("temp_file.txt")
```

### `ExitStack` — variable numbers of managers

When you don't know at write time how many context managers you'll need:

```python
from contextlib import ExitStack

def open_files(filenames):
    with ExitStack() as stack:
        files = [stack.enter_context(open(fname)) for fname in filenames]
        # If any open() fails, previously opened files are closed automatically
        return stack.pop_all().enter_context(...)
```

This is how libraries handle dynamic numbers of resources (connections, file handles, locks) safely.

### Common pitfalls

1. **The `@contextmanager` generator must yield exactly once.** Zero or multiple yields raise `RuntimeError`.
2. **Suppressing exceptions is almost always wrong.** It silently hides bugs. Only suppress expected, harmless exceptions.
3. **try/finally is mandatory with `@contextmanager`.** Without it, exceptions in the `with` block skip cleanup — defeating the purpose.
4. **Context managers are single-use by default.** A `@contextmanager` can't be restarted. Create a new one each time.

---

## 5.5 — `dataclasses` & `enums`

### `dataclasses` — classes that are mostly data

Writing a class that primarily holds data is tedious boilerplate: `__init__`, `__repr__`, `__eq__`, `__hash__`. The `@dataclass` decorator generates all of them from type annotations:

```python
from dataclasses import dataclass

@dataclass
class ChatMessage:
    role: str
    content: str
    token_count: int = 0        # default value
    metadata: dict | None = None

msg = ChatMessage("user", "Hello", 5)
print(msg)   # ChatMessage(role='user', content='Hello', token_count=5, metadata=None)
```

**Why dataclasses matter for AI engineering:** Pydantic models (Step 17) are a superset with validation. Structured LLM output parsing uses the same field-based pattern. Configuration classes, return types, and data transfer objects all benefit from automatic `__init__`/`__repr__`/`__eq__`.

**Key parameters:**

| Parameter | Default | Effect |
|---|---|---|
| `frozen=True` | `False` | Immutable instances (can't reassign fields) |
| `order=True` | `False` | Generates `<`, `<=`, `>`, `>=` |
| `slots=True` | `False` | `__slots__` for memory efficiency (3.10+) |

```python
@dataclass(frozen=True)
class Config:
    api_key: str
    model: str = "claude-sonnet-5"
    temperature: float = 0.0

cfg = Config(api_key="sk-...", model="gpt-4o")
# cfg.model = "claude"  # FrozenInstanceError!
```

**`field()` for advanced control:** Use `default_factory` instead of mutable defaults (the "mutable default trap" — a bare `list = []` is shared by all instances). Use `repr=False` to exclude sensitive or large fields from the string representation. Use `init=False` for computed fields.

**`__post_init__`** for computed fields and validation — runs after the auto-generated `__init__`:

```python
@dataclass
class Document:
    content: str
    chunk_count: int = field(init=False)

    def __post_init__(self):
        self.chunk_count = len(self.content) // 1000 + 1
```

### `enum` — named constants

An **enum** is a set of named constant values. They prevent typos and make code self-documenting:

```python
from enum import Enum

class ModelProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    LOCAL = "local"

def call_model(provider: ModelProvider, prompt: str):
    if provider == ModelProvider.ANTHROPIC:
        pass   # no risk of misspelling "anthropi"
```

**Why enums over strings:** Typos are caught at definition time, not runtime. Autocomplete works — your IDE knows all valid values. Related constants live in one place. `list(ModelProvider)` gives you every valid option. Enum members are singletons, so `is` comparison works.

**`auto()`** for automatic integer values when you only care about uniqueness, not the specific value:

```python
from enum import Enum, auto

class LogLevel(Enum):
    DEBUG = auto()      # 1
    INFO = auto()       # 2
    WARNING = auto()    # 3
    ERROR = auto()      # 4
```

**`IntEnum`** for enums that behave as integers — usable in comparisons, as list indices, or with math operators:

```python
from enum import IntEnum

class Priority(IntEnum):
    LOW = 10
    MEDIUM = 50
    HIGH = 100

if current_priority >= Priority.HIGH:
    escalate()
```

---

## Theory Summary

**Iteration is a protocol, not a type.** Any object with `__iter__` and `__next__` works in `for` loops — duck typing in action. Iterables create fresh iterators; iterators are one-pass consumers.

**Generators are lazy iterators that remember state.** A generator function pauses at each `yield`, preserving local variables and execution position. They're the idiomatic way to handle streams (file lines, LLM tokens, paginated API responses) and datasets too large for memory.

**`yield` produces; `return` ends.** A generator can have multiple `yield` statements over its lifetime. `return` raises `StopIteration`. Every generator is an iterator, but not every iterator is a generator.

**Decorators transform functions at definition time.** The `@` syntax runs when the function is defined, not when it's called — wrapping overhead is one-time. `@functools.wraps` is mandatory for proper introspection. Decorator factories enable parameterized decorators like `@retry(3)`.

**Context managers guarantee cleanup.** The `with` statement is a structured replacement for try/finally. `__exit__` runs unconditionally — on success, exception, or early return. `@contextmanager` uses `yield` to split setup from teardown in a single function.

**Dataclasses eliminate boilerplate.** `@dataclass` generates `__init__`, `__repr__`, `__eq__` (and optionally `__hash__`, `__lt__`, `__slots__`) from type annotations. Use `field()` for mutable defaults, computed fields, and field-level configuration. Enums make named constants type-safe and autocomplete-friendly.

**All four features rely on Python's function-as-object model.** Without first-class functions, you can't have decorators (taking and returning functions), `@contextmanager` (wrapping a generator), or `__post_init__` (called from auto-generated `__init__`). Understanding this model unlocks how Python's most powerful features connect.

---

## Quick Reference

| Concept | Key point |
|---|---|
| **Iterator protocol** | `__iter__` returns iterator; `__next__` returns next value or raises `StopIteration` |
| **Generator** | Function with `yield`; lazy, stateful, single-use |
| **Generator expression** | `(x for x in ...)` — lazy comprehension |
| **`yield from`** | Delegate to sub-generator |
| **Decorator** | Function that takes a function, returns a modified function |
| **`@functools.wraps`** | Preserves original function's metadata on the wrapper |
| **Decorator factory** | Outer function that returns a decorator (for parameterized decorators) |
| **Context manager protocol** | `__enter__` returns resource; `__exit__` cleans up |
| **`@contextmanager`** | Generator-based context manager — yield once, try/finally required |
| **`ExitStack`** | Dynamic, variable-number of context managers |
| **`@dataclass`** | Auto-generates `__init__`, `__repr__`, `__eq__` from annotations |
| **`field()`** | Per-field config: default_factory, repr=False, init=False |
| **`Enum`** | Type-safe named constants; `auto()` for automatic values |
| **`IntEnum`** | Enum that behaves as an integer |

---

## What to Practice

1. **Build a custom iterable.** Write a `Range` class implementing `__iter__` and `__next__` to replicate `range()` without storing all values.

2. **Generator pipeline.** Write a generator reading a CSV line by line, a second filtering rows, a third converting rows to dicts. Chain them. Observe memory with 100k+ rows.

3. **Write a `@retry` decorator.** Start fixed-attempts, then extend with `max_attempts` and `delay`. Test on a function that fails 30% of the time.

4. **Write a `@timer` decorator.** Stack with `@retry` — verify retry handles failures, timer measures total time across retries.

5. **Write a DB transaction context manager** using `@contextmanager`. Commit on success, rollback and re-raise on exception. Test both paths.

6. **Model an LLM API response as a dataclass.** Include content, model, usage (nested dataclass), finish_reason. Use `field(repr=False)` for the raw response.

7. **Define an `enum` for HTTP status categories** (2xx, 3xx, 4xx, 5xx). Write a function returning the category from a status code.

8. **Simulate an LLM streaming response** — generator yielding tokens with simulated latency, then a context manager tracking total tokens and elapsed time around the stream.

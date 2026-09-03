# Step 13: Testing with pytest

> **What it covers:** Test functions and assertions, fixtures (setup/teardown, scope), parametrized tests, mocking external APIs so unit tests never make a live LLM call, what you can and can't assert about non-deterministic output, and test discovery/markers/config — the fastest way to tell a hobby repo from an engineer's repo.

---

## The Problem

You change a prompt template, a chunking function, or a retry decorator, and you have no way to know if you broke something three files away until it fails in front of a user — or in production. `print()` and manually re-running `main.py` don't scale past a few functions, and they don't run themselves every time you touch the code. Step 71's CI pipeline needs something it can run automatically and get a pass/fail from; "I tried it and it looked fine" isn't a CI gate.

Worse, AI code has a specific version of this problem: the function you're testing calls out to Anthropic, OpenAI, or Gemini. If your tests actually hit that API, they're slow, they cost money, they fail when you're offline, and they can fail randomly because the model's output changes run to run — even though your parsing code is perfectly fine. Without knowing how to isolate your code from the model, you can't write tests for anything that touches an LLM, which in this course is almost everything from Step 15 onward.

---

## Foundational Concepts

### Why automated tests over manual checking

A test is code that calls your code and checks the result — no human required, runs in milliseconds, runs the same way every time, and runs before every commit instead of "whenever you remember." The value isn't catching bugs on day one (you'd probably catch those manually too). It's catching the regression on day 90, in a function you forgot existed, when you change something unrelated. That's the entire justification for spending time writing tests for code that "already works."

### Arrange — Act — Assert

Nearly every good test has the same three-part shape, regardless of language or framework:

1. **Arrange** — set up the inputs and any fake dependencies.
2. **Act** — call the one thing you're testing.
3. **Assert** — check the result.

```python
def test_discount_applies_to_total():
    cart = Cart(items=[Item(price=100)])   # Arrange
    cart.apply_discount(0.10)              # Act
    assert cart.total == 90                # Assert
```

When a test doesn't fit this shape — when "arrange" and "assert" are tangled together — it's usually testing too much at once. Split it.

### Test doubles: know what you're actually using

A **test double** is a stand-in object that takes the place of a real dependency during a test — the term is borrowed from movie **stunt doubles**, who stand in for the real actor when the scene is too risky or expensive to shoot for real. You use a double when the real thing (a database, an API, the filesystem) would make the test slow, unreliable, expensive, or outright dangerous (nobody wants a test suite that emails real customers).

"Mocking" gets used as a catch-all word for this, but there are five distinct kinds of double, depending on how much the stand-in actually needs to do — a taxonomy from Gerard Meszaros popularized by Martin Fowler ([martinfowler.com/articles/mocksArentStubs.html](https://martinfowler.com/articles/mocksArentStubs.html)):

| Double | What it does | Example |
|---|---|---|
| **Dummy** | Passed around, never actually used | An empty `logger=None` argument a function requires but ignores in this path |
| **Stub** | Returns a canned answer, doesn't care how it's called | A fake LLM client whose `.complete()` always returns `"ok"` |
| **Fake** | A real, working, simplified implementation | An in-memory dict standing in for a database |
| **Spy** | A stub that also records how it was called | A fake email sender that remembers every message sent |
| **Mock** | Pre-programmed with *expectations* — the test fails if it isn't called correctly | `mock_api.post.assert_called_once_with(...)` |

The practical distinction that matters: stubs/fakes/spies are checked via **state verification** ("did the result come out right?"); mocks are checked via **behavior verification** ("was the dependency called correctly?"). Python's `unittest.mock` module (Section 13.4) can produce any of these five depending on how you configure it — the class is called `Mock`, but what you build with it might be a stub.

### pytest vs. unittest — why this course uses pytest

Python ships a built-in test framework, `unittest`, which is class-based and Java-flavored (`self.assertEqual(a, b)`, `setUp`/`tearDown` methods). **pytest** is the de facto standard on top of it: plain functions, plain `assert`, and a fixture system that replaces `setUp`/`tearDown` with dependency injection. pytest can run `unittest`-style tests unchanged, so adopting it is strictly additive.

```python
# unittest style — works, but verbose
import unittest
class TestMath(unittest.TestCase):
    def test_add(self):
        self.assertEqual(1 + 1, 2)

# pytest style — what you'll actually write
def test_add():
    assert 1 + 1 == 2
```

### Determinism is a design property, not a testing trick

The real fix for "I can't test this, it calls an API" is not a clever mocking technique — it's writing the function so the dependency is a parameter, not a hardcoded import. A function that takes a `client` argument is trivial to test with a fake client; a function that does `import anthropic; client = anthropic.Anthropic()` at the top of the file is fighting you before the test even starts. Keep this in mind while reading 13.4 — the mocking tools exist to work around code that wasn't written this way, and sometimes the better fix is to change the code, not add another patch.

---

## 13.1 — Test Functions & Assertions

### Discovery rules

pytest finds tests by convention, not configuration: files named `test_*.py` or `*_test.py`, functions named `test_*` inside them, and classes named `Test*` with methods named `test_*` (no `__init__`). Run `pytest` with no arguments from the project root and it recursively finds everything matching that pattern.

```python
# test_chunking.py
def test_empty_string_returns_no_chunks():
    assert chunk_text("") == []

def test_short_text_returns_one_chunk():
    assert len(chunk_text("hello world")) == 1
```

```
$ pytest
======================== test session starts =========================
collected 2 items

test_chunking.py ..                                              [100%]
========================= 2 passed in 0.01s =========================
```

### Assertion rewriting

pytest rewrites plain `assert` statements at import time to produce a detailed failure report — you write `assert a == b`, and on failure pytest shows you exactly what `a` and `b` were, with no need for `unittest`'s zoo of `assertEqual`/`assertIn`/`assertIsInstance` methods:

```python
def test_summary_has_title():
    result = {"title": "", "attendees": []}
    assert result["title"] != ""
# AssertionError: assert '' != ''
```

One `assert` covers everything `unittest` needs a dozen different method names for — `assert x == y`, `assert x in y`, `assert isinstance(x, y)`, `assert x is None` all just work and all produce a readable failure.

### Exceptions and floats

```python
import pytest

def test_missing_api_key_raises():
    with pytest.raises(ValueError, match="API key"):
        load_client(api_key=None)

def test_similarity_score_is_close_enough():
    assert cosine_similarity(v1, v2) == pytest.approx(0.87, abs=0.01)
```

`pytest.raises` is the only correct way to test "this should fail" — never wrap a call in `try/except` and assert inside the `except` block, because a test that never raises will silently pass. `pytest.approx` exists because floating-point equality (`0.1 + 0.2 == 0.3`) is unreliable; never compare floats with bare `==`.

---

## 13.2 — Fixtures (Setup/Teardown, Scope)

### The problem, before the fix

Say you're testing `summarize()`. The first test needs a sample transcript, so you write one inline:

```python
def test_summary_extracts_attendees():
    transcript = "Alice: Let's ship by Friday.\nBob: Agreed, I'll own the deploy."
    summary = summarize(transcript)
    assert "Alice" in summary.attendees

def test_summary_flags_the_deadline():
    transcript = "Alice: Let's ship by Friday.\nBob: Agreed, I'll own the deploy."
    summary = summarize(transcript)
    assert "friday" in summary.summary.lower()
```

Two tests, same transcript string, copy-pasted. Fine for two — but write a fifth test that also needs a sample transcript, and you're maintaining that same literal string in five places. Change the transcript format once (add a timestamp, fix a typo) and you're now editing five tests by hand, and it's easy to miss one and leave it silently testing stale data. This is the exact repetition `setUp` was invented for in `unittest` — but `unittest`'s `setUp` runs before *every* test in a class whether that test needs the data or not, which trades one problem for another.

**Fixtures** are pytest's fix for both: a function decorated with `@pytest.fixture`, requested by name as a test's argument. pytest resolves it, runs it once per test that asks for it, and injects the result — no copy-pasted literal, and no forced setup for tests that don't need it:

```python
import pytest

@pytest.fixture
def sample_transcript():
    return "Alice: Let's ship by Friday.\nBob: Agreed, I'll own the deploy."

def test_summary_extracts_attendees(sample_transcript):
    summary = summarize(sample_transcript)
    assert "Alice" in summary.attendees

def test_summary_flags_the_deadline(sample_transcript):
    summary = summarize(sample_transcript)
    assert "friday" in summary.summary.lower()
```

Change the transcript once, in the fixture, and every test that requests `sample_transcript` picks up the change automatically. A test that doesn't need it — say, one testing an unrelated function — simply doesn't list it as an argument, and pytest never runs it for that test.

### Setup *and* teardown with `yield`

Code before `yield` is setup; code after is teardown, and it runs even if the test fails — the fixture is wrapped in an implicit `try/finally`:

```python
@pytest.fixture
def temp_log_file(tmp_path):
    path = tmp_path / "run.log"
    path.write_text("")
    yield path                 # test runs here, using `path`
    # teardown — runs even if the test raised
    path.unlink(missing_ok=True)
```

`tmp_path` is a built-in pytest fixture: a fresh, auto-cleaned temp directory per test. Never hand-roll temp file handling when this exists.

### Seeing the order for yourself

When one fixture depends on another, what actually runs, and in what order? Rather than take it on faith, make it visible:

```python
@pytest.fixture
def db_connection():
    print("\nopening connection")
    yield "conn"
    print("closing connection")

@pytest.fixture
def db_transaction(db_connection):
    print("starting transaction")
    yield db_connection
    print("rolling back transaction")

def test_query(db_transaction):
    print("running the actual test")
```

```
$ pytest -s -v test_db.py
opening connection
starting transaction
running the actual test
rolling back transaction
closing connection
PASSED
```

(`-s` is required — pytest captures `print` output by default and hides it unless a test fails; `-s` disables that capture so you can see this trace.) Setup ran outer-to-inner: `db_connection` before `db_transaction`, because `db_transaction` depends on it and needs it to exist first. Teardown ran the *exact reverse* — inner-to-outer, last-set-up-first-torn-down. That's not a coincidence; it's the rule, and it's why nested fixtures are safe: whatever a fixture depends on is guaranteed to still be alive when that fixture's own teardown code runs.

### Scope: how long a fixture lives

| Scope | Recreated | Use for |
|---|---|---|
| `function` (default) | Every test | Anything that must be fresh — most fixtures |
| `class` | Once per test class | Rare; test-class-specific shared state |
| `module` | Once per file | An expensive read-only resource shared by a file's tests |
| `session` | Once for the whole run | A loaded embedding model, a Docker container, a DB connection |

```python
@pytest.fixture(scope="session")
def embedding_model():
    return load_model("all-MiniLM-L6-v2")   # loaded once, reused by every test
```

**Gotcha:** a `session`-scoped fixture cannot depend on a `function`-scoped one — pytest raises an error, because the broad-scope fixture would need to outlive the narrow one. Scope must narrow as you go down the dependency chain, never widen.

### `autouse` and factories

`autouse=True` runs a fixture for every test in its scope without being requested — useful for things like resetting global state, but it hides the dependency from the test's signature, so use it sparingly:

```python
@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
```

When a test needs *multiple, differently-configured* instances rather than one fixed value, return a function instead of a value — a **fixture factory**:

```python
@pytest.fixture
def make_action_item():
    def _make(task="Ship it", owner=None):
        return ActionItem(task=task, owner=owner)
    return _make

def test_action_item_without_owner(make_action_item):
    item = make_action_item(owner=None)
    assert item.owner is None
```

### `conftest.py` — sharing fixtures across files

A file named `conftest.py` is auto-discovered by pytest; any fixture defined there is available to every test file in that directory and below, with no import needed. This is where you put fixtures more than one test file needs — a fake API client, a sample dataset, a temp project structure.

---

## 13.3 — Parametrized Tests

### One test, many inputs

`@pytest.mark.parametrize` runs the same test body once per row of data, instead of copy-pasting near-identical test functions:

```python
import pytest

@pytest.mark.parametrize("text,expected_chunks", [
    ("", 0),
    ("short", 1),
    ("word " * 500, 3),
])
def test_chunk_count(text, expected_chunks):
    assert len(chunk_text(text, chunk_size=800)) == expected_chunks
```

```
$ pytest -v
test_chunking.py::test_chunk_count[-0]         PASSED
test_chunking.py::test_chunk_count[short-1]    PASSED
test_chunking.py::test_chunk_count[word -1] .. PASSED
```

Each row becomes its own test ID (shown in `[]`) and its own pass/fail — one bad row doesn't hide the others, unlike a single test with a `for` loop and one `assert` at the end. Use the `ids=[...]` argument to give rows readable names instead of pytest's auto-generated ones.

### Stacking = combinations

Two `@parametrize` decorators on one function multiply — every value of the first runs against every value of the second:

```python
@pytest.mark.parametrize("temperature", [0.0, 0.7])
@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_client_builds(provider, temperature):
    ...   # runs 4 times: 2 providers × 2 temperatures
```

### Gotcha: shared mutable values

Parametrize values are passed to every test run **as the same object, not a copy**. If a test mutates a `list` or `dict` parameter, later tests using that same parametrized value see the mutation. Use immutable values (tuples, frozen dataclasses) or construct fresh objects inside the test.

### Beyond hand-picked examples: property-based testing

`@parametrize` still requires *you* to think of the interesting inputs. **Property-based testing** flips this: you describe the *shape* of valid input and a *property* that should always hold, and the tool ([Hypothesis](https://hypothesis.readthedocs.io/), the standard Python library) generates hundreds of inputs — including edge cases you wouldn't have thought to write by hand — trying to break your property.

```python
from hypothesis import given, strategies as st

@given(st.text(), st.integers(min_value=1, max_value=2000))
def test_chunk_text_never_exceeds_chunk_size(text, chunk_size):
    for chunk in chunk_text(text, chunk_size):
        assert len(chunk) <= chunk_size          # the property, not a specific example

# Hypothesis will try "", very long strings, unicode, whitespace-only text,
# chunk_size=1, chunk_size=2000 — and shrink any failure to the smallest
# input that still reproduces it.
```

This is the difference between "I tested 3 transcripts and they worked" and "I proved this holds for any string and any chunk size in range" — a meaningfully stronger guarantee, and one most engineers never reach for. It's not a replacement for example-based tests (which document specific, readable expected behavior) — use both: a handful of `@parametrize` cases for the behaviors you want to document, `@given` for the invariants you want stress-tested. Reach for it on pure functions with a clear property (idempotence, round-tripping, invariants like "output length never exceeds input length") — it's a poor fit for anything involving mocked I/O, since Hypothesis wants to call the function hundreds of times cheaply.

---

## 13.4 — Mocking External APIs

### The rule: no live network calls in unit tests

Unit tests must not depend on a real LLM API, a real database, or the network — otherwise they're slow, cost money per run, fail when you're offline or rate-limited, and (this is the sharp edge) can fail for reasons that have nothing to do with a bug in your code. The fix isn't "don't test that code" — it's replacing the real dependency with a test double for the duration of the test.

### `unittest.mock`: the standard tool

```python
from unittest.mock import Mock, patch

def test_summarize_calls_the_model():
    fake_client = Mock()
    fake_client.complete.return_value = "Meeting covered Q3 roadmap."

    result = summarize(fake_client, transcript="...")

    assert result == "Meeting covered Q3 roadmap."
    fake_client.complete.assert_called_once()   # behavior verification
```

Line by line — this only makes sense if `summarize` is written to *take* a client as an argument (the "determinism is a design property" point from earlier), so assume `summarize(client, transcript)` calls `client.complete(transcript)` internally and returns whatever comes back.

- `fake_client = Mock()` — creates a blank stand-in object. It has no real methods yet; `Mock` will invent any attribute or method you ask for the moment you touch it. Right now it's just an empty shell.
- `fake_client.complete.return_value = "Meeting covered Q3 roadmap."` — this line does two things at once. First, just by writing `fake_client.complete`, you cause `Mock` to auto-create a fake `complete` method on the fly (you never defined one — that's the "invents any attribute" behavior). Second, `.return_value = ...` configures that fake method: "whenever anyone calls `fake_client.complete(...)`, no matter what argument they pass, hand back this exact string."
- `result = summarize(fake_client, transcript="...")` — this calls your *real* `summarize` function, but hands it the fake client instead of a real Anthropic/OpenAI/Gemini client. Inside `summarize`, the line `client.complete(transcript)` runs against the fake — no network call happens anywhere.
- `assert result == "Meeting covered Q3 roadmap."` — checks that whatever `summarize` did with the fake's return value, it correctly passed it through as its own result. This is **state verification** — checking the output.
- `fake_client.complete.assert_called_once()` — a completely different kind of check. This doesn't look at any return value; it asks the mock itself, "were you actually called, exactly once?" If `summarize` had a bug where it forgot to call `complete` at all, the line above (`assert result == ...`) might still accidentally pass with a coincidental value — this line is what catches that. This is **behavior verification**, and it's only possible because `Mock` records every call made to it.

`MagicMock` is the same thing with Python's dunder methods (`__len__`, `__iter__`, etc.) pre-wired — use it when the code under test does something like `len(client_response)`.

`return_value` sets a fixed answer; `side_effect` covers everything more dynamic — raising an exception, returning different values on successive calls, or running a custom function:

```python
flaky = Mock(side_effect=[TimeoutError(), TimeoutError(), "success"])
# first two calls raise TimeoutError, third returns "success" — great for testing retry logic
```

### `patch`: swapping out real objects for the test's duration

`Mock()` above works when your function *takes* the client as an argument. But plenty of code doesn't — it just does `from summarizer import anthropic_client` at the top of a file and uses that name directly, with no way for a test to hand it a fake. `patch` is for exactly that case: it reaches into an already-written module and swaps a name out, from the outside, for the duration of one test.

```python
@patch("summarizer.anthropic_client")
def test_summarize_handles_api_error(mock_client):
    mock_client.messages.create.side_effect = ConnectionError("timeout")
    with pytest.raises(ConnectionError):
        summarize(transcript="...")
```

Line by line — this is the part that looks like magic the first time you see it:

- `@patch("summarizer.anthropic_client")` — before this test runs, Python goes into the already-imported `summarizer` module, finds the name `anthropic_client` sitting in it, and swaps in a brand-new `Mock` object in its place. The string is a *path to a name inside a module*, not a function call — that's why it's quoted text, not `summarizer.anthropic_client` written as real code. When the test function finishes (pass or fail), `patch` puts the original real object back — you never have to clean up manually.
- `def test_summarize_handles_api_error(mock_client):` — here's the actual "magic" part: `@patch` doesn't just do the swap silently, it also **hands you the fake object it just created**, as an extra argument to your test function. You never wrote `mock_client = Mock()` anywhere — the decorator creates it and passes it in for you. The parameter name (`mock_client`) is yours to choose; what matters is *position*, not the name.
- `mock_client.messages.create.side_effect = ConnectionError("timeout")` — same idea as `return_value` from the previous section, but instead of returning a value when called, this configures the fake to *raise* a `ConnectionError` when `.messages.create(...)` is called. `side_effect` is what you reach for any time "just return a fixed value" isn't dynamic enough — raising an exception, returning different things on successive calls, or running custom logic.
- `with pytest.raises(ConnectionError): summarize(transcript="...")` — calls the real `summarize` function. Somewhere inside it, `summarize` uses the module-level `anthropic_client` name — but because of the patch, that name now points at the fake, so calling it raises `ConnectionError` exactly as configured. `pytest.raises` catches that and turns "an exception happened" into "the test passed," proving `summarize` correctly propagates the error instead of silently swallowing it.

**The single most common mistake here: patch where the name is *looked up*, not where it's *defined*.** If `summarizer.py` does `from llm_sdk import client`, that module now has its own name `summarizer.client` pointing at the same object — patching `llm_sdk.client` does nothing to the copy `summarizer` is holding, because `summarize` never looks the name up in `llm_sdk` again after that import. You must patch `summarizer.client`, the copy that's actually consulted at call time. This trips up everyone once; after that it's automatic.

### `monkeypatch` — pytest's built-in alternative

For simpler cases — one attribute, one env var — the `monkeypatch` fixture is less ceremony than `patch` and auto-reverts after the test with no context manager needed:

```python
def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError):
        load_client()

def test_uses_test_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    ...
```

### Mocking HTTP directly: `responses`

When the code under test makes raw HTTP calls (`requests`/`httpx`) rather than going through an SDK object you can easily substitute, mock at the HTTP layer instead:

```python
import responses

@responses.activate
def test_embedding_api_call():
    responses.add(
        responses.POST, "https://api.example.com/embeddings",
        json={"embedding": [0.1, 0.2, 0.3]}, status=200,
    )
    result = get_embedding("hello world")
    assert len(result) == 3
```

### Which tool, when

| Tool | Best for |
|---|---|
| `unittest.mock.Mock`/`MagicMock` | Replacing an object/method your code calls directly |
| `unittest.mock.patch` | Swapping a name at import time (a client, a class, a whole module attribute) |
| `monkeypatch` | Env vars, single attributes, quick one-off swaps in a pytest-native way |
| `responses` / `httpx` mocking | Code that talks raw HTTP instead of going through an SDK object |
| `autospec=True` | Any of the above, when you want a `TypeError` if you call the mock with the wrong signature — catches typos `Mock()` alone would miss |

---

## 13.5 — Testing Non-Deterministic Output

### The actual problem

Ask an LLM the same question twice at `temperature > 0` and you can get two different (both correct) answers. `assert response == "expected text"` is not just fragile here — it's the wrong tool. But this doesn't mean the output is untestable; it means you need to test the *shape* of correctness, not the exact string.

### What you CAN assert

- **Type and schema** — did it come back as valid JSON, and does it validate against your Pydantic model (Step 17)? This is usually your strongest, cheapest check.
- **Structural bounds** — non-empty, under a max length, has the expected keys, list has at least one item.
- **Presence, not exact wording** — `"friday" in result.lower()` when the transcript mentioned a Friday deadline, rather than checking the sentence verbatim.
- **Regex/format** — a date field matches `\d{4}-\d{2}-\d{2}`, an email field contains `@`.
- **Your code's logic, with the model's response mocked** — this is the big one. Mock the client to return a fixed, known payload (13.4), and assert your *parsing and error-handling* code does the right thing with it. This is deterministic and should be the bulk of your test suite.

```python
def test_summary_schema_is_valid(mock_client):
    mock_client.complete.return_value = '{"title": "Standup", "attendees": ["Alice"], ...}'
    result = summarize(mock_client, transcript="...")
    assert isinstance(result, MeetingSummary)     # Pydantic validated it
    assert len(result.attendees) > 0
```

### What you CAN'T assert

Exact generated text, exact phrasing, "the best possible answer." If you find yourself writing `assert result == "Alice will follow up on the deployment by Friday."`, stop — that test will fail the next time the model, prompt, or temperature changes, for no reason related to a bug.

### Where this stops being a pytest problem

Grading whether an LLM's answer is *actually good* — faithful, relevant, not hallucinated — is a different discipline: **evals**, covered starting Step 30 (`evaluate()` & a golden dataset) and Step 76 (LLM-as-judge). Those use scored rubrics and statistical confidence over many samples, not pass/fail asserts, because "good" is graded, not matched. Step 13's job is narrower and cheaper: keep your *code* — parsing, validation, retries, error handling — covered by fast, deterministic, mocked unit tests, and leave judging the model's actual answer quality to the eval harness. Conflating the two is how teams end up with a test suite that's slow, flaky, and still doesn't measure what they think it measures.

### Snapshot testing — a middle ground

For output that's complex but *should* be stable given the same input (e.g., a deterministic formatting function, or a mocked-LLM-response pipeline), a **snapshot test** captures the output once, saves it, and future runs diff against the saved version:

```python
def test_formats_summary_consistently(mock_client, snapshot):
    result = format_summary(FIXED_SUMMARY)
    assert result == snapshot   # pytest-snapshot / syrupy plugin
```

Snapshots are for output that's deterministic given a fixed mocked input — not a substitute for mocking, and not appropriate for genuinely non-deterministic (live model) output.

---

## 13.6 — Test Discovery, Markers & Config

### Configuration lives in `pyproject.toml`

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: hits a real external service",
]
```

Registering custom markers avoids `PytestUnknownMarkWarning` and documents what each marker means for anyone reading the suite.

### Markers: `skip`, `skipif`, `xfail`

```python
import sys
import pytest

@pytest.mark.skip(reason="not implemented yet")
def test_future_feature():
    ...

@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only path handling")
def test_unix_permissions():
    ...

@pytest.mark.xfail(reason="known bug, tracked in #42")
def test_edge_case_currently_broken():
    assert weird_edge_case() == "correct"
```

`skip` never runs the test. `xfail` runs it but doesn't fail the suite if it fails — and *does* flag it (as `XPASS`) if it unexpectedly starts passing, which is your signal to remove the marker and fix the real test.

### Useful CLI flags

| Flag | Effect |
|---|---|
| `-k "chunk and not slow"` | Run tests matching a name expression |
| `-m "not integration"` | Run/skip tests by marker |
| `-x` | Stop after the first failure |
| `--lf` | Rerun only last failed tests |
| `-v` | Verbose — show each test name |

### Coverage: measure it, don't chase it

`pytest-cov` reports which lines your tests actually executed:

```bash
pytest --cov=src --cov-report=term-missing
```

Coverage tells you what code *ran* during tests, not whether the assertions were any good — a test with no `assert` at all still counts as "covered." Use coverage to find untested code you forgot about, not as a target to hit 100%. The last 5% is usually error-handling branches that cost more to fake-trigger than they're worth, or genuinely untestable code that should be simplified instead.

---

## Pitfalls

1. **Hitting a live LLM API in a unit test.** Slow, costs money on every CI run, fails when offline, and can fail randomly for reasons unrelated to your code. Mock the client (13.4) — always.
2. **Patching the wrong path.** `@patch("some_sdk.client")` does nothing if your code imported it as `from some_sdk import client` — patch `your_module.client` instead. This is the #1 "my mock isn't working" bug.
3. **Asserting exact LLM output text.** Breaks the moment the model, prompt, or temperature changes. Assert structure/schema/presence instead (13.5), or mock the response and test your own logic.
4. **Session-scoped fixture depending on a function-scoped one.** pytest errors — narrow-scope dependencies can't be embedded inside broad-scope fixtures. Fix by matching scopes or restructuring the dependency.
5. **Mutating a parametrized value inside a test.** Parametrize passes the same object to every run, not a copy; a mutated `list`/`dict` leaks into the next test case using that value.
6. **`autouse` fixtures hiding dependencies.** A test that mysteriously behaves differently once you add an unrelated fixture file is almost always an `autouse` fixture you didn't know was running. Use sparingly, and name them obviously.
7. **Chasing 100% coverage.** Coverage measures which lines *executed*, not whether the test actually checked anything meaningful. A test with a coverage hit and no real assertion is worse than no test — it looks green and proves nothing.
8. **Testing implementation instead of behavior.** Mocking every internal function call means the test breaks on any refactor, even correct ones — mock at the boundary (the external API), not the boundary of every private function.

---

## Quick Reference

| Concept | Key point |
|---|---|
| **Test discovery** | Files `test_*.py`, functions `test_*`, no config needed |
| **`assert`** | Plain Python `assert`; pytest rewrites it for readable failure output |
| **`pytest.raises`** | Only correct way to test that code raises an exception |
| **`pytest.approx`** | Float comparisons; never use bare `==` on floats |
| **Fixture** | `@pytest.fixture`; injected by argument name; `yield` splits setup/teardown |
| **Fixture scope** | `function` (default) → `class` → `module` → `session`; can't narrow-in-broad |
| **`conftest.py`** | Auto-discovered; shares fixtures across a directory tree, no import |
| **`@pytest.mark.parametrize`** | One test, many input rows; each row is its own pass/fail |
| **Stacked parametrize** | Multiplies — all combinations run |
| **`hypothesis` (`@given`)** | Property-based testing — generates hundreds of inputs to test an invariant, not a specific example |
| **`Mock`/`MagicMock`** | Stand-in object; `return_value`, `side_effect`; asserts on calls |
| **`patch`** | Swap a name for the test's duration; patch where it's *used* |
| **`monkeypatch`** | pytest-native patch for env vars/attributes; auto-reverts |
| **`responses`** | Mocks HTTP calls made via `requests`/similar |
| **Test doubles** | Dummy / stub / fake / spy / mock — state vs. behavior verification |
| **Non-deterministic output** | Assert schema/structure/presence, not exact text; mock for logic tests |
| **Evals vs. unit tests** | Unit tests check your code; evals (Step 30/76) grade the model's answer |
| **Markers** | `skip`, `skipif`, `xfail`; register custom ones in `pyproject.toml` |
| **`pytest-cov`** | `--cov-report=term-missing`; a floor to check, not a target to max |

---

## Theory Summary

**A test is Arrange–Act–Assert, automated.** Set up inputs, call one thing, check the result — no human, no delay, same result every time. That repeatability is the entire value proposition; catching today's bug is a bonus.

**Fixtures are dependency injection, not `setUp`.** A test declares what it needs by argument name; pytest resolves and injects it. Scope controls how long the injected thing lives — narrow by default, widen only for genuinely expensive shared resources, and never let a broad scope depend on a narrow one.

**Test doubles are five different things wearing one name.** Whether you need a stub (canned answer), a fake (working simplified version), or a mock (verifies it was called correctly) depends on whether you're checking the *result* or the *interaction*. `unittest.mock.Mock` can build any of them — know which one you're actually building.

**Untestable code is usually a design problem, not a testing problem.** Code that imports and constructs its own dependencies at the top of the file fights every mocking tool you throw at it. Code that receives its dependencies as arguments is trivially testable. When mocking feels like a fight, the fix is often to change the code, not to find a cleverer patch.

**Non-determinism changes what you assert, not whether you can test.** You can't pin exact LLM text, but you can pin schema, structure, and — most importantly — your own parsing and error-handling logic, by mocking the model's response to a fixed value and testing everything downstream of it deterministically. Judging whether the model's actual answer is *good* is a separate discipline (evals, Step 30/76) with its own tools; don't build that into your pytest suite.

**Coverage is a smoke detector, not a scoreboard.** It tells you what code never ran during any test — genuinely useful for finding forgotten paths. It says nothing about whether your assertions were worth writing. Optimize for tests that would actually catch a real bug, not for a coverage percentage.

---

## Deliverable

**`Phase 0/step13-pytest/`** — a small, dependency-free module plus its full test suite, built to be copy-pasted into any future project that calls an LLM API (Project 1 onward):

- **`llm_utils.py`** — two small, dependency-injected functions with no hardcoded SDK imports:
  - `ask(client, question: str) -> str` — calls `client.complete(question)` and returns the text.
  - `retry(func, attempts: int = 3, exceptions=(Exception,))` — calls `func()`, retrying on failure up to `attempts` times, re-raising the last exception (reuses the decorator pattern from [Step 11](Phase%200/Step11-Generators-Decorators-ContextManagers.md)).
- **`test_llm_utils.py`** covering every subtopic in this step:
  - plain `assert` tests and a `pytest.raises` test for `ask` with a bad client (13.1)
  - a `fake_client` fixture (stub, per 13.2) plus a `conftest.py` if you split it out
  - `@pytest.mark.parametrize` over several question/answer pairs (13.3)
  - a `Mock`-based test asserting `client.complete` was called exactly once with the right argument — no real network call anywhere in the file (13.4)
  - a non-deterministic-output test: mock `client.complete` to return varying text across calls, and assert `ask` returns a non-empty string of the right type each time — not a fixed value (13.5)
  - one `@pytest.mark.skip`/`xfail` example, and a `pyproject.toml` snippet registering a custom marker (13.6)
- Run `pytest -v --cov=llm_utils --cov-report=term-missing` and confirm every line runs green with no live network call — check with `pytest --co -q` first to see what would run, and grep the test file for `requests`/`anthropic`/`openai` imports to prove there are none.

This is the pattern — dependency-injected function, fixture-provided fake client, mocked call, structural assertion — you'll reuse for every LLM-calling module for the rest of the course.

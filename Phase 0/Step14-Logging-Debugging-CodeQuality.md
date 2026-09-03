# Step 14: Logging, Debugging & Code Quality

Three tools, three different questions:

| Question | Tool | Runs your code? |
|---|---|---|
| Right output? | Tests (Step 13) | Yes |
| Obviously wrong/sloppy (unused imports, undefined names)? | Linter (Ruff) | No |
| Types consistent (`str` where `int` expected)? | Type checker (mypy) | No |

All three are complementary — none replaces the others.

---

## 14.1 — The `logging` Module

`print()` has no severity, timestamp, destination, or off switch. It breaks once code runs in a container, a cron job, or concurrently.

```python
import logging

logging.debug("loading %s", path)          # fine-grained, off by default
logging.info("loaded %d chars", len(text)) # normal operation
logging.warning("transcript is short")     # suspicious, not broken
logging.error("failed to parse %s", path)  # something failed
logging.critical("out of disk")            # app can't continue
```

| Level | Value | Use for |
|---|---|---|
| `DEBUG` | 10 | Detail while investigating |
| `INFO` | 20 | Normal things happened |
| `WARNING` | 30 | Unexpected, not broken (default threshold) |
| `ERROR` | 40 | Something failed |
| `CRITICAL` | 50 | Can't continue |

The point of levels: they're a filter you change *without touching code* — `WARNING` in prod, `DEBUG` while chasing a bug.

**Logger + handler + formatter:**

```python
import logging

logger = logging.getLogger(__name__)   # same name -> same object, dotted hierarchy
logger.setLevel(logging.DEBUG)

console = logging.StreamHandler()      # decides WHERE a log goes
console.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
logger.addHandler(console)             # MISS THIS = nothing prints

logger.debug("loading %s", "transcript.txt")
```

- `getLogger(__name__)` returns the same object for the same name; names form a hierarchy that propagates up to the root logger.
- **Handler** = destination (`StreamHandler`, `FileHandler`). **Formatter** = what the line looks like.
- In library code, add `logging.getLogger(__name__).addHandler(logging.NullHandler())` instead of real handlers — output format belongs to the app, not the library.

**Real apps configure once with `dictConfig`:**

```python
import logging.config

logging.config.dictConfig({
    "version": 1,
    "formatters": {"default": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "default"}},
    "root": {"level": "INFO", "handlers": ["console"]},
})
```

---

## 14.2 — Structured Logging & Correlation IDs

Plain-text logs interleave when requests run concurrently, with no way to tell them apart. **Structured logging** emits key-value pairs (JSON) instead of prose:

```python
import structlog
log = structlog.get_logger()

log.info("transcript_processed", chars=4213, request_id="a1b2c3", duration_ms=340)
# {"event": "transcript_processed", "chars": 4213, "request_id": "a1b2c3", ...}
```

A **correlation ID** is a unique value per request attached to every log line from that request. Use `contextvars` (async/thread-safe) + a `logging.Filter` so the ID rides along automatically:

```python
import contextvars, logging, uuid

request_id_var = contextvars.ContextVar("request_id", default="-")

class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True

logging.getLogger().addFilter(RequestIdFilter())
# format: "%(asctime)s [%(request_id)s] %(levelname)s %(message)s"

def handle_request(transcript):
    request_id_var.set(str(uuid.uuid4())[:8])
    logging.info("loading transcript")   # auto-tagged with this request's ID
    logging.info("done")
```

Write to `stdout` as structured events; let the infrastructure (Docker/K8s/aggregator) route and store them.

---

## 14.3 — Debugging: `pdb` vs `cProfile`

```python
def summarize(transcript):
    cleaned = transcript.strip()
    breakpoint()          # pauses here, drops into pdb
    return call_llm(cleaned)
```

```
(Pdb) p cleaned       # print any expression
(Pdb) n               # next line (no stepping into calls)
(Pdb) s               # step INTO the next call
(Pdb) c               # continue
```

**Post-mortem** after a crash: `pdb.pm()` jumps into the state at the last exception — no rerun needed.

| Symptom | Tool |
|---|---|
| Wrong output / crash / unexpected value | Debugger (`breakpoint()`/`pdb`) |
| Correct but slow | Profiler (`cProfile`) |
| Know what happened after the fact | Logs |

```bash
python -m cProfile -s cumulative main.py
```

---

## 14.4 — Ruff & mypy

```bash
ruff check .      # linter: unused imports, undefined names, style
ruff format .     # formatter: consistent style (like Black)
```

```toml
# pyproject.toml
[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I"]
```

Ruff catches "sloppy or definitely wrong." **mypy** catches "internally inconsistent" by checking types without running code:

```python
def get_timeout(config: dict[str, int]) -> int:
    return config.get("timeout", "30")   # returns int | str, but annotated -> int
```

```
$ mypy config.py
config.py:2: error: Incompatible return value type (got "int | str", expected "int")
```

Run both — different bug classes. mypy is gradual: unannotated code gets minimal checking.

---

## 14.5 — Pre-commit Hooks

Automates "did you remember to run the checks" at commit time:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.0
    hooks:
      - id: mypy
```

```bash
pip install pre-commit
pre-commit install     # wires hooks into .git/hooks, one-time per clone
```

After that, every `git commit` runs Ruff and mypy on staged files first. It's a fast local gate, not a guarantee — bypassable with `--no-verify` (CI in Step 71 is the real backstop).

---

## Key Pitfalls

- **Never log secrets/PII** — API keys, tokens, raw user data end up in aggregators.
- **Lazy formatting:** use `logger.debug("loaded %s", expensive_call())`, not `f"...{expensive_call()}"` — the f-string runs even when DEBUG is off.
- **Forgetting `addHandler`** = zero output, zero errors.
- **Log-and-swallow:** `except: logger.error(e)` without re-raising hides the failure from callers.
- **Correlation ID as plain global** (not `contextvars`) leaks IDs across concurrent requests.
- **mypy's silence isn't proof** — it only checks what's annotated.

---

## Deliverable

**`Phase 0/step14-logging/`** — a reusable setup you'll import from here on:

- **`log_setup.py`** — `configure_logging(level="INFO", json=False)` that:
  - Uses `dictConfig` for a console handler + formatter.
  - Adds the `contextvars` correlation-ID filter, with `request_id` in the format string.
  - `json=True` swaps to structured/JSON output without touching call sites.
- **`pyproject.toml`** — Ruff (lint + format) and minimal mypy config, clean against `log_setup.py`.
- **`.pre-commit-config.yaml`** — Ruff + mypy as commit hooks. Run `pre-commit install`, then make one bad commit (unused import) to confirm it's blocked.
- **Prove it:** a five-line script importing `configure_logging`, setting a fake request ID, logging at a couple levels with `level="DEBUG"` vs `level="WARNING"` — confirm the DEBUG line disappears with only a config-argument change.

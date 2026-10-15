"""Tracing: reuse Step 31's span emitter to record what a run actually did.

The tracer is not rewritten here — it is **loaded from its step folder**. Two
things make that harder than a normal import, and both are worth knowing because
they are what "reusing your own code" actually looks like:

1. The folder is `step31-tracing`, and a hyphen is not legal in a Python package
   name, so `import step31-tracing.tracing` cannot exist. Loading the file by
   location is the standard way around that.
2. The module computes its output directory from its own file position, so used
   as-is it would write traces into Step 31's folder. A dependency should write
   where *the caller* lives, so `TRACE_DIR` is repointed below.

Tracing is deliberately optional: if Step 31's file is missing (someone clones
only this project), every span becomes a no-op and the agent still runs. A
debugging aid must never be the reason a run fails.
"""
from __future__ import annotations

import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from config import BASE_DIR

# This project's traces. Assigned onto the loaded module so its writer lands here.
TRACE_DIR = BASE_DIR / "traces"

# Two levels up from this project: PROJECTS/Project-3-... -> PROJECTS -> Phase 1(AI).
_STEP31_PATH = BASE_DIR.parent.parent / "STEP 31" / "step31-tracing" / "tracing.py"


class _NullSpan:
    """Stand-in span used when tracing is unavailable."""

    trace_id = ""

    def set(self, key: str, value: Any) -> "_NullSpan":
        """Accept attributes and discard them, so call sites need no branching."""
        return self

    def record_content(self, *args: Any, **kwargs: Any) -> None:
        pass

    def record_error(self, exc: Exception) -> None:
        pass


@contextmanager
def _null_span(name: str, kind: str = "INTERNAL", **attrs: Any):
    yield _NullSpan()


def _load_step31():
    """Import Step 31's tracing.py by file path. Returns None if it isn't there."""
    if not _STEP31_PATH.exists():
        return None
    spec = importlib.util.spec_from_file_location("step31_tracing", Path(_STEP31_PATH))
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    # Register the module *before* executing it. Decorators that look their own
    # module up by name — `@dataclass` does, via `cls.__module__` — crash with a
    # bare AttributeError otherwise, because a module built from a spec is not in
    # sys.modules until someone puts it there. (Found by running it.)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_STEP31 = _load_step31()

ENABLED = _STEP31 is not None

if _STEP31 is not None:
    _STEP31.TRACE_DIR = TRACE_DIR
    span = _STEP31.span
    set_capture_content = _STEP31.set_capture_content
else:

    def span(name: str, kind: str = "INTERNAL", **attrs: Any):  # noqa: ARG001
        """Fallback: every span is a no-op when Step 31's module is unavailable."""
        return _null_span(name, kind, **attrs)

    def set_capture_content(on: bool) -> None:  # noqa: ARG001
        """Fallback: nothing to configure."""
        return None

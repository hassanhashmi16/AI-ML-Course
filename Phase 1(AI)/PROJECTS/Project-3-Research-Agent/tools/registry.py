"""The tool registry — the one place tools are declared, validated, and called.

Why this exists: the agent loop must never know what any tool *is*. It asks the
registry for the schemas to show the model, and hands every call back to the
registry to execute. Adding a tool later is then a pure addition — no loop edit.

Two lessons from Step 32 are built into this file:

- **The schema is the interface (32.1).** What the model sees is `name`,
  `description`, and a JSON-schema `parameters` block. The description is written
  *for the model* (32.5): a vague one is the most common reason an agent "just
  won't use" a tool it needs.
- **Errors are observations, not crashes (32.5, 32.8).** `dispatch` never raises
  at the loop. A malformed call returns a short error *string* that goes back as
  the tool result, so the model can correct itself on the next turn. A tool bug
  that kills the process is how you get an agent that dies on its first bad call.
"""
from __future__ import annotations

from typing import Callable, TypedDict

from config import MAX_TOOL_RESULT_CHARS


class ToolSpec(TypedDict):
    """Everything the registry needs to expose one tool."""
    name: str                # how the model refers to it (snake_case, verb-first)
    description: str         # written for the model, not for humans
    parameters: dict         # JSON-schema object: properties + required
    fn: Callable[..., str]   # the plain Python function that does the work


# name -> spec, for every tool the agent may call. Populated at import time by
# each tool module calling `register`, so there is no central list to maintain.
TOOLS: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> None:
    """Add one tool to the registry.

    Called at import time by each tool module (Steps 4-7). Re-registering the
    same name overwrites it, which is what you want during development: edit a
    tool, re-import, done.
    """
    TOOLS[spec["name"]] = spec


def get_schemas() -> list[dict]:
    """The tool declarations to send with each model call.

    Only the model-facing fields — never `fn`, which is neither serializable nor
    something the model should ever see.
    """
    return [
        {
            "name": spec["name"],
            "description": spec["description"],
            "parameters": spec["parameters"],
        }
        for spec in TOOLS.values()
    ]


def dispatch(name: str, args: dict) -> str:
    """Execute a tool call and ALWAYS return a string.

    Every failure path returns a self-describing error rather than raising,
    because the return value becomes the next observation the model reads.
    Success and failure are the same kind of thing to the loop — which is the
    entire trick that makes tool-using agents robust.
    """
    spec = TOOLS.get(name)
    if spec is None:
        return (
            f"ERROR: unknown tool '{name}'. "
            f"Available tools: {', '.join(sorted(TOOLS)) or '(none registered)'}"
        )

    # Validate before calling: a clear message beats a TypeError five frames deep.
    problem = _validate(args, spec["parameters"])
    if problem is not None:
        return f"ERROR: invalid arguments for '{name}': {problem}"

    try:
        result = spec["fn"](**args)
    except TypeError as exc:
        # Reached when the model invents a parameter name — the most common
        # malformed call in practice, so it gets its own message.
        return f"ERROR: '{name}' called with wrong arguments: {exc}"
    except Exception as exc:  # noqa: BLE001 — deliberate: no tool bug may kill a run
        return f"ERROR: '{name}' raised {type(exc).__name__}: {exc}"

    text = result if isinstance(result, str) else str(result)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        # Protect the context window: one huge result can crowd out everything
        # else the model needs to see, and it is almost never useful in full.
        text = text[:MAX_TOOL_RESULT_CHARS] + "\n[...truncated]"
    return text


# JSON-schema "type" -> the Python type(s) that satisfy it.
_JSON_TYPES: dict[str, type | tuple] = {
    "string": str,
    "integer": int,
    "number": (int, float),  # a whole number is a valid "number"
    "boolean": bool,
}


def _validate(args: dict, parameters: dict) -> str | None:
    """Minimal schema check: required keys present, values the declared type.

    Deliberately minimal. It covers the mistakes a model actually makes — a
    missing key, a number where a string belongs — not the whole JSON-schema
    spec. Returns an error message, or None when the call looks fine.
    """
    for key in parameters.get("required", []):
        if key not in args:
            return f"missing required argument '{key}'"

    properties = parameters.get("properties", {})
    for key, value in args.items():
        expected = properties.get(key, {}).get("type")
        allowed = _JSON_TYPES.get(expected)
        # bool is a subclass of int in Python, so reject it explicitly where an
        # integer is expected; otherwise True would silently pass as 1.
        if allowed is int and isinstance(value, bool):
            return f"argument '{key}' should be an integer"
        if allowed is not None and not isinstance(value, allowed):
            return f"argument '{key}' should be a {expected}"
    return None

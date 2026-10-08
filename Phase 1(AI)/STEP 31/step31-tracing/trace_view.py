"""Read a trace and print the waterfall (31.2).

This is the tool you reach for when an answer is wrong. Read it in this order:

  1. total latency, then the WIDEST bar  -> where the time went
  2. tokens per span                     -> where the money went
  3. attributes on the failing span      -> retrieve/rerank FIRST, not the prompt

Run:  python trace_view.py [traces/<trace_id>.jsonl]
      (no argument -> the most recent trace)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TRACE_DIR = Path(__file__).parent / "traces"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def tokens_of(span: dict) -> int:
    """Token spend attached to a span, per the GenAI convention."""
    attrs = span["attributes"]
    return int(attrs.get("gen_ai.usage.input_tokens", 0)) + int(
        attrs.get("gen_ai.usage.output_tokens", 0)
    )


def main() -> None:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        files = sorted(TRACE_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        if not files:
            sys.exit("no traces yet - run `python demo.py` first")
        path = files[-1]

    spans = load(path)
    by_id = {s["span_id"]: s for s in spans}
    children: dict[str | None, list[dict]] = {}
    for s in spans:
        children.setdefault(s["parent_span_id"], []).append(s)

    root = next(s for s in spans if s["parent_span_id"] is None)
    total_ms = root["duration_ms"] or 1.0
    total_tokens = sum(tokens_of(s) for s in spans)
    # The root span contains every child, so it is always the longest. The useful
    # answer to "what was slow" is the slowest span that is NOT the wrapper.
    leaves = [s for s in spans if s["parent_span_id"]] or spans
    slowest = max(leaves, key=lambda s: s["duration_ms"])

    print(f"trace {root['trace_id'][:12]}...   {total_ms / 1000:.2f}s   {total_tokens:,} tokens\n")

    def walk(s: dict, prefix: str, is_last: bool, is_root: bool) -> None:
        connector = "" if is_root else ("\\- " if is_last else "|- ")
        toks = tokens_of(s)
        share = s["duration_ms"] / total_ms * 100
        flags = []
        if s is slowest:
            flags.append("<- slowest")
        if s["status"] == "ERROR":
            flags.append("<- ERROR: " + s["attributes"].get("error.message", "")[:48])
        # Pad the whole indented label, not just the name, so the columns line up
        # regardless of how deep the span sits.
        label = f"{prefix}{connector}{s['name']}"
        print(
            f"{label:<24}{s['kind']:<10}"
            f"{s['duration_ms'] / 1000:>6.2f}s"
            f"{(f'{toks:,} tok' if toks else ''):>11}"
            f"{share:>6.0f}%"
            f"  {' '.join(flags)}"
        )

        kids = children.get(s["span_id"], [])
        for i, kid in enumerate(kids):
            # Children indent under their parent. A parent's vertical bar only keeps
            # going if that parent was NOT the last of its own siblings.
            kid_prefix = prefix + ("" if is_root else ("   " if is_last else "|  "))
            walk(kid, kid_prefix, i == len(kids) - 1, False)

    walk(root, "", True, True)

    # The summary line is the part a dashboard would alert on.
    print(
        f"\nslowest: {slowest['name']} ({slowest['duration_ms'] / 1000:.2f}s, "
        f"{slowest['duration_ms'] / total_ms * 100:.0f}% of the request)"
    )
    errors = [s for s in spans if s["status"] == "ERROR"]
    if errors:
        print(f"failed spans: {', '.join(s['name'] for s in errors)}")
    print(f"content captured: {'yes' if any(s['events'] for s in spans) else 'no (structure only)'}")


if __name__ == "__main__":
    main()

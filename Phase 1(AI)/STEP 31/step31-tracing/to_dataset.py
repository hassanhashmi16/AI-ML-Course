"""Promote a trace into an eval case (31.3) - the flywheel.

    bad production run  ->  trace  ->  dataset row  ->  eval (Step 30)  ->  CI gate

This script does the middle hop: it reads a trace, pulls out the question and the
chunks that were retrieved, and appends a row to a golden-set file. It CANNOT fill in
the reference answer, because deciding what is right is the one step a machine must
not do - so it writes a placeholder and tells you to fill it in.

Run:  python to_dataset.py [traces/<trace_id>.jsonl] [--out golden_from_traces.jsonl]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TRACE_DIR = Path(__file__).parent / "traces"
PLACEHOLDER = "FILL ME IN - read the retrieved chunks and write the correct answer"


def main() -> None:
    parser = argparse.ArgumentParser(description="Turn a trace into a dataset row.")
    parser.add_argument("trace", nargs="?", help="trace file (default: most recent)")
    parser.add_argument("--out", default="golden_from_traces.jsonl")
    args = parser.parse_args()

    if args.trace:
        path = Path(args.trace)
    else:
        files = sorted(TRACE_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        if not files:
            raise SystemExit("no traces yet - run `python demo.py` first")
        path = files[-1]

    spans = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    question = next(
        (s["attributes"]["input.question"] for s in spans if "input.question" in s["attributes"]),
        None,
    )
    chunk_ids = next(
        (s["attributes"]["retrieval.chunk_ids"] for s in spans if "retrieval.chunk_ids" in s["attributes"]),
        [],
    )
    errored = [s["name"] for s in spans if s["status"] == "ERROR"]

    if question is None:
        raise SystemExit(
            "this trace has no `input.question` attribute. The question is user content,\n"
            "so it is only present when content capture was on - see tracing.set_capture_content()."
        )

    row = {
        "question": question,
        "reference": PLACEHOLDER,
        "type": "from-trace",
        "source_trace": spans[0]["trace_id"],
        "retrieved_chunk_ids": chunk_ids,
    }
    if errored:
        row["note"] = f"failed spans: {', '.join(errored)}"

    out = Path(args.out)
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")

    print(f"appended 1 row to {out.resolve()}")
    print(f"  question : {question}")
    print(f"  chunks   : {chunk_ids}")
    if errored:
        print(f"  note     : failed spans - {', '.join(errored)}")
    print(f"\nNEXT: open the trace, read the retrieved chunks, and replace `reference`\n"
          f"with the correct answer. That is the only part a machine cannot do - and it\n"
          f"is what turns this run into a test that guards it forever.")


if __name__ == "__main__":
    main()

"""Run an instrumented version of Project 2's pipeline.

The stage names and attributes mirror the real pipeline exactly, so the trace this
produces looks like the one the real app produces:

    ask
     |- rewrite        CLIENT   (a model call)
     |- retrieve       INTERNAL
     |   |- dense.search   CLIENT  (a database call)
     |   \\- sparse.search  CLIENT  (a database call)
     |- rerank         CLIENT   (a model call)
     \\- generate       CLIENT   (a model call)

To instrument the real project, replace each `_fake_call` with the real function
(`retrieval.rewrite.rewrite_query`, `retrieval.dense.dense_search`, ...) around the
same `with span(...)` blocks. The instrumentation does not change; only the bodies do.

Run:  python demo.py
"""
from __future__ import annotations

import time

from tracing import set_capture_content, span

# Same pin as Project 2's config, so the trace reads like the real thing.
GEMINI_MODEL = "gemini-3.6-flash"
COHERE_RERANK_MODEL = "rerank-v3.5"


def _fake_call(seconds: float) -> None:
    """Stand-in for real work: sleeps so the span has a believable duration."""
    time.sleep(seconds)


def run(question: str, fail_generate: bool = False) -> None:
    """One fully instrumented question, end to end."""
    with span("ask", **{"input.question": question, "input.question_chars": len(question)}) as root:
        # --- rewrite (Step 10): one model call -------------------------------------
        with span("rewrite", kind="CLIENT", **{
            "gen_ai.provider.name": "google",
            "gen_ai.request.model": GEMINI_MODEL,
        }) as s:
            _fake_call(0.6)
            s.set("gen_ai.usage.input_tokens", 210).set("gen_ai.usage.output_tokens", 110)
            s.set("rewrite.query_count", 3)
            s.record_content(prompt=f"rewrite: {question}")

        # --- retrieve (Steps 8, 9, 11): fusion of two retrievers -------------------
        with span("retrieve", **{"retrieval.fused_k": 20}) as ret:
            with span("dense.search", kind="CLIENT", **{"db.system": "postgresql"}) as d:
                _fake_call(0.21)
                d.set("retrieval.k", 20)
                d.set("retrieval.rows", 20)
            with span("sparse.search", kind="CLIENT", **{"db.system": "postgresql"}) as sp:
                _fake_call(0.10)
                sp.set("retrieval.k", 20)
                sp.set("retrieval.rows", 18)
            # Structure, not content: WHICH chunks came back, not what they said.
            ret.set("retrieval.chunk_ids", [101, 42, 188, 7, 93])

        # --- rerank (Step 11): the cross-encoder ------------------------------------
        with span("rerank", kind="CLIENT", **{
            "rerank.provider": "cohere",
            "rerank.model": COHERE_RERANK_MODEL,
        }) as s:
            _fake_call(0.31)
            s.set("rerank.input_count", 20).set("rerank.output_count", 5)
            s.set("rerank.top_score", 0.91)

        # --- generate (Step 13): the answer ----------------------------------------
        with span("generate", kind="CLIENT", **{
            "gen_ai.provider.name": "google",
            "gen_ai.request.model": GEMINI_MODEL,
            "gen_ai.response.model": GEMINI_MODEL,  # may differ from the requested one
        }) as s:
            if fail_generate:
                # The exact failure Project 2 actually hit: the free tier's daily cap.
                _fake_call(0.2)
                raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
            _fake_call(2.72)
            s.set("gen_ai.usage.input_tokens", 2820).set("gen_ai.usage.output_tokens", 140)
            s.set("gen_ai.response.id", "resp_8f21c")
            s.record_content(completion="Annapurna I is the deadliest eight-thousander...")

        root.set("output.answer_chars", 96)


def main() -> None:
    # Content capture is a deliberate, explicit opt-in (dev only). Flip to False and
    # the trace keeps every id, count and timing while dropping all user text.
    set_capture_content(True)

    print("run 1: a healthy question")
    run("which eight-thousander is the deadliest?")

    print("run 2: the same pipeline, generation failing (the 429 we hit for real)")
    try:
        run("how hard is K2 compared to Everest?", fail_generate=True)
    except RuntimeError as exc:
        print(f"  (the trace recorded the failure: {exc})")

    print("\nwrote 2 traces to traces/  ->  inspect with:  python trace_view.py")


if __name__ == "__main__":
    main()

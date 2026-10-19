r"""Exercise Step 15: local traces and public progress events.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_traces.py

Runs a fixture-driven investigation through ``run_with_events`` (scripted
models, no provider calls) and verifies:

  1. The event stream is linked and ordered: run_started, per-stage events
     (model / tools / grading / synthesis), run_finished.
  2. Tool stages name the tools that ran, and durations are recorded.
  3. The JSONL log exists, parses, and matches the emitted events.
  4. Events expose no hidden model reasoning (short messages, scalar data).
  5. The run works without a tracing account; the tracing status is accurate.
"""

import json
import sys
import uuid
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from agent.graph import build_graph  # noqa: E402
from agent.nodes import ClaimSupport, Sufficiency  # noqa: E402
from agent.observability import configure_tracing, run_with_events  # noqa: E402
from agent.persistence import open_checkpointer  # noqa: E402
from agent.state import new_state  # noqa: E402
from agent.tools import ToolContext  # noqa: E402
from api.events import EventKind  # noqa: E402
from config import settings  # noqa: E402
from console import make_stdout_safe  # noqa: E402
from generation.answer import AnswerDraft, DraftClaim  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.collect import Collector  # noqa: E402
from ingest.index import index_records  # noqa: E402
from models import ClaimLabel, InvestigationRequest  # noqa: E402
from retrieval.clients import (  # noqa: E402
    build_embeddings,
    build_sparse_embedding,
    build_vector_store,
    collection_name,
    open_qdrant,
    reset_collection,
)

REPO = "https://github.com/pallets/flask"
EXPECTED_SHA = "b17bb9ed563ab2857c0db9a07ec4e6407404c7be"
PR = 4682
PR_ID = f"github:pallets/flask:pr:{PR}"
QUOTE = "there's no reason to use a `LocalStack` now"  # verbatim in PR #4682
QUESTION = "Why did Flask replace the LocalStack-based context storage?"


class _Return:
    def __init__(self, value):
        self.value = value

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return self.value


class ScriptedLLM:
    """Two scripted tool calls; a fixed answer draft for synthesis."""

    def __init__(self, replies: list[AIMessage], draft: AnswerDraft):
        self.replies = list(replies)
        self.draft = draft

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return self.replies.pop(0) if self.replies else AIMessage(content="done")

    def with_structured_output(self, schema):
        return _Return(self.draft)


def _build_context(repo, snapshot, collector):
    embeddings = build_embeddings()
    sparse = build_sparse_embedding()
    client = open_qdrant()
    collection = collection_name(snapshot)
    store = build_vector_store(
        client, embeddings, collection, sparse_embedding=sparse, mode="hybrid"
    )
    context = ToolContext(
        repo=repo,
        snapshot=snapshot,
        collector=collector,
        client=client,
        embeddings=embeddings,
        sparse_embedding=sparse,
        store=store,
        collection=collection,
    )
    return context, client


def main() -> None:
    make_stdout_safe()
    gh = get_github()
    repo = get_repository(gh, REPO)
    snapshot = resolve_ref(gh, REPO, "2.2.0")
    assert snapshot.sha == EXPECTED_SHA
    request = InvestigationRequest(repository=REPO, question=QUESTION)

    draft = AnswerDraft(
        summary="Traced answer.",
        claims=[
            DraftClaim(
                statement="The PR states there is no reason to use a LocalStack now.",
                label=ClaimLabel.DOCUMENTED,
                source_id=PR_ID,
                quote=QUOTE,
            )
        ],
        unresolved=[],
    )

    collector = Collector(repo, snapshot)
    context, client = _build_context(repo, snapshot, collector)
    try:
        collector.add_file("src/flask/ctx.py")
        collector.add_file("src/flask/globals.py")
        collector.add_pull(PR)
        records = [collector.sources[key] for key in sorted(collector.sources)]
        reset_collection(client, context.embeddings, context.collection)
        index_records(client, context.store, context.collection, snapshot, records, rebuild=True)

        thread = f"check-traces-{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": thread}}
        llm = ScriptedLLM(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "search_evidence",
                         "args": {"query": "LocalStack ContextVar overhead"},
                         "id": "call-1"}
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "read_discussion",
                         "args": {"number": PR},
                         "id": "call-2"}
                    ],
                ),
            ],
            draft,
        )
        with open_checkpointer() as saver:
            graph = build_graph(
                context,
                llm=llm,
                grader_llm=_Return(Sufficiency(sufficient=True)),
                judge_llm=_Return(ClaimSupport(supported=True)),
                checkpointer=saver,
            )
            state = new_state(request, snapshot)
            state["sources"] = dict(collector.sources)
            state["messages"] = [HumanMessage(content=QUESTION)]
            events, result, log_path = run_with_events(
                graph, state, config, thread_id=thread
            )
    finally:
        client.close()
        collector.close()

    # 1) Linked, ordered stream.
    assert events[0].kind is EventKind.RUN_STARTED
    assert events[-1].kind is EventKind.RUN_FINISHED
    stage_names = {event.stage for event in events if event.kind is EventKind.STAGE_FINISHED}
    assert {"model", "tools", "grading", "synthesis"} <= stage_names, stage_names
    print(f"PASS  linked event stream: {[event.stage for event in events]}")

    # 2) Tool stages name their tools; durations recorded.
    tool_events = [
        event
        for event in events
        if event.kind is EventKind.STAGE_FINISHED and event.stage == "tools"
    ]
    tools_run = ", ".join(event.data.get("tools", "") for event in tool_events)
    assert "search_evidence" in tools_run and "read_discussion" in tools_run, tools_run
    stage_events = [e for e in events if e.kind is EventKind.STAGE_FINISHED]
    assert all(e.duration_ms is not None and e.duration_ms >= 0 for e in stage_events)
    assert events[-1].duration_ms is not None
    print(f"PASS  tool stages + durations: {tools_run}")

    # 3) The JSONL log matches the emitted events.
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(events)
    payloads = [json.loads(line) for line in lines]
    assert all(payload["thread_id"] == thread for payload in payloads)
    print(f"PASS  JSONL trace: {log_path.name} ({len(lines)} lines)")

    # 4) No hidden reasoning leaks into public events.
    raw = log_path.read_text(encoding="utf-8")
    assert "You are CodeTrail's investigator" not in raw
    assert all(len(event.message) <= 200 for event in events)
    assert all(
        set(event.data) <= {"tools", "tool_calls", "requested_tools", "grade",
                            "sufficient", "claims", "status", "rounds", "last_grade"}
        for event in events
    )
    print("PASS  events expose progress only (no prompts or completions)")

    # 5) Tracing status is accurate and the run needed no tracing account.
    note = configure_tracing()
    tracing_expected = "on" if (
        settings.langsmith_tracing and settings.langsmith_api_key.get_secret_value()
    ) else "off"
    assert tracing_expected in note, note
    print(f"PASS  tracing status: {note}")
    print(f"      final status: {result['report'].status} | claims: {len(result['report'].claims)}")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

r"""Exercise Step 13: durable checkpoints and resume.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_resume.py

Fixture-driven with scripted models (no provider calls). A run is crashed
inside the investigate node after the first tool step; fresh runtime objects
(the equivalent of a process restart) then resume the same thread from the
SQLite checkpoint. Verified:

  1. The crash leaves a durable checkpoint for the thread.
  2. Resume continues from that checkpoint and finishes the report.
  3. The pre-crash tool call is not repeated: the trail is exactly
     search_evidence then read_discussion.
  4. The index count equals the chunks of the final sources, so the replay
     duplicated no evidence.
"""

import sys
import uuid
from collections import Counter
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from agent.graph import build_graph  # noqa: E402
from agent.nodes import ClaimSupport, Sufficiency  # noqa: E402
from agent.persistence import open_checkpointer, saved_state  # noqa: E402
from agent.state import new_state  # noqa: E402
from agent.tools import ToolContext  # noqa: E402
from console import make_stdout_safe  # noqa: E402
from generation.answer import AnswerDraft, DraftClaim  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.collect import Collector  # noqa: E402
from ingest.documents import to_documents  # noqa: E402
from ingest.index import index_records  # noqa: E402
from ingest.split import split_documents  # noqa: E402
from models import ClaimLabel, InvestigationRequest, Report  # noqa: E402
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
    """A structured-output stub that always returns one value."""

    def __init__(self, value):
        self.value = value

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return self.value


class ScriptedLLM:
    """Tool-calling stub: queued AIMessages for investigate, fixed answer draft.

    With ``crash_when_exhausted`` it raises once the queue is empty -- a crash
    *outside* the grader's protective try/except, so the run actually dies.
    """

    def __init__(self, replies: list[AIMessage], draft: AnswerDraft, crash_when_exhausted=False):
        self.replies = list(replies)
        self.draft = draft
        self.crash_when_exhausted = crash_when_exhausted

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        if not self.replies:
            if self.crash_when_exhausted:
                raise RuntimeError("simulated crash mid-investigation")
            return AIMessage(content="done")
        return self.replies.pop(0)

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
        summary="Resumed answer from durable state.",
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
    thread = f"check-resume-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread}}

    # --- Run 1: one search, then a crash in the grade node.
    collector1 = Collector(repo, snapshot)
    collector1.add_file("src/flask/ctx.py")
    collector1.add_file("src/flask/globals.py")
    records1 = [collector1.sources[key] for key in sorted(collector1.sources)]
    context1, client1 = _build_context(repo, snapshot, collector1)
    try:
        reset_collection(client1, context1.embeddings, context1.collection)
        index_records(
            client1, context1.store, context1.collection, snapshot, records1, rebuild=True
        )
        llm1 = ScriptedLLM(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_evidence",
                            "args": {"query": "LocalStack ContextVar overhead"},
                            "id": "call-1",
                        }
                    ],
                )
            ],
            draft,
            crash_when_exhausted=True,
        )
        with open_checkpointer() as saver:
            graph1 = build_graph(
                context1,
                llm=llm1,
                grader_llm=_Return(Sufficiency(sufficient=True)),
                checkpointer=saver,
            )
            state = new_state(request, snapshot)
            state["sources"] = dict(collector1.sources)
            state["messages"] = [HumanMessage(content=QUESTION)]
            crashed = False
            try:
                graph1.invoke(state, config)
            except Exception as exc:  # simulated crash
                crashed = True
                print(f"PASS  crashed mid-run: {type(exc).__name__}")
            assert crashed, "the fixture was supposed to crash"
            checkpoint = saved_state(saver, thread)
            assert checkpoint is not None, "no durable checkpoint after the crash"
            assert checkpoint.get("tool_calls") == 1
            print(f"PASS  durable checkpoint: tool_calls={checkpoint['tool_calls']}, "
                  f"sources={len(checkpoint.get('sources', {}))}")
    finally:
        client1.close()
        collector1.close()

    # --- Run 2: fresh objects (the restart), same thread and checkpoint file.
    collector2 = Collector(repo, snapshot)
    context2, client2 = _build_context(repo, snapshot, collector2)
    try:
        llm2 = ScriptedLLM(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_discussion",
                            "args": {"number": PR},
                            "id": "call-2",
                        }
                    ],
                )
            ],
            draft,
        )
        with open_checkpointer() as saver:
            graph2 = build_graph(
                context2,
                llm=llm2,
                grader_llm=_Return(Sufficiency(sufficient=True)),
                judge_llm=_Return(ClaimSupport(supported=True)),
                checkpointer=saver,
            )
            result = graph2.invoke(None, config)

        report = result["report"]
        assert isinstance(report, Report) and report.claims, "resume did not finish the report"
        tool_names = [
            call["name"]
            for message in result["messages"]
            if isinstance(message, AIMessage)
            for call in (message.tool_calls or [])
        ]
        assert tool_names == ["search_evidence", "read_discussion"], tool_names
        assert result["tool_calls"] == 2
        print(f"PASS  resumed to a cited report: trail={tool_names} "
              f"(the pre-crash search was not repeated)")

        # 4) Every final source is indexed exactly once (no duplicated evidence).
        #    Counted per source, so unrelated points from earlier checks in the
        #    shared demo collection cannot make this assertion lie.
        points, _ = client2.scroll(
            collection_name=context2.collection, limit=2000, with_payload=True
        )
        stored = Counter(
            point.payload.get("metadata", {}).get("source_id") for point in points
        )
        expected = {
            source_id: len(split_documents(to_documents([record])))
            for source_id, record in result["sources"].items()
        }
        for source_id, count in expected.items():
            assert stored.get(source_id) == count, (
                f"{source_id}: indexed {stored.get(source_id)} point(s), expected {count}"
            )
        print(f"PASS  idempotent evidence: each of {len(expected)} sources "
              f"indexed exactly once across the resume")
    finally:
        client2.close()
        collector2.close()

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

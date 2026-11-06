r"""Exercise Step 11: the LangGraph investigation workflow.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_graph.py

Starts an investigation from a known question, lets the graph drive the model
through its tools, and verifies:

  1. The trail is genuinely multi-hop: at least two tool calls across at least
     two distinct tools, including a history/change/discussion step.
  2. The run ends with the shared Report format, saved to disk and reloadable.
  3. Every claim cites an inspected source with a verbatim quote.

The configured model provider (Groq) handles decisions, grading, and
synthesis; embeddings, sparse search, and reranking stay local.
"""

import sys
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from agent.graph import build_graph  # noqa: E402
from agent.state import new_state  # noqa: E402
from agent.tools import ToolContext  # noqa: E402
from console import make_stdout_safe  # noqa: E402
from generation.answer import save_report  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.collect import Collector  # noqa: E402
from ingest.index import index_records  # noqa: E402
from models import InvestigationRequest, Report  # noqa: E402
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
QUESTION = (
    "Why did Flask replace the LocalStack-based context storage with direct "
    "ContextVar handling?"
)


def main() -> None:
    make_stdout_safe()
    gh = get_github()
    repo = get_repository(gh, REPO)
    snapshot = resolve_ref(gh, REPO, "2.2.0")
    assert snapshot.sha == EXPECTED_SHA

    collector = Collector(repo, snapshot)
    collection = collection_name(snapshot)
    client = open_qdrant()
    try:
        embeddings = build_embeddings()
        sparse = build_sparse_embedding()

        # Start with source files only; the investigator must find the rest.
        collector.add_file("src/flask/ctx.py")
        collector.add_file("src/flask/globals.py")
        records = [collector.sources[key] for key in sorted(collector.sources)]
        reset_collection(client, embeddings, collection)
        store = build_vector_store(
            client, embeddings, collection, sparse_embedding=sparse, mode="hybrid"
        )
        index_records(client, store, collection, snapshot, records, rebuild=True)

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
        graph = build_graph(context)

        state = new_state(
            InvestigationRequest(repository=REPO, question=QUESTION), snapshot
        )
        state["sources"] = dict(collector.sources)  # seed with the initial files
        state["messages"] = [HumanMessage(content=QUESTION)]
        result = graph.invoke(state)
    finally:
        client.close()

    # 1) A real multi-hop trail, recorded in the messages.
    ai_messages = [message for message in result["messages"] if isinstance(message, AIMessage)]
    tool_names = [
        call["name"] for message in ai_messages for call in (message.tool_calls or [])
    ]
    assert result["tool_calls"] >= 2, f"expected a multi-hop trail, got {tool_names}"
    assert len(set(tool_names)) >= 2, f"expected distinct tools, got {tool_names}"
    assert any(name != "search_evidence" for name in tool_names), (
        f"the trail never left search: {tool_names}"
    )
    print(f"PASS  multi-hop trail: {result['tool_calls']} tool call(s) -> {tool_names}")
    print(f"      evidence grade: {[note for note in result['notes'] if note.startswith('evidence grade')]}")

    # 2) The shared Report format, saved and reloadable.
    report = result["report"]
    assert isinstance(report, Report), "the graph did not produce a Report"
    print(f"      unresolved: {report.unresolved}")
    print(f"      failures: {list(result['failures'])}")
    assert report.claims, "the report must contain validated claims"
    path = save_report(report)
    reloaded = Report.model_validate_json(path.read_text(encoding="utf-8"))
    assert len(reloaded.claims) == len(report.claims)
    print(f"PASS  report: status={report.status} | claims={len(report.claims)} | "
          f"saved {path.name} ({path.stat().st_size} bytes)")

    # 3) Every claim's quote is verbatim in the cited, inspected record.
    records_by_id = {record.source_id: record for record in result["sources"].values()}
    for claim in report.claims:
        for excerpt in claim.excerpts:
            record = records_by_id[excerpt.source_id]
            assert excerpt.quote in record.content, "quote is not verbatim"
    labels = ", ".join(sorted({claim.label.value for claim in report.claims}))
    print(f"PASS  citations verbatim against {len(records_by_id)} inspected source(s) "
          f"(labels: {labels})")
    print(f"      summary: {report.summary[:220]}")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

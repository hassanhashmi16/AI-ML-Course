r"""Exercise Step 17: the FastAPI service around the investigation runner.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_api.py

Fixture-driven with scripted models (no provider calls). It first creates an
interrupted investigation (the same crash fixture as Step 13), then drives the
API with FastAPI's TestClient:

  1. /health reports OK.
  2. POST /investigations returns the CLI's Report schema, and the saved file
     is retrievable through /reports/{name}.
  3. /investigations/{id}/events streams the recorded stages over SSE.
  4. POST /investigations/{id}/resume finishes the interrupted run.
  5. Unknown threads and missing reports return 404; bad report names 400.
"""

import sys
import uuid
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from agent.graph import build_graph  # noqa: E402
from agent.nodes import ClaimSupport, Sufficiency  # noqa: E402
from agent.persistence import open_checkpointer  # noqa: E402
from agent.state import new_state  # noqa: E402
from agent.tools import ToolContext  # noqa: E402
from api.main import create_app  # noqa: E402
from api.service import InvestigationService  # noqa: E402
from console import make_stdout_safe  # noqa: E402
from generation.answer import AnswerDraft, DraftClaim  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.collect import Collector  # noqa: E402
from ingest.index import index_records  # noqa: E402
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
    def __init__(self, value):
        self.value = value

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return self.value


class ScriptedLLM:
    """Queued tool-call replies plus a fixed structured answer draft."""

    def __init__(self, replies, draft, crash_when_exhausted=False):
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


class FixtureModels:
    """Model factory for the injected service: one queued run per llm call."""

    def __init__(self):
        self.queue = []

    def add_run(self, replies, draft):
        self.queue.append((list(replies), draft))

    def __call__(self, role):
        if role == "llm":
            replies, draft = self.queue.pop(0)
            return ScriptedLLM(replies, draft)
        if role == "grader":
            return _Return(Sufficiency(sufficient=True))
        return _Return(ClaimSupport(supported=True))


def _tool_call(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def _build_context(repo, snapshot, collector):
    embeddings = build_embeddings()
    sparse = build_sparse_embedding()
    client = open_qdrant()
    collection = collection_name(snapshot)
    store = build_vector_store(
        client, embeddings, collection, sparse_embedding=sparse, mode="hybrid"
    )
    context = ToolContext(
        repo=repo, snapshot=snapshot, collector=collector, client=client,
        embeddings=embeddings, sparse_embedding=sparse, store=store,
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
        summary="API fixture answer.",
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

    # --- Prepare an interrupted investigation (crash after the first tool).
    collector = Collector(repo, snapshot)
    collector.add_file("src/flask/ctx.py")
    collector.add_file("src/flask/globals.py")
    collector.add_pull(PR)
    records = [collector.sources[key] for key in sorted(collector.sources)]
    context, client = _build_context(repo, snapshot, collector)
    interrupted = f"check-api-{uuid.uuid4().hex[:8]}"
    try:
        reset_collection(client, context.collection)
        index_records(client, context.store, context.collection, snapshot, records, rebuild=True)
        crashing = ScriptedLLM(
            [_tool_call("search_evidence", {"query": "LocalStack overhead"}, "call-1")],
            draft,
            crash_when_exhausted=True,
        )
        with open_checkpointer() as saver:
            graph = build_graph(
                context, llm=crashing,
                grader_llm=_Return(Sufficiency(sufficient=True)), checkpointer=saver,
            )
            state = new_state(request, snapshot)
            state["sources"] = dict(collector.sources)
            state["messages"] = [HumanMessage(content=QUESTION)]
            crashed = False
            try:
                graph.invoke(state, {"configurable": {"thread_id": interrupted}})
            except Exception:
                crashed = True
        assert crashed, "the fixture was supposed to interrupt the run"
    finally:
        client.close()
        collector.close()
    print(f"PASS  interrupted run prepared: {interrupted}")

    # --- Drive the service/API with scripted models (no provider calls).
    fixtures = FixtureModels()
    fixtures.add_run(
        [
            _tool_call("search_evidence", {"query": "LocalStack overhead"}, "call-1"),
            _tool_call("read_discussion", {"number": PR}, "call-2"),
        ],
        draft,
    )
    fixtures.add_run(
        [_tool_call("read_discussion", {"number": PR}, "call-2")],
        draft,
    )
    service = InvestigationService(model_factory=fixtures)
    app = create_app(service)

    with TestClient(app) as api:
        health = api.get("/health")
        assert health.status_code == 200 and health.json()["status"] == "ok"
        print(f"PASS  /health: {health.json()}")

        started = api.post(
            "/investigations",
            json={
                "repository": REPO,
                "ref": "2.2.0",
                "question": QUESTION,
                "paths": ["src/flask/ctx.py"],
                "pulls": [PR],
            },
        )
        assert started.status_code == 200, started.text
        body = started.json()
        assert body["status"] == "completed"
        report = Report.model_validate(body["report"])
        assert report.claims
        print(f"PASS  POST /investigations -> {body['thread_id']} "
              f"({report.status}, {len(report.claims)} claim(s))")

        report_name = Path(body["report_path"]).name
        served = api.get(f"/reports/{report_name}")
        assert served.status_code == 200
        Report.model_validate(served.json())
        listing = api.get("/reports")
        assert listing.status_code == 200
        assert report_name in [item["name"] for item in listing.json()["reports"]]
        print(f"PASS  /reports lists and serves the same Report schema: {report_name}")

        with api.stream("GET", f"/investigations/{body['thread_id']}/events") as response:
            assert response.status_code == 200
            text = response.read().decode("utf-8")
        assert "run_started" in text and "stage_finished" in text and "run_finished" in text
        assert text.count("event:") >= 4
        print(f"PASS  SSE events replayed: {text.count('event:')} events")

        status = api.get(f"/investigations/{body['thread_id']}")
        assert status.status_code == 200 and status.json()["report"] is not None

        resumed = api.post(f"/investigations/{interrupted}/resume")
        assert resumed.status_code == 200, resumed.text
        resumed_body = resumed.json()
        resumed_report = Report.model_validate(resumed_body["report"])
        assert resumed_body["status"] == "completed" and resumed_report.claims
        with api.stream("GET", f"/investigations/{interrupted}/events") as response:
            resumed_text = response.read().decode("utf-8")
        assert "run_finished" in resumed_text
        print(f"PASS  POST /resume finished the interrupted run "
              f"({resumed_report.status}, {len(resumed_report.claims)} claim(s))")

        assert api.get("/investigations/does-not-exist").status_code == 404
        assert api.get("/reports/missing.json").status_code == 404
        assert api.get("/reports/not-json.txt").status_code == 400
        print("PASS  guards: unknown thread, missing report, invalid report name")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

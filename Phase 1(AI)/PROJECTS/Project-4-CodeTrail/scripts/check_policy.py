r"""Exercise Step 12: corrective retrieval, grounding, and budgets.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_policy.py

Deterministic fixtures, no model calls. The real PR record comes from the
Step 5 cache; embeddings, search, and reranking run locally.

What is verified:
  1. Budgets stop a run with a reason (tool cap, repeated actions), and a
     spent budget skips grading entirely.
  2. A failed evidence grade routes back for another lookup; a later
     sufficient grade routes to synthesis (the retry loop).
  3. An exhausted budget still produces an honest PARTIAL report that says
     no claim survived validation.
  4. A citation-valid but semantically unsupported claim gets one revision,
     then is downgraded and its statement recorded as unresolved.
"""

import sys
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from langchain_core.messages import AIMessage  # noqa: E402

from agent.nodes import (  # noqa: E402
    MIN_TOOL_CALLS,
    ClaimSupport,
    Sufficiency,
    grade_evidence,
    ground_and_finalize,
    route_after_grade,
    synthesize,
)
from agent.policy import should_stop  # noqa: E402
from agent.state import new_state  # noqa: E402
from agent.tools import ToolContext  # noqa: E402
from config import settings  # noqa: E402
from console import make_stdout_safe  # noqa: E402
from generation.answer import AnswerDraft, DraftClaim  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.collect import Collector  # noqa: E402
from ingest.index import index_records  # noqa: E402
from models import (  # noqa: E402
    Claim,
    ClaimLabel,
    Coverage,
    InvestigationRequest,
    Report,
    ReportStatus,
    SupportingExcerpt,
)
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


class StubGrader:
    """Returns a fixed verdict and records that it was called."""

    def __init__(self, verdict):
        self.verdict = verdict

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return self.verdict


class ExplodingGrader:
    """Fails the fixture if grading is attempted at all."""

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        raise AssertionError("grader must not be called when the budget is spent")


class StubGenerator:
    """Structured-output stub that returns a prepared draft."""

    def __init__(self, draft):
        self.draft = draft

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return self.draft


class NegativeJudge:
    """Grounding judge that never accepts a claim."""

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return ClaimSupport(supported=False, reason="fixture: quote does not establish it")


def main() -> None:
    make_stdout_safe()
    gh = get_github()
    repo = get_repository(gh, REPO)
    snapshot = resolve_ref(gh, REPO, "2.2.0")
    assert snapshot.sha == EXPECTED_SHA
    request = InvestigationRequest(repository=REPO, question="Why did Flask switch context storage?")

    collector = Collector(repo, snapshot)
    collection = collection_name(snapshot)
    client = open_qdrant()
    try:
        embeddings = build_embeddings()
        sparse = build_sparse_embedding()
        collector.add_pull(PR)
        collector.add_reviews(PR)
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

        def fresh_state():
            state = new_state(request, snapshot)
            state["sources"] = dict(collector.sources)
            return state

        # 1) Budgets stop with a reason, and a spent budget skips grading.
        state = fresh_state()
        assert should_stop(state) == (False, "")
        state["tool_calls"] = settings.max_tool_calls
        stopped, reason = should_stop(state)
        assert stopped and "tool budget" in reason
        graded = grade_evidence(state, ExplodingGrader())
        assert any("stopping early" in note for note in graded["notes"])
        assert route_after_grade(state) == "synthesize"
        print(f"PASS  budget stop: {reason} (grader skipped, routed to synthesize)")

        repeated = fresh_state()
        call = {"name": "search_evidence", "args": {"query": "LocalStack"}, "id": "call-1"}
        repeated["messages"] = [
            AIMessage(content="", tool_calls=[call]),
            AIMessage(content="", tool_calls=[call]),
        ]
        stopped, reason = should_stop(repeated)
        assert stopped and "repeated action" in reason
        print(f"PASS  repeated action: {reason}")

        # 2) A failed grade routes back; a later sufficient grade stops.
        retry = fresh_state()
        retry["tool_calls"] = 1
        first = grade_evidence(
            retry,
            StubGrader(Sufficiency(sufficient=False, missing="the reason", next_query="LocalStack overhead")),
        )
        assert first["evidence_sufficient"] is False
        assert any("[grader]" in message.content for message in first["messages"])
        retry["evidence_sufficient"] = False
        retry["messages"] = first["messages"]
        assert route_after_grade(retry) == "investigate"
        retry["tool_calls"] = MIN_TOOL_CALLS
        retry["evidence_sufficient"] = True
        assert route_after_grade(retry) == "synthesize"
        print("PASS  retry loop: insufficient -> investigate, sufficient -> synthesize")

        # 3) An exhausted budget still yields an honest partial report.
        spent = fresh_state()
        spent["tool_calls"] = settings.max_tool_calls
        empty_draft = AnswerDraft(summary="Best effort within budget.", claims=[], unresolved=[])
        outcome = synthesize(spent, context, llm=StubGenerator(empty_draft))
        report = outcome["report"]
        assert report.status is ReportStatus.PARTIAL
        assert report.unresolved, "a partial report must say what is missing"
        print(f"PASS  honest partial: status={report.status} | unresolved={report.unresolved}")

        # 4) Citation-valid but unsupported -> one revision -> downgrade.
        coverage = Coverage(
            repository=REPO, snapshot_sha=EXPECTED_SHA, discussions_read=1, comments_read=2
        )
        claim = Claim(
            statement="The PR says LocalStack is no longer needed.",
            label=ClaimLabel.DOCUMENTED,
            excerpts=[SupportingExcerpt(source_id=PR_ID, quote=QUOTE)],
        )
        report = Report(
            question=request.question,
            snapshot=snapshot,
            status=ReportStatus.COMPLETE,
            summary="fixture",
            claims=[claim],
            coverage=coverage,
        )
        revision_draft = AnswerDraft(
            summary="revised",
            claims=[
                DraftClaim(
                    statement=claim.statement,
                    label=claim.label,
                    source_id=PR_ID,
                    quote=QUOTE,
                )
            ],
            unresolved=[],
        )
        revised, notes = ground_and_finalize(
            report,
            question=request.question,
            snapshot=snapshot,
            records=records,
            documents=[],
            coverage=coverage,
            llm=StubGenerator(revision_draft),
            judge_llm=NegativeJudge(),
        )
        assert revised.status is ReportStatus.PARTIAL
        assert revised.claims == [], "unsupported claims must be downgraded"
        assert any("not supported by its citations" in item for item in revised.unresolved)
        assert any("revision" in note for note in notes)
        assert any("downgraded" in note for note in notes)
        print("PASS  grounding: citation-valid claim rejected semantically, revised, then downgraded")
        print(f"      notes: {notes}")
    finally:
        client.close()

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

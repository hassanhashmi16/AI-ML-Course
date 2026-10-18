"""Service layer: run and resume investigations behind the API.

Everything here is synchronous and blocking; FastAPI runs sync endpoints in
its threadpool, which keeps SDK calls off the event loop. One investigation
may be active at a time (the initial single-process limit): a second start or
resume is refused instead of interleaved.

The service owns the Qdrant client and local embedders for the app's lifetime;
each run owns its own collector and checkpointer connection.
"""

from __future__ import annotations

import threading

from langchain_core.messages import HumanMessage
from pydantic import Field, field_validator

from agent.graph import build_graph
from agent.memory import save_findings
from agent.observability import run_with_events
from agent.persistence import new_thread_id, open_checkpointer, saved_state
from agent.state import new_state
from agent.tools import ToolContext
from generation.answer import build_llm, save_report
from github_source.client import get_github, get_repository, resolve_ref
from github_source.code import discover_files
from github_source.collect import Collector
from ingest.index import index_records
from models import (
    Contract,
    InvestigationRequest,
    RepoSnapshot,
    SourceRecord,
    canonical_repo_url,
)
from retrieval.clients import (
    build_embeddings,
    build_sparse_embedding,
    build_vector_store,
    collection_name,
    open_qdrant,
)


class RunBusy(RuntimeError):
    """Another investigation is already running; the initial limit is one."""


class InvestigationRequestIn(Contract):
    """The API's request body (validated before any GitHub access)."""

    repository: str
    question: str = Field(min_length=1)
    ref: str | None = None
    paths: list[str] = Field(default_factory=list)
    pulls: list[int] = Field(default_factory=list)

    @field_validator("repository")
    @classmethod
    def _canonical(cls, value: str) -> str:
        return canonical_repo_url(value)


def _resolve(repository: str, ref: str | None):
    gh = get_github()
    repo = get_repository(gh, repository)
    snapshot = resolve_ref(gh, repository, ref)
    return repo, snapshot


class InvestigationService:
    """One process, one active investigation, shared local clients."""

    def __init__(self, *, model_factory=None, client=None) -> None:
        self.client = client or open_qdrant()
        self.embeddings = build_embeddings()
        self.sparse_embedding = build_sparse_embedding()
        self.model_factory = model_factory or (lambda role: build_llm())
        self.runs: dict[str, dict] = {}
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    def close(self) -> None:
        self.client.close()

    def _context(self, repo, snapshot, collector) -> ToolContext:
        collection = collection_name(snapshot)
        store = build_vector_store(
            self.client,
            self.embeddings,
            collection,
            sparse_embedding=self.sparse_embedding,
            mode="hybrid",
        )
        return ToolContext(
            repo=repo,
            snapshot=snapshot,
            collector=collector,
            client=self.client,
            embeddings=self.embeddings,
            sparse_embedding=self.sparse_embedding,
            store=store,
            collection=collection,
        )

    def _record(self, thread: str, result: dict, log_path, collector) -> dict:
        report = result.get("report")
        report_path = None
        if report is not None:
            report_path = save_report(report)
            try:
                save_findings(
                    self.client,
                    self.embeddings,
                    report,
                    dict(collector.sources),
                    thread_id=thread,
                )
            except Exception:  # findings are best-effort; the report is the deliverable
                pass
        record = {
            "thread_id": thread,
            "status": "completed" if report is not None else "incomplete",
            "report": report,
            "report_path": str(report_path) if report_path is not None else None,
            "error": None,
        }
        self.runs[thread] = record
        return record

    def start(self, payload: InvestigationRequestIn) -> dict:
        """Collect, index, and run one investigation to completion."""
        if not self._lock.acquire(blocking=False):
            raise RunBusy("another investigation is running")
        try:
            repo, snapshot = _resolve(payload.repository, payload.ref)
            collector = Collector(repo, snapshot)
            try:
                if payload.paths:
                    for path in payload.paths:
                        collector.add_file(path)
                else:
                    discovered, _warning = discover_files(repo, snapshot, limit=10)
                    for path in discovered:
                        collector.add_file(path)
                for number in payload.pulls:
                    collector.add_pull(number)
                    collector.add_reviews(number)

                context = self._context(repo, snapshot, collector)
                index_records(
                    self.client,
                    context.store,
                    context.collection,
                    snapshot,
                    list(collector.sources.values()),
                )
                thread = new_thread_id(snapshot)
                config = {"configurable": {"thread_id": thread}}
                with open_checkpointer() as saver:
                    graph = build_graph(
                        context,
                        llm=self.model_factory("llm"),
                        grader_llm=self.model_factory("grader"),
                        judge_llm=self.model_factory("judge"),
                        checkpointer=saver,
                    )
                    state = new_state(
                        InvestigationRequest(
                            repository=payload.repository, question=payload.question
                        ),
                        snapshot,
                    )
                    state["sources"] = dict(collector.sources)
                    state["messages"] = [HumanMessage(content=payload.question)]
                    _events, result, log_path = run_with_events(
                        graph, state, config, thread_id=thread
                    )
                return self._record(thread, result, log_path, collector)
            finally:
                collector.close()
        finally:
            self._lock.release()

    def resume(self, thread: str) -> dict:
        """Continue an interrupted investigation from its checkpoint."""
        if not self._lock.acquire(blocking=False):
            raise RunBusy("another investigation is running")
        try:
            with open_checkpointer() as saver:
                saved = saved_state(saver, thread)
                if saved is None:
                    raise LookupError(thread)
                request = saved["request"]
                snapshot = saved["snapshot"]
                repo, _ = _resolve(request.repository, None)

                collector = Collector(repo, snapshot)
                collector.sources.update(
                    {
                        source_id: (
                            record
                            if isinstance(record, SourceRecord)
                            else SourceRecord.model_validate(record)
                        )
                        for source_id, record in saved.get("sources", {}).items()
                    }
                )
                try:
                    context = self._context(repo, snapshot, collector)
                    index_records(
                        self.client,
                        context.store,
                        context.collection,
                        snapshot,
                        list(collector.sources.values()),
                    )
                    graph = build_graph(
                        context,
                        llm=self.model_factory("llm"),
                        grader_llm=self.model_factory("grader"),
                        judge_llm=self.model_factory("judge"),
                        checkpointer=saver,
                    )
                    _events, result, log_path = run_with_events(
                        graph,
                        None,
                        {"configurable": {"thread_id": thread}},
                        thread_id=thread,
                    )
                    return self._record(thread, result, log_path, collector)
                finally:
                    collector.close()
        finally:
            self._lock.release()

    def status(self, thread: str) -> dict:
        """A finished run's record, or `interrupted` when only a checkpoint exists."""
        record = self.runs.get(thread)
        if record is not None:
            return record
        with open_checkpointer() as saver:
            saved = saved_state(saver, thread)
        if saved is None:
            raise LookupError(thread)
        return {
            "thread_id": thread,
            "status": "interrupted",
            "report": None,
            "report_path": None,
            "error": None,
        }

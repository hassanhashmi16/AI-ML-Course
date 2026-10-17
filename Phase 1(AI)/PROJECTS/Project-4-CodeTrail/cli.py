"""CodeTrail command line: run or resume an investigation.

    python cli.py investigate --repo URL [--ref REF] [--path FILE ...] \
        [--pull N ...] --question "..." [--thread ID]
    python cli.py resume --thread ID

Investigations are checkpointed to data/checkpoints.sqlite after every graph
step. The thread ID is printed when a run starts; keep it to resume an
interrupted investigation later.
"""

from __future__ import annotations

import argparse

from langchain_core.messages import HumanMessage

from agent.graph import build_graph
from agent.memory import save_findings
from agent.observability import configure_tracing, run_with_events
from agent.persistence import new_thread_id, open_checkpointer, saved_state
from agent.state import new_state
from agent.tools import ToolContext
from console import make_stdout_safe
from generation.answer import save_report
from github_source.client import get_github, get_repository, resolve_ref
from github_source.collect import Collector
from ingest.index import index_records
from models import InvestigationRequest, SourceRecord
from retrieval.clients import (
    build_embeddings,
    build_sparse_embedding,
    build_vector_store,
    collection_name,
    open_qdrant,
)


def _repository_and_snapshot(repository: str, ref: str | None):
    gh = get_github()
    repo = get_repository(gh, repository)
    snapshot = resolve_ref(gh, repository, ref)
    return repo, snapshot


def _context(repo, snapshot, collector):
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


def _print_report(result: dict, *, context=None, records=None, thread_id=None) -> None:
    report = result.get("report")
    if report is None:
        print("no report produced; inspect the thread or resume again")
        return
    path = save_report(report)
    message = f"report: {path}\nstatus: {report.status} | claims: {len(report.claims)}"
    if context is not None:
        finding_ids = save_findings(
            context.client,
            context.embeddings,
            report,
            records or {},
            thread_id=thread_id,
        )
        message += f" | findings saved: {len(finding_ids)}"
    print(message)


def investigate(args) -> None:
    """Start a new investigation on a fresh thread."""
    repo, snapshot = _repository_and_snapshot(args.repo, args.ref)
    collector = Collector(repo, snapshot)
    try:
        for path in args.path:
            collector.add_file(path)
        for number in args.pull:
            collector.add_pull(number)
            collector.add_reviews(number)
        records = [collector.sources[key] for key in sorted(collector.sources)]

        context, client = _context(repo, snapshot, collector)
        try:
            index_records(
                context.client, context.store, context.collection, snapshot, records
            )
            thread = args.thread or new_thread_id(snapshot)
            config = {"configurable": {"thread_id": thread}}
            print(f"thread: {thread}")
            with open_checkpointer() as saver:
                graph = build_graph(context, checkpointer=saver)
                state = new_state(
                    InvestigationRequest(repository=args.repo, question=args.question),
                    snapshot,
                )
                state["sources"] = dict(collector.sources)
                state["messages"] = [HumanMessage(content=args.question)]
                events, result, log_path = run_with_events(
                    graph, state, config, thread_id=thread
                )
            _print_report(
                result,
                context=context,
                records=dict(collector.sources),
                thread_id=thread,
            )
            print(f"events: {len(events)} | log: {log_path}")
        finally:
            client.close()
    finally:
        collector.close()


def resume(args) -> None:
    """Continue a checkpointed investigation from its last durable state."""
    with open_checkpointer() as saver:
        saved = saved_state(saver, args.thread)
        if not saved:
            raise SystemExit(f"no checkpoint for thread: {args.thread}")
        request = saved["request"]
        snapshot = saved["snapshot"]
        repo, _ = _repository_and_snapshot(request.repository, None)

        collector = Collector(repo, snapshot)
        saved_sources = saved.get("sources", {})
        collector.sources.update(
            {
                source_id: (
                    record
                    if isinstance(record, SourceRecord)
                    else SourceRecord.model_validate(record)
                )
                for source_id, record in saved_sources.items()
            }
        )

        context, client = _context(repo, snapshot, collector)
        try:
            # Re-indexing is idempotent; it makes search available even if the
            # crash happened before the first index completed.
            index_records(
                context.client,
                context.store,
                context.collection,
                snapshot,
                list(collector.sources.values()),
            )
            graph = build_graph(context, checkpointer=saver)
            events, result, log_path = run_with_events(
                graph,
                None,
                {"configurable": {"thread_id": args.thread}},
                thread_id=args.thread,
            )
            _print_report(
                result,
                context=context,
                records=dict(collector.sources),
                thread_id=args.thread,
            )
            print(f"events: {len(events)} | log: {log_path}")
        finally:
            client.close()
            collector.close()


def main() -> None:
    make_stdout_safe()
    print(configure_tracing())
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("investigate", help="start an investigation")
    run.add_argument("--repo", required=True, help="public GitHub repository URL")
    run.add_argument("--ref", default=None, help="branch/tag (default: default branch)")
    run.add_argument(
        "--path", action="append", default=[], help="file path to inspect (repeatable)"
    )
    run.add_argument(
        "--pull", action="append", default=[], type=int, help="PR number to inspect (repeatable)"
    )
    run.add_argument("--question", required=True, help="the question to investigate")
    run.add_argument("--thread", default=None, help="explicit thread id (default: generated)")
    run.set_defaults(func=investigate)

    again = commands.add_parser("resume", help="resume a checkpointed investigation")
    again.add_argument("--thread", required=True, help="thread id printed by investigate")
    again.set_defaults(func=resume)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

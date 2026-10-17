"""Baseline RAG answer: one retrieval pass -> a cited, validated Report.

This is the ordinary-RAG baseline that the investigation workflow (Steps 10+)
must beat: retrieve wide, rerank narrow, ask the model for claims **with exact
quotes**, validate those quotes, and assemble the shared ``Report``.

The LLM fills only the content (summary, claims, unresolved); the report's
identity -- snapshot, coverage, timeline -- is assembled deterministically
from inspected records. Nothing the model says is trusted until its citation
passes ``reporting/citations.py``.

Run the baseline with:
    python -m generation.answer --repo https://github.com/pallets/flask --ref 2.2.0 ^
        --pull 4682 --question "Why did Flask replace LocalStack?"
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.documents import Document
from pydantic import Field

from config import settings
from github_source.client import get_github, get_repository, resolve_ref
from github_source.code import discover_files
from github_source.collect import Collector
from ingest.index import index_records
from models import (
    ClaimLabel,
    Contract,
    Coverage,
    Report,
    ReportStatus,
    RepoSnapshot,
    SourceRecord,
    TimelineEvent,
    repo_slug,
)
from reporting.citations import validate_claims
from retrieval.clients import (
    build_embeddings,
    build_sparse_embedding,
    build_vector_store,
    collection_name,
    open_qdrant,
    reset_collection,
)
from retrieval.rerank import rerank_documents
from retrieval.search import search_evidence

PROMPT = """You explain code changes using ONLY the evidence passages below.

Question: {question}

Evidence passages:
{evidence}

Rules:
- Every claim must cite exactly one source_id and include a quote copied
  character-for-character from that passage (no paraphrasing, no ellipses,
  no added punctuation inside the quote).
- label "documented" when the passage states the reason outright; "inferred"
  when it follows from the evidence but is not stated.
- Do not use the label "unknown" for claims -- put anything the evidence does
  not establish into `unresolved`.
- Never invent source IDs. If the evidence cannot answer the question, say so
  in `summary` and list what is missing in `unresolved`.

Return the structured answer."""


class DraftClaim(Contract):
    """What the model is asked for: one statement + one exact quote."""

    statement: str = Field(min_length=1)
    label: ClaimLabel
    source_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class AnswerDraft(Contract):
    """The model's structured answer, before citation validation."""

    summary: str = Field(min_length=1)
    claims: list[DraftClaim] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


def build_llm():
    """The configured generation model (Groq by default)."""
    if settings.gen_provider == "groq":
        api_key = settings.groq_api_key.get_secret_value()
        if not api_key:
            raise ValueError("GEN_PROVIDER=groq requires GROQ_API_KEY in .env")
        from langchain_groq import ChatGroq

        return ChatGroq(model=settings.groq_gen_model, api_key=api_key, temperature=0)
    if settings.gen_provider == "google":
        api_key = settings.gemini_api_key.get_secret_value()
        if not api_key:
            raise ValueError("GEN_PROVIDER=google requires GEMINI_API_KEY in .env")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=settings.gen_model, google_api_key=api_key, temperature=0)
    raise ValueError(f"unsupported GEN_PROVIDER: {settings.gen_provider!r}")


def format_evidence(documents: list[Document]) -> str:
    """Numbered passages with their source identity, as the model will see them."""
    blocks: list[str] = []
    for position, document in enumerate(documents, start=1):
        metadata = document.metadata
        blocks.append(
            f"[{position}] source_id: {metadata['source_id']}\n"
            f"    title: {metadata.get('title', '?')} | kind: {metadata.get('kind')} | "
            f"lines {metadata.get('start_line')}-{metadata.get('end_line')}\n"
            f"    {document.page_content}"
        )
    return "\n\n".join(blocks)


def build_timeline(records: list[SourceRecord], used_ids: set[str]) -> list[TimelineEvent]:
    """Dated events for the sources actually cited, oldest first."""
    events = [
        TimelineEvent(
            date=record.source_date,
            kind=record.kind,
            title=record.title or record.source_id,
            source_id=record.source_id,
        )
        for record in records
        if record.source_id in used_ids and record.source_date is not None
    ]
    return sorted(events, key=lambda event: event.date)


def answer_question(
    question: str,
    snapshot: RepoSnapshot,
    records: list[SourceRecord],
    documents: list[Document],
    coverage: Coverage,
) -> tuple[Report, list[str]]:
    """One retrieval pass -> a validated, cited Report (plus validation issues)."""
    records_by_id = {record.source_id: record for record in records}
    llm = build_llm().with_structured_output(AnswerDraft)
    draft = llm.invoke(PROMPT.format(question=question, evidence=format_evidence(documents)))

    claims, issues = validate_claims(draft.claims, records_by_id)
    used_ids = {excerpt.source_id for claim in claims for excerpt in claim.excerpts}

    unresolved = list(draft.unresolved)
    unresolved.extend(f"citation check: {issue}" for issue in issues)
    if not claims and not unresolved:
        unresolved.append("No claim survived citation validation.")
    status = ReportStatus.COMPLETE if claims and not issues else ReportStatus.PARTIAL
    report = Report(
        question=question,
        snapshot=snapshot,
        status=status,
        summary=draft.summary,
        claims=claims,
        timeline=build_timeline(records, used_ids),
        unresolved=unresolved,
        coverage=coverage,
    )
    return report, issues


def save_report(report: Report) -> Path:
    """Write the report JSON under reports/ (gitignored) and return its path."""
    slug = repo_slug(report.snapshot.repository).replace("/", "-")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = settings.reports_dir / f"{slug}@{report.snapshot.sha[:12]}-{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def main() -> None:
    """The baseline command: collect, index, retrieve, answer, save."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="public GitHub repository URL")
    parser.add_argument("--ref", default=None, help="branch/tag (default: the repository's default branch)")
    parser.add_argument("--path", action="append", default=[], help="file path to inspect (repeatable)")
    parser.add_argument("--pull", action="append", default=[], type=int, help="PR number to inspect (repeatable)")
    parser.add_argument("--discover-limit", type=int, default=10, help="files to discover when no --path is given")
    parser.add_argument("--question", required=True, help="the question to answer")
    parser.add_argument("--rebuild", action="store_true", help="rebuild the index before answering")
    args = parser.parse_args()

    gh = get_github()
    repo = get_repository(gh, args.repo)
    snapshot = resolve_ref(gh, args.repo, args.ref)

    collector = Collector(repo, snapshot)
    try:
        if args.path:
            for path in args.path:
                collector.add_file(path)
        else:
            discovered, warning = discover_files(repo, snapshot, limit=args.discover_limit)
            if warning:
                print(warning)
            for path in discovered:
                collector.add_file(path)
        for number in args.pull:
            collector.add_pull(number)
            collector.add_reviews(number)
        records = [collector.sources[key] for key in sorted(collector.sources)]
        coverage = collector.coverage()
    finally:
        collector.close()

    collection = collection_name(snapshot)
    client = open_qdrant()
    try:
        if args.rebuild:
            reset_collection(client, collection)
        embeddings = build_embeddings()
        sparse = build_sparse_embedding()
        store = build_vector_store(
            client, embeddings, collection, sparse_embedding=sparse, mode="hybrid"
        )
        index_records(client, store, collection, snapshot, records, rebuild=args.rebuild)

        candidates, warning = search_evidence(
            client, embeddings, sparse, snapshot, args.question, mode="hybrid"
        )
        if warning:
            raise SystemExit(warning)
        ranked, rerank_warning = rerank_documents(args.question, candidates)
        if rerank_warning:
            print(f"note: {rerank_warning}")
        report, issues = answer_question(args.question, snapshot, records, ranked, coverage)
    finally:
        client.close()

    path = save_report(report)
    print(f"report: {path}")
    print(f"status: {report.status} | claims: {len(report.claims)} | issues: {len(issues)}")
    print(f"summary: {report.summary[:300]}")


if __name__ == "__main__":
    main()

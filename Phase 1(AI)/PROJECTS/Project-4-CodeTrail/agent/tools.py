"""Typed tools for the investigator: search evidence and follow its trail.

Each tool is a plain function behind a LangChain tool schema, closing over a
**trusted run context** -- repository, pinned SHA, collector, and index
client. The model never supplies repository or ref, so a tool call cannot
wander outside the investigation's scope.

Every read tool indexes what it fetched before returning, so the next
``search_evidence`` call can already see it. Outputs are compact on purpose:
a tool result competes with everything else for the model's context budget.

This replaces Project 3's handwritten tool schemas/dispatch with the same
plain-function responsibilities plus framework-provided schemas.
"""

from __future__ import annotations

from dataclasses import dataclass

from github.Repository import Repository
from langchain_core.embeddings import Embeddings
from langchain_core.tools import BaseTool, tool
from qdrant_client import QdrantClient

from github_source.code import inspect_change
from github_source.collect import Collector
from ingest.index import index_records
from models import RepoSnapshot
from retrieval.rerank import rerank_documents
from retrieval.search import search_evidence as run_search

# Output budgets: a tool result is context the model pays for on every
# following call, so each tool caps what it returns.
TOOL_CHAR_LIMIT = 8000
SNIPPET_CHARS = 300
CODE_CHARS = 4000


@dataclass
class ToolContext:
    """Trusted per-investigation context shared by all tools."""

    repo: Repository
    snapshot: RepoSnapshot
    collector: Collector
    client: QdrantClient
    embeddings: Embeddings
    sparse_embedding: object
    store: object
    collection: str


def _clip(text: str, limit: int) -> str:
    """Keep the head of long text and say how much was cut."""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n... [truncated: {len(text)} chars total]"


def _index_new(context: ToolContext, ids: list[str]) -> None:
    """Make freshly fetched records searchable before the next retrieval."""
    records = [context.collector.sources[i] for i in ids if i in context.collector.sources]
    if records:
        index_records(
            context.client,
            context.store,
            context.collection,
            context.snapshot,
            records,
        )


def _last_warning(context: ToolContext) -> str:
    return context.collector.warnings[-1] if context.collector.warnings else "unknown error"


def build_tools(context: ToolContext) -> list[BaseTool]:
    """The five investigator tools, bound to this run's context."""

    @tool
    def search_evidence(query: str, k: int = 5) -> str:
        """Search the indexed evidence for this repository snapshot.

        Use it to find code or discussion passages relevant to a question.
        Returns compact results with source_id, kind, title, line range, and
        an excerpt. Cite these source_ids exactly.
        """
        candidates, warning = run_search(
            context.client,
            context.embeddings,
            context.sparse_embedding,
            context.snapshot,
            query,
            mode="hybrid",
        )
        if warning:
            return warning
        ranked, rerank_warning = rerank_documents(query, candidates, top_k=k)
        if not ranked:
            return "No evidence matched this query."
        blocks: list[str] = []
        for document in ranked:
            metadata = document.metadata
            blocks.append(
                f"- source_id: {metadata['source_id']} | kind: {metadata.get('kind')} | "
                f"title: {metadata.get('title', '?')} | "
                f"lines {metadata.get('start_line')}-{metadata.get('end_line')}\n"
                f"  {_clip(document.page_content, SNIPPET_CHARS)}"
            )
        output = "Results (cite source_id plus an exact quote):\n" + "\n".join(blocks)
        if rerank_warning:
            output += f"\nnote: {rerank_warning}"
        return _clip(output, TOOL_CHAR_LIMIT)

    @tool
    def read_code(path: str) -> str:
        """Read one file at the pinned snapshot.

        Use it when a search result points at a file you need in full, or when
        the question names a path. Returns the file text with its source_id.
        """
        source_id = context.collector.add_file(path)
        if source_id is None:
            return f"read_code failed for {path}: {_last_warning(context)}"
        _index_new(context, [source_id])
        record = context.collector.sources[source_id]
        line_count = record.content.count("\n") + 1
        return _clip(
            f"source_id: {source_id}\nurl: {record.url}\nlines: {line_count}\n\n"
            f"{_clip(record.content, CODE_CHARS)}",
            TOOL_CHAR_LIMIT,
        )

    @tool
    def list_file_history(path: str, limit: int = 10) -> str:
        """List commits that touched a file, newest first.

        Use it to find the change that introduced or modified a piece of code.
        Each entry includes the commit SHA (for read_change) and its source_id.
        """
        ids = context.collector.add_file_history(path, limit=limit)
        if not ids:
            return f"No commits recorded for {path}."
        _index_new(context, ids)
        lines: list[str] = []
        for source_id in ids:
            record = context.collector.sources[source_id]
            sha = source_id.rsplit(":", 1)[-1]
            date = record.source_date.date().isoformat() if record.source_date else "?"
            lines.append(f"- {sha} {date} {record.title} | source_id {source_id}")
        return _clip(f"History for {path} (newest first):\n" + "\n".join(lines), TOOL_CHAR_LIMIT)

    @tool
    def read_change(sha: str) -> str:
        """Inspect one commit: message, changed files, and warnings.

        Use it after list_file_history, or when a discussion names a commit.
        Returns the commit's source_id plus its changed-file metadata.
        """
        try:
            record, changed, warning = inspect_change(context.repo, context.snapshot, sha)
        except ValueError as exc:
            return f"read_change failed: {exc}"
        _index_new(context, [record.source_id])
        files: list[str] = []
        for file in changed[:40]:
            line = f"  {file.status:<9} {file.filename} (+{file.additions}/-{file.deletions})"
            if file.previous_filename:
                line += f" renamed from {file.previous_filename}"
            if not file.patch_available:
                line += " [no patch]"
            files.append(line)
        date = record.source_date.date().isoformat() if record.source_date else "?"
        output = (
            f"source_id: {record.source_id}\n"
            f"commit {sha} by {record.author} on {date}\n\n"
            f"{_clip(record.content, 1000)}\n\n"
            f"Changed files ({len(changed)}):\n" + "\n".join(files)
        )
        if warning:
            output += f"\nwarning: {warning}"
        if record.relationships:
            leads: list[str] = []
            for relationship in record.relationships:
                if ":pr:" in relationship:
                    number = relationship.rsplit(":pr:", 1)[-1]
                    leads.append(f"  pull request #{number} (source_id {relationship})")
                else:
                    leads.append(f"  {relationship}")
            output += "\nleads (read a PR number with read_discussion):\n" + "\n".join(leads)
        return _clip(output, TOOL_CHAR_LIMIT)

    @tool
    def read_discussion(number: int) -> str:
        """Read a PR or issue thread: description, comments, and reviews.

        Use it to find the stated reason behind a change. Pass the PR/issue
        number (for example 4682). Returns a source_id for every fetched record.
        """
        ids: list[str] = []

        def _discussion_block(record) -> str:
            date = record.source_date.date().isoformat() if record.source_date else "?"
            return (
                f"source_id: {record.source_id}\n"
                f"state: {record.state} | by {record.author} | {date}\n"
                f"title: {record.title}\n\n{_clip(record.content, 1500)}"
            )

        pull_id = context.collector.add_pull(number)
        if pull_id is not None:
            ids.append(pull_id)
            ids.extend(context.collector.add_comments(number))
            ids.extend(context.collector.add_reviews(number))
            _index_new(context, ids)
            blocks = [_discussion_block(context.collector.sources[pull_id])]
            for source_id in ids[1:]:
                record = context.collector.sources[source_id]
                blocks.append(
                    f"[{record.kind.value}] source_id: {source_id} | {record.author}"
                    f"{' | ' + record.state if record.state else ''}\n"
                    f"{_clip(record.content, 400)}"
                )
            return _clip("\n\n".join(blocks), TOOL_CHAR_LIMIT)

        issue_id = context.collector.add_issue(number)
        if issue_id is not None:
            ids.append(issue_id)
            ids.extend(context.collector.add_comments(number))
            _index_new(context, ids)
            blocks = [_discussion_block(context.collector.sources[issue_id])]
            for source_id in ids[1:]:
                record = context.collector.sources[source_id]
                blocks.append(
                    f"[comment] source_id: {source_id} | {record.author}\n"
                    f"{_clip(record.content, 400)}"
                )
            return _clip("\n\n".join(blocks), TOOL_CHAR_LIMIT)

        return f"No pull request or issue #{number} found. {_last_warning(context)}"

    return [search_evidence, read_code, list_file_history, read_change, read_discussion]

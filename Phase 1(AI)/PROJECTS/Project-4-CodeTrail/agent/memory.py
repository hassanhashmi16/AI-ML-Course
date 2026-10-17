"""Reusable findings: validated claims that outlive one investigation.

A finished report's cited claims are saved into a **separate** Qdrant
collection with their source references, repository, base SHA, and source
revision. A later run on the same repository@snapshot can recall them as
**leads** -- never as established fact: every recalled finding is revalidated
against the current evidence before it is trusted, and the repository + base
SHA filter makes it impossible for another repository (or another revision)
to inherit it.

Checkpoints (Step 13) resume one run. Findings (this step) help later runs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from langchain_core.embeddings import Embeddings
from pydantic import AwareDatetime
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from models import ClaimLabel, Contract, Report, RepoSnapshot, SourceRecord

FINDINGS_COLLECTION = "codetrail_findings"


class Finding(Contract):
    """One validated claim, stored with everything needed to re-check it."""

    finding_id: str
    repository: str
    base_sha: str
    question: str
    statement: str
    label: ClaimLabel
    source_id: str
    quote: str
    start_line: int
    end_line: int
    source_revision: str | None = None
    thread_id: str | None = None
    created_at: AwareDatetime


def ensure_collection(client: QdrantClient, embeddings: Embeddings) -> None:
    """Create the findings collection (dense only) on first use."""
    if client.collection_exists(FINDINGS_COLLECTION):
        return
    dimension = len(embeddings.embed_query("dimension probe"))
    client.create_collection(
        collection_name=FINDINGS_COLLECTION,
        vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
    )


def save_findings(
    client: QdrantClient,
    embeddings: Embeddings,
    report: Report,
    records: dict[str, SourceRecord],
    *,
    thread_id: str | None = None,
) -> list[str]:
    """Upsert every cited claim of a finished report as a reusable finding.

    The finding ID is deterministic (repository@sha + source + quote), so
    saving the same claim twice replaces it instead of duplicating it.
    """
    if not report.claims:
        return []
    ensure_collection(client, embeddings)
    saved: list[str] = []
    created_at = datetime.now(timezone.utc)
    for claim in report.claims:
        for excerpt in claim.excerpts:
            identifier = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{report.snapshot.repository}@{report.snapshot.sha}:"
                f"{excerpt.source_id}:{excerpt.quote}",
            )
            record = records.get(excerpt.source_id)
            finding = Finding(
                finding_id=str(identifier),
                repository=report.snapshot.repository,
                base_sha=report.snapshot.sha,
                question=report.question,
                statement=claim.statement,
                label=claim.label,
                source_id=excerpt.source_id,
                quote=excerpt.quote,
                start_line=excerpt.start_line or 1,
                end_line=excerpt.end_line or 1,
                source_revision=record.content_revision if record else None,
                thread_id=thread_id,
                created_at=created_at,
            )
            vector = embeddings.embed_query(f"{report.question}\n{claim.statement}")
            client.upsert(
                collection_name=FINDINGS_COLLECTION,
                points=[
                    PointStruct(
                        id=finding.finding_id,
                        vector=vector,
                        payload=finding.model_dump(mode="json"),
                    )
                ],
            )
            saved.append(finding.finding_id)
    return saved


def recall_findings(
    client: QdrantClient,
    embeddings: Embeddings,
    snapshot: RepoSnapshot,
    question: str,
    *,
    limit: int = 5,
) -> list[Finding]:
    """Findings for the same repository@snapshot, most relevant first."""
    if not client.collection_exists(FINDINGS_COLLECTION):
        return []
    response = client.query_points(
        collection_name=FINDINGS_COLLECTION,
        query=embeddings.embed_query(question),
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="repository", match=MatchValue(value=snapshot.repository)
                ),
                FieldCondition(key="base_sha", match=MatchValue(value=snapshot.sha)),
            ]
        ),
        limit=limit,
        with_payload=True,
    )
    return [Finding.model_validate(point.payload) for point in response.points]


def revalidate_findings(
    findings: list[Finding], records: dict[str, SourceRecord]
) -> list[tuple[Finding, str]]:
    """Re-check recalled findings against current evidence.

    Status is one of ``supported``, ``stale`` (the quote no longer appears),
    or ``unverified`` (the source was not inspected in this run). Only the
    first may be treated as evidence; the others are leads to re-investigate.
    """
    results: list[tuple[Finding, str]] = []
    for finding in findings:
        record = records.get(finding.source_id)
        if record is None:
            results.append((finding, "unverified: source not inspected in this run"))
        elif finding.quote not in record.content:
            results.append((finding, "stale: quote no longer found in the source"))
        else:
            results.append((finding, "supported"))
    return results


def format_leads(results: list[tuple[Finding, str]]) -> list[str]:
    """Lead lines for prompts or logs -- the status always travels with them."""
    return [
        f"[{status}] {finding.statement} (source {finding.source_id})"
        for finding, status in results
    ]

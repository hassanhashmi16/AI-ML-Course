"""Readers for discussion evidence: PRs, issues, conversation comments, and reviews.

These readers answer the "why" side of CodeTrail: a code change shows *what*
happened, the discussion shows the stated reason. Everything is SHA-scoped to
the snapshot and normalized into ``SourceRecord``s with stable IDs, PR state
("merged" vs "proposed"), edit markers, and relationships back to the parent
thread -- so a later claim can distinguish accepted intent from a passing
comment.
"""

from __future__ import annotations

from itertools import islice

from github import GithubException
from github.Repository import Repository

from config import settings
from github_source.client import as_aware
from models import RepoSnapshot, SourceKind, SourceRecord, make_source_id


def _parent_id(
    snapshot: RepoSnapshot, number: int, kind: SourceKind
) -> str:
    """Stable ID of the PR or issue a comment belongs to."""
    return make_source_id(kind, snapshot.repository, snapshot.sha, str(number))


def _pull_state(pull) -> str:
    """GitHub reports merged via ``merged_at``; open/closed via ``state``."""
    if pull.merged_at is not None:
        return "merged"
    return "open" if pull.state == "open" else "closed"


def read_pull(repo: Repository, snapshot: RepoSnapshot, number: int) -> SourceRecord:
    """One PR description as a retained source record."""
    try:
        pull = repo.get_pull(number)
    except GithubException as exc:
        if exc.status == 404:
            raise ValueError(f"pull request not found: #{number}") from exc
        raise
    relationships: list[str] = []
    if pull.merge_commit_sha:  # the commit that landed the PR, as a lead
        relationships.append(
            make_source_id(SourceKind.COMMIT, snapshot.repository, snapshot.sha, pull.merge_commit_sha)
        )
    return SourceRecord(
        source_id=_parent_id(snapshot, number, SourceKind.PULL_REQUEST),
        kind=SourceKind.PULL_REQUEST,
        repository=snapshot.repository,
        snapshot_sha=snapshot.sha,
        url=pull.html_url,
        title=pull.title,
        author=pull.user.login if pull.user else None,
        source_date=as_aware(pull.created_at),
        state=_pull_state(pull),
        content=pull.body or "(no description)",
        content_revision=f"updated:{as_aware(pull.updated_at).isoformat()}" if pull.updated_at else None,
        relationships=relationships,
    )


def read_issue(repo: Repository, snapshot: RepoSnapshot, number: int) -> SourceRecord:
    """One issue description as a retained source record."""
    try:
        issue = repo.get_issue(number)
    except GithubException as exc:
        if exc.status == 404:
            raise ValueError(f"issue not found: #{number}") from exc
        raise
    return SourceRecord(
        source_id=_parent_id(snapshot, number, SourceKind.ISSUE),
        kind=SourceKind.ISSUE,
        repository=snapshot.repository,
        snapshot_sha=snapshot.sha,
        url=issue.html_url,
        title=issue.title,
        author=issue.user.login if issue.user else None,
        source_date=as_aware(issue.created_at),
        state=issue.state,  # open / closed
        content=issue.body or "(no description)",
        content_revision=f"updated:{as_aware(issue.updated_at).isoformat()}" if issue.updated_at else None,
    )


def read_comments(
    repo: Repository,
    snapshot: RepoSnapshot,
    number: int,
    limit: int | None = None,
) -> tuple[list[SourceRecord], str | None]:
    """Conversation comments on a PR or issue, bounded with a visible warning.

    This is the issue-comments endpoint, which serves PRs too (a PR *is* an
    issue in the API); line-level review comments are covered by
    ``read_reviews``. Each comment records which thread it belongs to, so a
    quote can always be traced back to its discussion.
    """
    cap = limit if limit is not None else settings.max_comments
    try:
        issue = repo.get_issue(number)  # also tells us PR vs issue for the parent ID
    except GithubException as exc:
        if exc.status == 404:
            raise ValueError(f"discussion not found: #{number}") from exc
        raise
    parent_kind = SourceKind.PULL_REQUEST if issue.pull_request is not None else SourceKind.ISSUE
    parent_id = _parent_id(snapshot, number, parent_kind)

    comments = issue.get_comments()
    total = comments.totalCount
    records: list[SourceRecord] = []
    for comment in islice(comments, cap):
        author = comment.user.login if comment.user else None
        records.append(
            SourceRecord(
                source_id=make_source_id(
                    SourceKind.COMMENT,
                    snapshot.repository,
                    snapshot.sha,
                    f"issue-{number}-comment-{comment.id}",
                ),
                kind=SourceKind.COMMENT,
                repository=snapshot.repository,
                snapshot_sha=snapshot.sha,
                url=comment.html_url,
                title=f"comment by {author or 'unknown'} on #{number}",
                author=author,
                source_date=as_aware(comment.created_at),
                content=comment.body or "(empty comment)",
                content_revision=(
                    f"updated:{as_aware(comment.updated_at).isoformat()}"
                    if comment.updated_at
                    else None
                ),
                relationships=[parent_id],
            )
        )
    warning = None
    if total > len(records):
        warning = f"comments truncated: showing {len(records)} of {total} (limit {cap})"
    return records, warning


def read_reviews(
    repo: Repository,
    snapshot: RepoSnapshot,
    number: int,
    limit: int | None = None,
) -> tuple[list[SourceRecord], str | None]:
    """PR reviews (submitted review bodies with their verdict), bounded."""
    cap = limit if limit is not None else settings.max_comments
    try:
        pull = repo.get_pull(number)
    except GithubException as exc:
        if exc.status == 404:
            raise ValueError(f"pull request not found: #{number}") from exc
        raise
    parent_id = _parent_id(snapshot, number, SourceKind.PULL_REQUEST)

    reviews = pull.get_reviews()
    total = reviews.totalCount
    records: list[SourceRecord] = []
    for review in islice(reviews, cap):
        author = review.user.login if review.user else None
        records.append(
            SourceRecord(
                source_id=make_source_id(
                    SourceKind.REVIEW,
                    snapshot.repository,
                    snapshot.sha,
                    f"pr-{number}-review-{review.id}",
                ),
                kind=SourceKind.REVIEW,
                repository=snapshot.repository,
                snapshot_sha=snapshot.sha,
                url=review.html_url,
                title=f"review by {author or 'unknown'} on #{number}",
                author=author,
                source_date=as_aware(review.submitted_at),
                state=review.state.lower() if review.state else None,
                content=review.body or "(no review text)",
                relationships=[parent_id],
            )
        )
    warning = None
    if total > len(records):
        warning = f"reviews truncated: showing {len(records)} of {total} (limit {cap})"
    return records, warning

"""GitHub client: authenticate, validate a repository, resolve a ref to a SHA.

One place owns the PyGithub connection and the ref-resolution step, so the
readers in ``code.py`` (and the collector in Step 5) share the same behavior.
Every reader works against a pinned ``RepoSnapshot``: resolve once, then
never resolve again -- that is what makes the evidence SHA-addressable and
the answers reproducible.
"""

from __future__ import annotations

from datetime import datetime, timezone

from github import Auth, Github, GithubException
from github.Repository import Repository

from config import settings
from models import RepoSnapshot, repo_slug


def as_aware(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive datetime (PyGithub mixes naive/aware across paths).

    Our models require timezone-aware dates, so the conversion happens once,
    here, instead of surfacing as a validation error mid-investigation.
    """
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def get_github() -> Github:
    """A PyGithub client using GITHUB_TOKEN when present.

    Public repositories are readable without a token, but the anonymous rate
    limit (60 requests/hour) is far too small for real investigations.
    """
    token = settings.github_token.get_secret_value()
    if token:
        return Github(auth=Auth.Token(token))  # the SDK never logs the token
    return Github()  # anonymous fallback, for a smoke check only


def get_repository(gh: Github, repository: str) -> Repository:
    """Return the repository for a canonical GitHub URL, or fail clearly."""
    slug = repo_slug(repository)
    try:
        return gh.get_repo(slug)
    except GithubException as exc:
        if exc.status == 404:
            raise ValueError(f"repository not found or not public: {slug}") from exc
        raise  # rate limits and other failures must not masquerade as "not found"


def resolve_ref(gh: Github, repository: str, ref: str | None) -> RepoSnapshot:
    """Pin a branch/tag (or the default branch) to an immutable commit SHA.

    The SHA, not the ref, is used for every later read. Historical evidence
    (an old commit, an old comment) keeps its own dates; the snapshot pins
    *scope*, not time.
    """
    repo = get_repository(gh, repository)
    ref_name = ref or repo.default_branch
    try:
        commit = repo.get_commit(sha=ref_name)
    except GithubException as exc:
        # GitHub answers an unknown ref on this endpoint with 404 or 422.
        if exc.status in (404, 422):
            raise ValueError(f"ref not found: {ref_name!r}") from exc
        raise
    commit_date = as_aware(commit.commit.committer.date)
    if commit_date is None:
        raise ValueError(f"commit {commit.sha} has no committer date; refusing an unpinnable snapshot")
    return RepoSnapshot(
        repository=repository,
        ref_requested=ref,
        sha=commit.sha,
        commit_date=commit_date,
    )

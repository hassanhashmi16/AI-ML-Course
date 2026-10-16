"""Bounded readers for repository code and file history.

Every reader takes the pinned ``RepoSnapshot`` and never resolves a ref
itself; all reads are SHA-addressed, so anything written from them can point
at exact, immutable content (canonical URL + blob revision + line ranges).

Bounded means bounded *visibly*: readers that can be cut short by a
configured limit return ``(data, warning)``, and the warning names the limit.
Silently returning less would make a truncated history look like a complete
one -- the failure this step's check exists to catch.
"""

from __future__ import annotations

from github import GithubException
from github.Commit import Commit
from github.Repository import Repository

from config import settings
from github_source.client import as_aware
from models import Contract, RepoSnapshot, SourceKind, SourceRecord, make_source_id

# Extensions file discovery may select when the request names no path, and
# the size cap that keeps a "small file set" actually small.
READABLE_EXTENSIONS = {".py", ".md", ".rst", ".txt", ".toml", ".cfg", ".ini"}
MAX_DISCOVERED_FILE_BYTES = 200_000


class ChangedFile(Contract):
    """One file touched by a commit, with the metadata GitHub reports.

    This is inspection metadata (not a retained source record): it says what
    a change did, while the commit's ``SourceRecord`` holds the message and
    identity that a claim will cite.
    """

    filename: str
    status: str  # added / modified / removed / renamed / ...
    additions: int = 0
    deletions: int = 0
    patch_available: bool = False  # False for binary or oversized files
    previous_filename: str | None = None  # set when status == "renamed"


def _commit_record(
    snapshot: RepoSnapshot,
    commit: Commit,
    relationships: list[str] | None = None,
) -> SourceRecord:
    """One commit -> one retained source record (its stable ID ends in the SHA)."""
    message = commit.commit.message or ""
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    author = commit.author.login if commit.author is not None else None
    if not author and commit.commit.author is not None:
        author = commit.commit.author.name
    return SourceRecord(
        source_id=make_source_id(SourceKind.COMMIT, snapshot.repository, snapshot.sha, commit.sha),
        kind=SourceKind.COMMIT,
        repository=snapshot.repository,
        snapshot_sha=snapshot.sha,
        url=commit.html_url,
        title=lines[0] if lines else commit.sha[:7],
        author=author,
        source_date=as_aware(commit.commit.committer.date),
        content=message or "(no commit message)",
        relationships=relationships or [],
    )


def read_file(repo: Repository, snapshot: RepoSnapshot, path: str) -> SourceRecord:
    """Read one file at the pinned snapshot into a retained source record."""
    try:
        content = repo.get_contents(path, ref=snapshot.sha)
    except GithubException as exc:
        if exc.status == 404:
            raise ValueError(f"path not found at {snapshot.sha[:7]}: {path}") from exc
        raise
    if isinstance(content, list):
        raise ValueError(f"path is a directory, not a file: {path}")
    # The contents API only serves base64 for files up to ~1 MB. Anything it
    # declines must fail loudly here, not become an empty record downstream.
    if content.encoding != "base64":
        raise ValueError(f"file too large for the contents API ({content.size} bytes): {path}")
    try:
        text = content.decoded_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not UTF-8 text: {path}") from exc
    return SourceRecord(
        source_id=make_source_id(SourceKind.FILE, snapshot.repository, snapshot.sha, path),
        kind=SourceKind.FILE,
        repository=snapshot.repository,
        snapshot_sha=snapshot.sha,
        url=f"{snapshot.repository}/blob/{snapshot.sha}/{path}",
        title=path,
        content=text,
        content_revision=content.sha,  # blob SHA: same bytes -> same revision
    )


def list_file_history(
    repo: Repository,
    snapshot: RepoSnapshot,
    path: str,
    limit: int | None = None,
) -> tuple[list[SourceRecord], str | None]:
    """Commits that touched ``path``, newest first, capped with a visible warning."""
    cap = limit if limit is not None else settings.max_commits
    commits = repo.get_commits(path=path, sha=snapshot.sha)
    total = commits.totalCount  # forces one page fetch, then slices lazily
    records = [_commit_record(snapshot, commit) for commit in commits[:cap]]
    warning = None
    if total > len(records):
        warning = (
            f"file history truncated: showing {len(records)} of {total} commits (limit {cap})"
        )
    return records, warning


def inspect_change(
    repo: Repository,
    snapshot: RepoSnapshot,
    sha: str,
) -> tuple[SourceRecord, list[ChangedFile], str | None]:
    """Inspect one commit: its record, changed-file metadata, and warnings."""
    try:
        commit = repo.get_commit(sha=sha)
    except GithubException as exc:
        if exc.status in (404, 422):
            raise ValueError(f"commit not found: {sha}") from exc
        raise

    changed = [
        ChangedFile(
            filename=file.filename,
            status=file.status,
            additions=file.additions,
            deletions=file.deletions,
            patch_available=bool(file.patch),
            previous_filename=getattr(file, "previous_filename", None),
        )
        for file in commit.files
    ]

    warnings: list[str] = []
    no_patch = [file.filename for file in changed if not file.patch_available]
    if no_patch:
        warnings.append(
            f"no patch provided for {len(no_patch)} file(s) (binary or oversized): "
            + ", ".join(no_patch[:3])
            + ("..." if len(no_patch) > 3 else "")
        )
    renamed = [file.filename for file in changed if file.status == "renamed"]
    if renamed:
        warnings.append("renamed file(s): " + ", ".join(renamed[:3]))

    # Associated PRs are *leads* -- the reason for a change often lives in the
    # discussion. This lookup is optional by design: a failure stays visible
    # instead of hiding the commit itself. (Iterate with a manual cap:
    # slicing a PyGithub PaginatedList raises IndexError past its length.)
    relationships: list[str] = []
    try:
        for pull in commit.get_pulls():
            if len(relationships) >= 3:
                break
            relationships.append(
                make_source_id(
                    SourceKind.PULL_REQUEST, snapshot.repository, snapshot.sha, str(pull.number)
                )
            )
    except GithubException as exc:
        warnings.append(f"PR association lookup failed (status {exc.status})")

    record = _commit_record(snapshot, commit, relationships=relationships)
    return record, changed, ("; ".join(warnings) if warnings else None)


def discover_files(
    repo: Repository,
    snapshot: RepoSnapshot,
    limit: int | None = None,
) -> tuple[list[str], str | None]:
    """A small deterministic file set for when the request names no path.

    Deterministic order (shallowest first, then alphabetical) so re-running
    discovery on the same snapshot selects the same files -- which keeps
    source IDs stable and evaluation runs comparable.
    """
    cap = limit if limit is not None else settings.max_files
    tree = repo.get_git_tree(snapshot.sha, recursive=True)
    candidates = sorted(
        (
            element.path
            for element in tree.tree
            if element.type == "blob"
            and (element.size or 0) <= MAX_DISCOVERED_FILE_BYTES
            and _readable(element.path)
        ),
        key=lambda path: (path.count("/"), path),
    )
    selected = candidates[:cap]
    warning = None
    if len(candidates) > len(selected):
        warning = (
            f"file discovery truncated: selected {len(selected)} of {len(candidates)} "
            f"candidate files (limit {cap})"
        )
    return selected, warning


def _readable(path: str) -> bool:
    lowered = path.lower()
    return any(lowered.endswith(ext) for ext in READABLE_EXTENSIONS)

"""CodeTrail's shared contracts: request -> evidence -> claims -> report.

Every layer imports these classes instead of inventing its own shapes. That
is what keeps a ``source_id`` meaningful from the collector (Steps 4-5),
through chunking and retrieval (Steps 6-8), through the investigation graph
(Steps 10-12), and into the final report (Step 9).

The validators are deliberate. Where a schema can enforce an honesty rule --
a documented claim must cite an excerpt; an unknown claim must not pretend
to -- it raises immediately instead of letting a wrong shape travel.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class Contract(BaseModel):
    """Base for all shared contracts: a misspelled field must fail loudly."""

    model_config = ConfigDict(extra="forbid")


class SourceKind(StrEnum):
    """Where a piece of evidence came from."""

    FILE = "file"                  # a file's text at the snapshot
    COMMIT = "commit"              # a commit message and changed-file metadata
    PULL_REQUEST = "pull_request"  # a PR description
    ISSUE = "issue"                # an issue description
    COMMENT = "comment"            # one discussion comment (on a PR or issue)
    REVIEW = "review"              # a review comment from a PR review


class ClaimLabel(StrEnum):
    """How strongly inspected evidence supports a claim.

    This is the report's honesty unit, and it is structural -- not a note in
    the prose. ``documented`` means a source states it; ``inferred`` means it
    follows from evidence that does not state it outright; ``unknown`` means
    it was not established within the searched scope (see ``Coverage``).
    """

    DOCUMENTED = "documented"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class ReportStatus(StrEnum):
    """How complete a finished investigation is."""

    COMPLETE = "complete"  # finished within limits, evidence gathered as planned
    PARTIAL = "partial"    # a budget or scope limit cut it short; result is honest but incomplete
    FAILED = "failed"      # no usable report could be produced


def canonical_repo_url(url: str) -> str:
    """Normalize a GitHub repository URL to ``https://github.com/owner/repo``.

    Accepts the common spellings (trailing slash, ``.git`` suffix, SSH form)
    so the same repository always becomes the same string -- which is what
    keeps cache keys, filters, and source IDs stable.
    """
    text = url.strip().rstrip("/")
    if text.startswith("git@github.com:"):
        text = "https://github.com/" + text[len("git@github.com:"):]
    if text.endswith(".git"):
        text = text[: -len(".git")]
    prefix = "https://github.com/"
    if not text.startswith(prefix):
        raise ValueError("only https://github.com/owner/repo URLs are supported")
    parts = text[len(prefix):].split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("expected exactly https://github.com/owner/repo")
    return prefix + parts[0] + "/" + parts[1]


def repo_slug(repository: str) -> str:
    """``https://github.com/owner/repo`` -> ``owner/repo`` (for IDs and caches)."""
    return canonical_repo_url(repository)[len("https://github.com/"):]


def make_source_id(kind: SourceKind, repository: str, snapshot_sha: str, identifier: str) -> str:
    """Deterministic ID for a source record: the same source always gets the same ID.

    Repeating collection or indexing with these IDs is what makes writes
    idempotent -- a second fetch replaces the same key instead of duplicating
    evidence. ``identifier`` is caller-chosen and must itself be stable, e.g.
    a file path, a PR/issue number, or ``pr-4682-comment-998877``.
    """
    if not identifier:
        raise ValueError("identifier must not be empty")
    slug = repo_slug(repository)
    match kind:
        case SourceKind.FILE:
            # Scoped by snapshot: the same path at a different SHA is a
            # different record, because its content is different.
            return f"github:{slug}@{snapshot_sha}:file:{identifier}"
        case SourceKind.COMMIT:
            return f"github:{slug}:commit:{identifier}"
        case SourceKind.PULL_REQUEST:
            return f"github:{slug}:pr:{identifier}"
        case SourceKind.ISSUE:
            return f"github:{slug}:issue:{identifier}"
        case SourceKind.COMMENT:
            return f"github:{slug}:comment:{identifier}"
        case SourceKind.REVIEW:
            return f"github:{slug}:review:{identifier}"
    raise ValueError(f"unsupported source kind: {kind}")  # unreachable with the enum


class RepoSnapshot(Contract):
    """The pinned moment in a repository's history that an investigation explains.

    Resolve a branch/tag to a SHA once and use that SHA consistently; frozen
    so the snapshot cannot drift mid-run. Historical evidence (a 2022 commit,
    an old comment) keeps its own dates -- the snapshot pins *scope*, not time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str  # canonical URL
    ref_requested: str | None = None  # the branch/tag the user asked for, if any
    sha: str
    commit_date: AwareDatetime

    @field_validator("repository")
    @classmethod
    def _canonical(cls, value: str) -> str:
        return canonical_repo_url(value)


class InvestigationRequest(Contract):
    """What the user asked: a public repository, a question, optional path/ref."""

    repository: str
    question: str = Field(min_length=1)
    path: str | None = None
    ref: str | None = None

    @field_validator("repository")
    @classmethod
    def _canonical(cls, value: str) -> str:
        return canonical_repo_url(value)

    @field_validator("path", "ref", mode="before")
    @classmethod
    def _blank_is_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("path")
    @classmethod
    def _clean_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().replace("\\", "/").strip("/")
        if not cleaned or ".." in cleaned.split("/"):
            raise ValueError("path must be repository-relative (no '..', not empty)")
        return cleaned

    @field_validator("question")
    @classmethod
    def _clean_question(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("question must not be blank")
        return cleaned


class SourceRecord(Contract):
    """One piece of retained evidence, keyed by a stable ``source_id``.

    Retains the full source text plus its identity (ID, URL), dates, and
    relationships -- so a later answer can cite an exact excerpt and the
    reader can inspect the original. Chunking (Step 6) is what prepares
    smaller passages for search; the full record stays intact here.
    """

    source_id: str = Field(min_length=1)
    kind: SourceKind
    repository: str
    snapshot_sha: str
    url: str
    title: str | None = None
    author: str | None = None
    source_date: AwareDatetime | None = None  # when this material was created
    content: str = Field(min_length=1)        # the retained source text
    content_revision: str | None = None       # e.g. blob SHA or last-edited marker
    relationships: list[str] = Field(default_factory=list)  # related source_ids
    truncated: bool = False  # a limit or pagination cutoff shortened `content`


class SupportingExcerpt(Contract):
    """An exact quote from an inspected source that supports a claim."""

    source_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)  # must match the source text exactly (checked in Step 9)
    start_line: int | None = Field(default=None, ge=1)  # for code: the quoted line range
    end_line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _check_line_range(self) -> "SupportingExcerpt":
        if (self.start_line is None) != (self.end_line is None):
            raise ValueError("start_line and end_line must be given together")
        if self.start_line and self.end_line and self.end_line < self.start_line:
            raise ValueError("end_line must not precede start_line")
        return self


class Claim(Contract):
    """One statement in the final explanation, with its honesty label attached.

    The label/evidence rules are the point: a ``documented`` or ``inferred``
    claim without supporting excerpts is rejected, and an ``unknown`` claim
    cannot carry excerpts -- "not established in scope" is a different thing
    from "supported", and the schema keeps them apart.
    """

    statement: str = Field(min_length=1)
    label: ClaimLabel
    excerpts: list[SupportingExcerpt] = Field(default_factory=list)

    @model_validator(mode="after")
    def _evidence_matches_label(self) -> "Claim":
        if self.label is ClaimLabel.UNKNOWN:
            if self.excerpts:
                raise ValueError("an unknown claim carries no supporting excerpts")
        elif not self.excerpts:
            raise ValueError(f"{self.label} claim requires at least one supporting excerpt")
        return self


class TimelineEvent(Contract):
    """One dated moment in the history of the change being explained."""

    date: AwareDatetime
    kind: SourceKind
    title: str = Field(min_length=1)
    summary: str = ""
    source_id: str | None = None  # link back to the evidence that records this moment


class Coverage(Contract):
    """What was actually inspected, and where the search stopped.

    This is the scope that ``unknown`` is relative to: a finding is unknown
    *within* this coverage, and cutoffs (limit reached, failed lookup,
    pagination end) stay visible here instead of disappearing.
    """

    repository: str
    snapshot_sha: str
    files_read: int = Field(default=0, ge=0)
    commits_read: int = Field(default=0, ge=0)
    discussions_read: int = Field(default=0, ge=0)
    comments_read: int = Field(default=0, ge=0)
    complete: bool = True
    notes: list[str] = Field(default_factory=list)  # cutoffs, gaps, failed lookups


class Report(Contract):
    """The finished answer: claims, timeline, and the scope it was built within."""

    question: str
    snapshot: RepoSnapshot
    status: ReportStatus
    summary: str = Field(min_length=1)
    claims: list[Claim] = Field(default_factory=list)
    alternatives: list[Claim] = Field(default_factory=list)  # options documented as considered
    timeline: list[TimelineEvent] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)  # open questions, stated as such
    coverage: Coverage
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _status_matches_content(self) -> "Report":
        if self.status is ReportStatus.COMPLETE and not self.claims:
            raise ValueError("a complete report must contain at least one claim")
        if self.status is ReportStatus.PARTIAL and not (self.unresolved or self.coverage.notes):
            raise ValueError("a partial report must state what limited it (unresolved or coverage notes)")
        return self

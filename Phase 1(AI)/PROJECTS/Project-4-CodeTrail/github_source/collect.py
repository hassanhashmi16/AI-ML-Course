"""Collector: fetch a bounded evidence bundle for one snapshot, cached.

The cache is diskcache-backed (SQLite on disk, stdlib-friendly) and keyed by
the stable source IDs from ``models.make_source_id`` -- plus listing keys for
multi-record reads (a file history, a comment thread). That gives two
properties the rest of the build depends on:

  * **Replay is free.** Collecting the same snapshot again reads from disk
    with zero GitHub requests -- important under the anonymous rate limit and
    for re-running larger collections later.
  * **Writes are idempotent.** The same source always lands on the same key,
    so a repeat collection replaces a record instead of duplicating evidence.

Failed and truncated reads are appended to ``warnings`` and flow into
``Coverage``: a missing discussion must look different from an empty one.
"""

from __future__ import annotations

import json
from pathlib import Path

from diskcache import Cache
from github import GithubException
from github.Repository import Repository

from config import settings
from github_source import code, discussions
from models import (
    Coverage,
    RepoSnapshot,
    SourceKind,
    SourceRecord,
    make_source_id,
    repo_slug,
)


class Collector:
    """Collect evidence for one pinned snapshot into one cache-aware bundle."""

    def __init__(
        self,
        repo: Repository,
        snapshot: RepoSnapshot,
        cache_dir: Path | None = None,
    ) -> None:
        self.repo = repo
        self.snapshot = snapshot
        self.sources: dict[str, SourceRecord] = {}  # stable id -> record
        self.warnings: list[str] = []               # truncations and failed reads
        self.cache_hits = 0
        self.cache_misses = 0
        directory = cache_dir if cache_dir is not None else settings.data_dir / "cache"
        self.cache = Cache(directory=str(directory))

    def close(self) -> None:
        self.cache.close()

    # ---- internals ---------------------------------------------------------

    def _listing_key(self, label: str, identifier: str, limit: int) -> str:
        """Cache key for a multi-record read, scoped to repo@snapshot + limit."""
        slug = repo_slug(self.snapshot.repository)
        return f"github:{slug}@{self.snapshot.sha}:{label}:{identifier}:limit={limit}"

    def _single(self, source_id: str, fetcher, label: str) -> str | None:
        """Cache-first fetch of one record keyed by its stable source ID."""
        cached = self.cache.get(source_id)
        if cached is not None:
            self.cache_hits += 1
            self.sources[source_id] = SourceRecord.model_validate_json(cached)
            return source_id
        self.cache_misses += 1
        try:
            record = fetcher()
        except (GithubException, ValueError) as exc:
            self.warnings.append(f"{label} read failed: {exc}")
            return None
        self.cache.set(source_id, record.model_dump_json())
        self.sources[source_id] = record
        return source_id

    def _listing(self, cache_key: str, fetcher, label: str) -> list[str]:
        """Cache-first fetch of a bounded list of records.

        The listing envelope (record JSON + its truncation warning) is cached
        as one value, so a replay reproduces both the evidence and the warning
        without touching GitHub; each record is also stored under its own ID
        for direct lookup later.
        """
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.cache_hits += 1
            envelope = json.loads(cached)
            for raw in envelope["records"]:
                record = SourceRecord.model_validate(raw)
                self.sources[record.source_id] = record
            if envelope["warning"]:
                self.warnings.append(f"{label}: {envelope['warning']}")
            return [raw["source_id"] for raw in envelope["records"]]
        self.cache_misses += 1
        try:
            records, warning = fetcher()
        except (GithubException, ValueError) as exc:
            self.warnings.append(f"{label} read failed: {exc}")
            return []
        envelope = {
            "records": [record.model_dump(mode="json") for record in records],
            "warning": warning,
        }
        self.cache.set(cache_key, json.dumps(envelope))
        for record in records:
            self.sources[record.source_id] = record
            self.cache.set(record.source_id, record.model_dump_json())
        if warning:
            self.warnings.append(f"{label}: {warning}")
        return [record.source_id for record in records]

    # ---- public adders -----------------------------------------------------

    def add_file(self, path: str) -> str | None:
        source_id = make_source_id(SourceKind.FILE, self.snapshot.repository, self.snapshot.sha, path)
        return self._single(source_id, lambda: code.read_file(self.repo, self.snapshot, path), f"file {path}")

    def add_file_history(self, path: str, limit: int | None = None) -> list[str]:
        cap = limit if limit is not None else settings.max_commits
        key = self._listing_key("file-history", path, cap)
        fetcher = lambda: code.list_file_history(self.repo, self.snapshot, path, limit=cap)  # noqa: E731
        return self._listing(key, fetcher, f"file history {path}")

    def add_pull(self, number: int) -> str | None:
        source_id = make_source_id(SourceKind.PULL_REQUEST, self.snapshot.repository, self.snapshot.sha, str(number))
        return self._single(source_id, lambda: discussions.read_pull(self.repo, self.snapshot, number), f"pull request #{number}")

    def add_issue(self, number: int) -> str | None:
        source_id = make_source_id(SourceKind.ISSUE, self.snapshot.repository, self.snapshot.sha, str(number))
        return self._single(source_id, lambda: discussions.read_issue(self.repo, self.snapshot, number), f"issue #{number}")

    def add_comments(self, number: int, limit: int | None = None) -> list[str]:
        cap = limit if limit is not None else settings.max_comments
        key = self._listing_key("comments", str(number), cap)
        fetcher = lambda: discussions.read_comments(self.repo, self.snapshot, number, limit=cap)  # noqa: E731
        return self._listing(key, fetcher, f"comments on #{number}")

    def add_reviews(self, number: int, limit: int | None = None) -> list[str]:
        cap = limit if limit is not None else settings.max_comments
        key = self._listing_key("reviews", str(number), cap)
        fetcher = lambda: discussions.read_reviews(self.repo, self.snapshot, number, limit=cap)  # noqa: E731
        return self._listing(key, fetcher, f"reviews on #{number}")

    # ---- outputs -----------------------------------------------------------

    def coverage(self) -> Coverage:
        """What this collection actually gathered, including its cutoffs."""
        kinds = [record.kind for record in self.sources.values()]
        return Coverage(
            repository=self.snapshot.repository,
            snapshot_sha=self.snapshot.sha,
            files_read=sum(1 for kind in kinds if kind is SourceKind.FILE),
            commits_read=sum(1 for kind in kinds if kind is SourceKind.COMMIT),
            discussions_read=sum(
                1 for kind in kinds if kind in (SourceKind.PULL_REQUEST, SourceKind.ISSUE)
            ),
            comments_read=sum(
                1 for kind in kinds if kind in (SourceKind.COMMENT, SourceKind.REVIEW)
            ),
            complete=not self.warnings,
            notes=list(self.warnings),
        )

    def save_bundle(self, path: Path | None = None) -> Path:
        """Write the evidence, coverage, and warnings to one reusable JSON file."""
        if path is None:
            slug = repo_slug(self.snapshot.repository).replace("/", "-")
            path = settings.data_dir / "bundles" / f"{slug}@{self.snapshot.sha[:12]}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        bundle = {
            "repository": self.snapshot.repository,
            "ref_requested": self.snapshot.ref_requested,
            "sha": self.snapshot.sha,
            "sources": {
                source_id: record.model_dump(mode="json")
                for source_id, record in sorted(self.sources.items())
            },
            "coverage": self.coverage().model_dump(mode="json"),
            "warnings": list(self.warnings),
            "cache": {"hits": self.cache_hits, "misses": self.cache_misses},
        }
        path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        return path

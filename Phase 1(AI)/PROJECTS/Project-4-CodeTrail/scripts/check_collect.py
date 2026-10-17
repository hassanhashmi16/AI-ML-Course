r"""Exercise the Step 5 collector against the pinned Flask snapshot.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_collect.py

Collects one demo trail (file + bounded history + PR #4682 + its comments and
reviews), then repeats the collection to prove the disk cache replays it with
zero GitHub requests. A missing PR is requested on purpose, so a failed read
must show up as a visible warning. No model calls.

What is verified:
  1. The bundle contains the expected discussion evidence, with PR state
     ("merged") and relationships retained.
  2. A repeat collection replays from cache: zero misses, same sources.
  3. Truncated and failed reads stay visible (warnings + incomplete coverage).
  4. The saved JSON bundle reloads and matches the collection.
"""

import json
import sys
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from config import settings  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.collect import Collector  # noqa: E402

REPO = "https://github.com/pallets/flask"
EXPECTED_SHA = "b17bb9ed563ab2857c0db9a07ec4e6407404c7be"
PATH = "src/flask/ctx.py"
PR = 4682  # the LocalStack -> ContextVar refactor, per docs/demo-cases.md


def main() -> None:
    token = settings.github_token.get_secret_value()
    print(f"GitHub auth: {'token' if token else 'anonymous (60 requests/hour)'}")

    gh = get_github()
    repo = get_repository(gh, REPO)
    snapshot = resolve_ref(gh, REPO, "2.2.0")
    assert snapshot.sha == EXPECTED_SHA

    # ---- First collection: real fetches (or a warm cache from an earlier run).
    collector = Collector(repo, snapshot)
    try:
        file_id = collector.add_file(PATH)
        assert file_id and file_id in collector.sources
        print(f"PASS  file record: {file_id}")

        history_ids = collector.add_file_history(PATH, limit=3)
        assert len(history_ids) == 3
        assert any("truncated" in warning for warning in collector.warnings), (
            "bounded history must report its truncation"
        )
        print(f"PASS  bounded history visible: {len(history_ids)} records, warning kept")

        pr_id = collector.add_pull(PR)
        assert pr_id, f"PR #{PR} must collect"
        pull = collector.sources[pr_id]
        assert pull.state == "merged", f"expected merged PR, got {pull.state!r}"
        assert pull.content, "PR description must be retained"
        print(f"PASS  PR #{PR}: state={pull.state}, {len(pull.content)} description chars, "
              f"leads={pull.relationships or 'none'}")

        comment_ids = collector.add_comments(PR)
        review_ids = collector.add_reviews(PR)
        print(f"PASS  discussion evidence: {len(comment_ids)} comment(s), {len(review_ids)} review(s)")

        missing = collector.add_pull(999999)
        assert missing is None, "a missing PR must not produce a record"
        assert any("read failed" in warning for warning in collector.warnings), (
            "a failed read must stay visible"
        )
        print(f"PASS  failed read visible: {collector.warnings[-1]}")

        coverage = collector.coverage()
        assert not coverage.complete, "warnings must make coverage incomplete"
        assert coverage.notes, "coverage notes must carry the warnings"
        print(f"PASS  coverage: files={coverage.files_read} commits={coverage.commits_read} "
              f"discussions={coverage.discussions_read} comments={coverage.comments_read} "
              f"complete={coverage.complete}")

        first_hits, first_misses = collector.cache_hits, collector.cache_misses
        bundle_path = collector.save_bundle()
        sources_first = set(collector.sources)
    finally:
        collector.close()

    # ---- Second collection: everything must replay from the cache.
    collector2 = Collector(repo, snapshot)
    try:
        assert collector2.add_file(PATH) == file_id
        assert len(collector2.add_file_history(PATH, limit=3)) == 3
        assert collector2.add_pull(PR) == pr_id
        collector2.add_comments(PR)
        collector2.add_reviews(PR)
        assert collector2.cache_misses == 0, "a replay must not touch GitHub"
        assert collector2.cache_hits > 0
        assert set(collector2.sources) == sources_first
        print(f"PASS  replay from cache: hits={collector2.cache_hits} misses={collector2.cache_misses} "
              f"(first run: {first_hits} hits / {first_misses} misses)")
    finally:
        collector2.close()

    # ---- The saved bundle reloads and matches.
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert payload["sha"] == EXPECTED_SHA
    assert set(payload["sources"]) == sources_first
    print(f"PASS  bundle saved: {bundle_path.name} "
          f"({bundle_path.stat().st_size} bytes, {len(payload['sources'])} sources)")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

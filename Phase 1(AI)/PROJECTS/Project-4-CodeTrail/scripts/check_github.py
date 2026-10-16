r"""Exercise the Step 4 GitHub readers against the pinned Flask snapshot.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_github.py

Uses live GitHub API reads (about ten requests) and no model calls. With
GITHUB_TOKEN set in .env the authenticated rate limit applies; without it
the smoke check still runs on the anonymous limit.

What is verified:
  1. The 2.2.0 ref resolves to the SHA recorded in docs/demo-cases.md.
  2. src/flask/ctx.py is readable at that snapshot with a canonical URL and
     a retained blob revision.
  3. A bounded file history reports its truncation as a visible warning.
  4. The newest change to that file is inspectable: changed-file metadata,
     patch/rename warnings, and PR leads.
  5. File discovery returns a bounded, deterministic set with a warning.
  6. A missing repository and a missing ref fail with clear errors.
"""

import sys
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from config import settings  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.code import (  # noqa: E402
    discover_files,
    inspect_change,
    list_file_history,
    read_file,
)

REPO = "https://github.com/pallets/flask"
EXPECTED_SHA = "b17bb9ed563ab2857c0db9a07ec4e6407404c7be"
PATH = "src/flask/ctx.py"


def main() -> None:
    token = settings.github_token.get_secret_value()
    print(f"GitHub auth: {'token' if token else 'anonymous (60 requests/hour)'}")

    gh = get_github()
    repo = get_repository(gh, REPO)

    # 1) Ref resolution pins exactly the snapshot the demo cases recorded.
    snapshot = resolve_ref(gh, REPO, "2.2.0")
    assert snapshot.sha == EXPECTED_SHA, (
        f"resolved {snapshot.sha}, demo cases expect {EXPECTED_SHA}"
    )
    print(f"PASS  resolved 2.2.0 -> {snapshot.sha[:7]} ({snapshot.commit_date.date()})")

    # 2) A file read retains its text, canonical URL, and revision.
    record = read_file(repo, snapshot, PATH)
    assert "class AppContext" in record.content, "ctx.py does not look like the expected file"
    assert record.url.endswith(f"/blob/{EXPECTED_SHA}/{PATH}")
    assert record.content_revision, "blob revision was not retained"
    print(f"PASS  read {record.title}: {len(record.content.splitlines())} lines, "
          f"blob {record.content_revision[:7]}")

    # 3) Bounded history: three records, and the cutoff is visible.
    history, warning = list_file_history(repo, snapshot, PATH, limit=3)
    assert len(history) == 3, "expected exactly three history records"
    assert warning, "a bounded history must report its truncation"
    newest = history[0]
    print(f"PASS  file history bounded to {len(history)}: {warning}")

    # 4) The newest change to the file is inspectable. The stable commit ID
    #    ends with the commit SHA, so parse it back for the inspection call.
    newest_sha = newest.source_id.rsplit(":", 1)[-1]
    change, changed_files, change_warning = inspect_change(repo, snapshot, newest_sha)
    assert any(f.filename == PATH for f in changed_files), (
        "ctx.py is missing from the change that touched it"
    )
    print(f"PASS  inspected {newest_sha[:7]}: {len(changed_files)} file(s) changed"
          + (f"; {change_warning}" if change_warning else ""))
    print(f"      PR leads: {change.relationships or 'none found'}")

    # 5) Discovery without a path is bounded and deterministic.
    discovered, discovery_warning = discover_files(repo, snapshot, limit=5)
    assert len(discovered) == 5 and discovery_warning
    print(f"PASS  discovery bounded to {len(discovered)}: {', '.join(discovered[:3])}, ...")

    # 6) The two obvious miss cases fail with clear errors.
    def must_fail(what: str, fn) -> None:
        try:
            fn()
        except ValueError as exc:
            print(f"PASS  rejected: {what} ({exc})")
            return
        raise SystemExit(f"FAIL: accepted '{what}'")

    must_fail(
        "missing repository",
        lambda: get_repository(gh, "https://github.com/this-org-definitely-does-not-exist/missing"),
    )
    must_fail("missing ref", lambda: resolve_ref(gh, REPO, "no-such-ref-9999"))

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

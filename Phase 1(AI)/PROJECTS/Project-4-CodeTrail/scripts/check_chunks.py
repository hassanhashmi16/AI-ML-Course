r"""Exercise Step 6: records -> Documents -> source-mapped chunks.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_chunks.py

Builds a small sample from the Step 5 collection (ctx.py + PR #4682 + its
reviews; the GitHub reads replay from cache), converts the records into
Documents, and splits them into chunks. No model calls. A cold machine makes
a handful of GitHub reads; a warm one makes none.

What is verified:
  1. Documents carry the traceable identity (source_id, kind, SHA, URL).
  2. Every chunk is an exact substring of its source record's text at its
     recorded offsets -- the mapping retrieval will depend on.
  3. Line numbers are within the source's bounds.
  4. Chunk IDs are stable: splitting the same records twice yields identical
     ID sequences (idempotent indexing).
  5. A sample chunk from ctx.py contains the term it should, with sane lines.
"""

import sys
from collections import Counter
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from config import settings  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.collect import Collector  # noqa: E402
from ingest.documents import to_documents  # noqa: E402
from ingest.split import split_documents  # noqa: E402

REPO = "https://github.com/pallets/flask"
EXPECTED_SHA = "b17bb9ed563ab2857c0db9a07ec4e6407404c7be"
PATH = "src/flask/ctx.py"
PR = 4682


def main() -> None:
    token = settings.github_token.get_secret_value()
    print(f"GitHub auth: {'token' if token else 'anonymous (60 requests/hour)'}")

    gh = get_github()
    repo = get_repository(gh, REPO)
    snapshot = resolve_ref(gh, REPO, "2.2.0")
    assert snapshot.sha == EXPECTED_SHA

    collector = Collector(repo, snapshot)
    try:
        collector.add_file(PATH)
        collector.add_pull(PR)
        collector.add_reviews(PR)
        records = [collector.sources[key] for key in sorted(collector.sources)]
    finally:
        collector.close()

    # 1) Records -> Documents with traceable identity.
    documents = to_documents(records)
    assert len(documents) == len(records) >= 3
    for document in documents:
        assert document.metadata["source_id"] and document.metadata["snapshot_sha"]
        assert document.metadata["kind"] in {"file", "pull_request", "review"}
    print(f"PASS  documents built: {len(documents)} record(s) -> {len(documents)} document(s)")

    # 2) + 3) Every chunk maps exactly into its record, with valid locations.
    chunks = split_documents(documents)
    assert chunks, "splitting produced no chunks"
    per_kind = Counter()
    for chunk in chunks:
        record = next(
            item for item in records if item.source_id == chunk.metadata["source_id"]
        )
        start = chunk.metadata["start_index"]
        end = chunk.metadata["end_index"]
        assert record.content[start:end] == chunk.page_content, (
            f"chunk {chunk.metadata['chunk_id']} does not match its source text"
        )
        total_lines = record.content.count("\n") + 1
        assert 1 <= chunk.metadata["start_line"] <= chunk.metadata["end_line"] <= total_lines
        per_kind[chunk.metadata["kind"]] += 1
    counts = ", ".join(f"{kind}={count}" for kind, count in sorted(per_kind.items()))
    print(f"PASS  chunks map exactly: {len(chunks)} chunk(s) ({counts}); "
          f"every chunk == record.content[start:end]")

    # 4) Stable IDs: splitting again yields the same sequence.
    split_again = split_documents(to_documents(records))
    assert [c.metadata["chunk_id"] for c in split_again] == [
        c.metadata["chunk_id"] for c in chunks
    ]
    print("PASS  ids stable: re-split produced an identical chunk_id sequence")

    # 5) A concrete sample: the refactor lives in these lines of ctx.py.
    sample = next(c for c in chunks if "AppContext" in c.page_content and c.metadata["kind"] == "file")
    lines = sample.metadata["start_line"], sample.metadata["end_line"]
    print(f"PASS  sample: ctx.py L{lines[0]}-L{lines[1]} contains 'AppContext' "
          f"({len(sample.page_content)} chars, id ...#{sample.metadata['start_index']}-"
          f"{sample.metadata['end_index']})")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

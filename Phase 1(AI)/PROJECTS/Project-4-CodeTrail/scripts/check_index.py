r"""Exercise Step 7: embed chunks and index them in the local Qdrant.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_index.py

Builds a small sample from the Step 5 collection (ctx.py + PR #4682 + its
reviews; GitHub reads replay from cache), then exercises the local index.
No model calls; the first run downloads the local embedding model (~90 MB)
into the project's ignored .cache/ directory.

What is verified:
  1. A rebuild indexes every chunk; the point count matches the chunk count.
  2. The index survives closing and reopening the store (it lives on disk).
  3. Re-indexing unchanged data keeps the count identical (idempotent).
  4. A changed source replaces its own chunks: old points gone, new added.
  5. Changed embedding/splitter settings are refused until --rebuild.
"""

import sys
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from config import settings  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.collect import Collector  # noqa: E402
from ingest.documents import to_documents  # noqa: E402
from ingest.index import (  # noqa: E402
    IndexConfigMismatch,
    ensure_compatible,
    index_records,
    load_manifest,
)
from ingest.split import split_documents  # noqa: E402
from models import SourceKind  # noqa: E402
from retrieval.clients import (  # noqa: E402
    build_embeddings,
    build_vector_store,
    collection_name,
    open_qdrant,
)

REPO = "https://github.com/pallets/flask"
EXPECTED_SHA = "b17bb9ed563ab2857c0db9a07ec4e6407404c7be"
PATH = "src/flask/ctx.py"
PR = 4682


def main() -> None:
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

    embeddings = build_embeddings()
    collection = collection_name(snapshot)

    # 1) A clean rebuild indexes every chunk.
    client = open_qdrant()
    try:
        store = build_vector_store(client, embeddings, collection)
        result = index_records(client, store, collection, snapshot, records, rebuild=True)
        count = result["points"]
        assert count == result["chunks"] > 0, "every chunk must land as a point"
        print(f"PASS  rebuilt: {count} points from {result['chunks']} chunk(s) "
              f"({len(records)} source(s)) -> {collection}")
    finally:
        client.close()

    # 2) The index lives on disk: a brand-new client still sees it.
    client2 = open_qdrant()
    try:
        count2 = client2.count(collection_name=collection, exact=True).count
        assert count2 == count
        print(f"PASS  survives close/reopen: reopened store reports {count2} points")

        store2 = build_vector_store(client2, embeddings, collection)

        # 3) Re-indexing the same records changes nothing.
        again = index_records(client2, store2, collection, snapshot, records, rebuild=False)
        assert again["points"] == count2
        print(f"PASS  idempotent: re-indexing unchanged data kept {again['points']} points")

        # 4) A modified source replaces its own chunks (no stale points left).
        original = next(record for record in records if record.kind is SourceKind.FILE)
        modified = original.model_copy(
            update={
                "content": original.content + "\n\n# note appended by the reindex check\n",
                "content_revision": "check-modified",
            }
        )
        before = len(split_documents(to_documents([original])))
        after = len(split_documents(to_documents([modified])))
        replaced = index_records(client2, store2, collection, snapshot, [modified], rebuild=False)
        assert replaced["points"] == count2 - before + after, (
            "stale chunks were not replaced cleanly"
        )
        print(f"PASS  stale replaced: file chunks {before} -> {after}, "
              f"collection {count2} -> {replaced['points']} points")

        # Restore the original record and confirm the count returns.
        restored = index_records(client2, store2, collection, snapshot, records, rebuild=False)
        assert restored["points"] == count2
        print(f"PASS  restored: re-indexing the original kept {restored['points']} points")

        # 5) Changed settings are refused until an explicit rebuild.
        manifest = load_manifest(collection)
        assert manifest, "manifest must exist after indexing"
        keys = ("embed_provider", "embed_model", "embed_dim", "chunk_size", "chunk_overlap")
        subset = {key: manifest[key] for key in keys}
        tampered = {**subset, "chunk_size": subset["chunk_size"] + 100}
        try:
            ensure_compatible(tampered, subset)
        except IndexConfigMismatch as exc:
            print(f"PASS  mismatch refused: {exc}")
        else:
            raise SystemExit("FAIL: incompatible settings were accepted")

        print(f"PASS  manifest: {manifest['embed_provider']} / {manifest['embed_model']} / "
              f"dim {manifest['embed_dim']} / chunk {manifest['chunk_size']}-{manifest['chunk_overlap']}")
    finally:
        client2.close()

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

r"""Exercise Step 8: hybrid retrieval and reranking over the local index.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_search.py

Builds a small multi-file sample (4 Flask source files + PR #4682 + reviews),
rebuilds the local index with dense + sparse vectors, then verifies:

  1. A contaminant point from another repository ranks first WITHOUT a filter
     but never appears through search_evidence (repository + SHA filters).
  2. A semantic question retrieves the context-storage sources.
  3. A symbol-heavy question retrieves json/provider.py (dense first result is
     printed for comparison).
  4. Every returned chunk maps back to a collected record at its offsets.
  5. Reranking narrows wide candidates and attaches scores; disabled and
     failed reranking are labelled and keep the retrieval order.

No model API calls; the local reranker/sparse weights download once into the
ignored .cache/ directory. GitHub reads replay from the Step 5 cache.
"""

import sys
import uuid
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: E402

from config import settings  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.collect import Collector  # noqa: E402
from ingest.documents import to_documents  # noqa: E402
from ingest.index import index_records  # noqa: E402
from ingest.split import split_documents  # noqa: E402
from retrieval.clients import (  # noqa: E402
    build_embeddings,
    build_sparse_embedding,
    build_vector_store,
    collection_name,
    open_qdrant,
    reset_collection,
)
from retrieval.rerank import rerank_documents  # noqa: E402
from retrieval.search import search_evidence  # noqa: E402

REPO = "https://github.com/pallets/flask"
EXPECTED_SHA = "b17bb9ed563ab2857c0db9a07ec4e6407404c7be"
PR = 4682
FILES = [
    "src/flask/ctx.py",
    "src/flask/globals.py",
    "src/flask/json/provider.py",
    "src/flask/app.py",
]
SENTINEL_ID = "github:example/other-contamination@deadbeef:sentinel:1"


def main() -> None:
    gh = get_github()
    repo = get_repository(gh, REPO)
    snapshot = resolve_ref(gh, REPO, "2.2.0")
    assert snapshot.sha == EXPECTED_SHA

    collector = Collector(repo, snapshot)
    try:
        for path in FILES:
            collector.add_file(path)
        collector.add_pull(PR)
        collector.add_reviews(PR)
        records = [collector.sources[key] for key in sorted(collector.sources)]
    finally:
        collector.close()
    records_by_id = {record.source_id: record for record in records}

    embeddings = build_embeddings()
    sparse = build_sparse_embedding()
    collection = collection_name(snapshot)

    client = open_qdrant()
    try:
        # The sample index is rebuilt every run (dense + sparse schema).
        reset_collection(client, collection)
        store = build_vector_store(
            client, embeddings, collection, sparse_embedding=sparse, mode="hybrid"
        )
        result = index_records(client, store, collection, snapshot, records, rebuild=True)
        print(f"PASS  index rebuilt: {result['points']} points from {result['chunks']} "
              f"chunk(s), {len(records)} source(s)")

        # 1) Scope filter: prove a foreign-repository point cannot leak.
        sentinel = records[0].model_copy(
            update={
                "source_id": SENTINEL_ID,
                "repository": "https://github.com/example/other-contamination",
                "title": "sentinel",
                "content": "Contamination sentinel zanzibarquokka: unrelated evidence "
                           "from another repository.",
            }
        )
        sentinel_chunks = split_documents(to_documents([sentinel]))
        store.add_documents(
            documents=sentinel_chunks,
            ids=[str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.metadata["chunk_id"]))
                 for chunk in sentinel_chunks],
        )
        raw = store.similarity_search("zanzibarquokka contamination sentinel", k=3)
        assert any(d.metadata.get("source_id") == SENTINEL_ID for d in raw), (
            "the sentinel should match without filters -- otherwise this test proves nothing"
        )
        filtered, warning = search_evidence(
            client, embeddings, sparse, snapshot,
            "zanzibarquokka contamination sentinel", mode="hybrid", k=3,
        )
        assert warning is None
        assert all(d.metadata.get("source_id") != SENTINEL_ID for d in filtered), (
            "scope filter leaked a point from another repository"
        )
        print("PASS  scope filter: sentinel matches unfiltered, never through search_evidence")
        # Remove the sentinel so it cannot pollute later runs.
        client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[FieldCondition(key="metadata.source_id", match=MatchValue(value=SENTINEL_ID))]
            ),
        )

        # 2) A semantic question should reach the context-storage sources.
        semantic_query = "how does Flask keep application and request context state isolated?"
        semantic_docs, warning = search_evidence(
            client, embeddings, sparse, snapshot, semantic_query, mode="hybrid", k=5
        )
        assert warning is None and semantic_docs
        semantic_titles = [doc.metadata.get("title") for doc in semantic_docs]
        assert any(
            title in {"src/flask/ctx.py", "src/flask/globals.py"} for title in semantic_titles
        ), f"semantic question missed the context sources: {semantic_titles}"
        print(f"PASS  semantic (hybrid): {', '.join(str(t) for t in semantic_titles[:3])}")

        # 3) A symbol-heavy question should reach the JSON provider file.
        symbol_query = "JSONProvider DefaultJSONProvider"
        dense_docs, _ = search_evidence(
            client, embeddings, sparse, snapshot, symbol_query, mode="dense", k=5
        )
        hybrid_docs, _ = search_evidence(
            client, embeddings, sparse, snapshot, symbol_query, mode="hybrid", k=5
        )
        assert any(
            doc.metadata.get("title") == "src/flask/json/provider.py" for doc in hybrid_docs
        ), "symbol question missed json/provider.py"
        print(f"PASS  symbol (hybrid): first={hybrid_docs[0].metadata.get('title')} | "
              f"dense first={dense_docs[0].metadata.get('title') if dense_docs else 'n/a'}")

        # 4) Provenance: every returned chunk maps back to its record.
        for doc in semantic_docs + hybrid_docs:
            metadata = doc.metadata
            assert metadata["source_id"] in records_by_id
            assert metadata["repository"] == REPO and metadata["snapshot_sha"] == EXPECTED_SHA
            record = records_by_id[metadata["source_id"]]
            assert record.content[metadata["start_index"]:metadata["end_index"]] == doc.page_content
        print("PASS  provenance: every chunk maps to its record at its offsets")

        # 5) Reranking: wide candidates -> narrow, labelled when off.
        candidates, _ = search_evidence(
            client, embeddings, sparse, snapshot, semantic_query,
            mode="hybrid", k=settings.retrieve_k,
        )
        assert len(candidates) > settings.rerank_k
        ranked, warning = rerank_documents(semantic_query, candidates, top_k=settings.rerank_k)
        assert warning is None, warning
        assert len(ranked) == settings.rerank_k
        assert all("rerank_score" in doc.metadata for doc in ranked)
        assert {doc.metadata["chunk_id"] for doc in ranked} <= {
            doc.metadata["chunk_id"] for doc in candidates
        }
        print(f"PASS  reranked: {len(candidates)} candidates -> {len(ranked)} "
              f"(top score {ranked[0].metadata['rerank_score']})")

        disabled, disabled_warning = rerank_documents(
            semantic_query, candidates, top_k=settings.rerank_k, provider="none"
        )
        assert "disabled" in disabled_warning
        assert [d.metadata["chunk_id"] for d in disabled] == [
            d.metadata["chunk_id"] for d in candidates[: settings.rerank_k]
        ]
        print(f"PASS  disabled labelled: {disabled_warning}")

        # Failure path: simulate the local reranker crashing. This is
        # deterministic and makes no network calls (a configured Cohere key
        # would otherwise turn the "failure" case into a real success).
        import retrieval.rerank as rerank_module

        original_encoder = rerank_module._cross_encoder

        def _boom():
            raise RuntimeError("simulated reranker crash")

        rerank_module._cross_encoder = _boom
        try:
            failed, failed_warning = rerank_documents(
                semantic_query, candidates, top_k=settings.rerank_k
            )
        finally:
            rerank_module._cross_encoder = original_encoder
        assert "failed" in failed_warning
        assert [d.metadata["chunk_id"] for d in failed] == [
            d.metadata["chunk_id"] for d in candidates[: settings.rerank_k]
        ]
        print(f"PASS  failure labelled: {failed_warning}")
    finally:
        client.close()

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

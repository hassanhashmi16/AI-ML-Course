"""Index chunks into the local Qdrant collection, with a rebuild guard.

The rules this file enforces:

  * **stable point IDs** (uuid5 of the chunk_id), so re-indexing replaces
    points instead of duplicating them;
  * **per-source replacement** -- before a source's new chunks are added, its
    old points are deleted, so a changed source never leaves stale passages
    behind;
  * **an index manifest** recording provider/model/dimension/splitter
    settings. If any of them changes, indexing refuses until an explicit
    rebuild: old vectors were produced by different math and must not mix.

Run the ingest command with:
    python -m ingest.index --repo https://github.com/pallets/flask --ref 2.2.0 --path src/flask/ctx.py
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from config import settings
from github_source.client import get_github, get_repository, resolve_ref
from github_source.code import discover_files
from github_source.collect import Collector
from ingest.documents import to_documents
from ingest.split import CHUNK_OVERLAP, CHUNK_SIZE, split_documents
from models import RepoSnapshot, SourceRecord
from retrieval.clients import (
    build_embeddings,
    build_sparse_embedding,
    build_vector_store,
    collection_name,
    ensure_collection,
    open_qdrant,
    reset_collection,
)


class IndexConfigMismatch(ValueError):
    """The stored index was built with different settings than the current ones."""


def manifest_path(collection: str) -> Path:
    return settings.data_dir / "index" / f"{collection}.manifest.json"


def load_manifest(collection: str) -> dict | None:
    """The stored manifest for a collection, or None before the first build."""
    path = manifest_path(collection)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def current_settings(store) -> dict:
    """The settings a build would use now, with the embedder's real dimension."""
    dimension = len(store.embeddings.embed_query("dimension probe"))
    if settings.embed_provider == "google" and dimension != settings.embed_dim:
        raise ValueError(
            f"embedding dimension mismatch: model produced {dimension}, EMBED_DIM says {settings.embed_dim}"
        )
    return {
        "embed_provider": settings.embed_provider,
        "embed_model": (
            settings.fastembed_embed_model
            if settings.embed_provider == "fastembed"
            else settings.embed_model
        ),
        "embed_dim": dimension,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }


def ensure_compatible(previous: dict | None, current: dict) -> None:
    """Refuse to mix old vectors with new settings unless a rebuild is asked for."""
    if previous is None:
        return
    changed = [
        f"{key}: {previous.get(key)} -> {current.get(key)}"
        for key in current
        if previous.get(key) != current.get(key)
    ]
    if changed:
        raise IndexConfigMismatch(
            "index settings changed (" + "; ".join(changed) + "); rerun with --rebuild"
        )


def _replace_sources(client: QdrantClient, store, collection: str, chunks: list) -> None:
    """Delete each source's old points, then add its new chunks."""
    # After an explicit rebuild the collection was just deleted; recreate it
    # (sized to the embedder) before deleting/adding anything.
    ensure_collection(client, store.embeddings, collection)
    source_ids = sorted({chunk.metadata["source_id"] for chunk in chunks})
    for source_id in source_ids:
        client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="metadata.source_id",
                        match=MatchValue(value=source_id),
                    )
                ]
            ),
        )
    # uuid5 of the stable chunk_id: the same chunk always lands on the same
    # point ID, which is what makes re-indexing idempotent.
    point_ids = [
        str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.metadata["chunk_id"])) for chunk in chunks
    ]
    store.add_documents(documents=chunks, ids=point_ids)


def index_records(
    client: QdrantClient,
    store,
    collection: str,
    snapshot: RepoSnapshot,
    records: list[SourceRecord],
    rebuild: bool = False,
) -> dict:
    """Index these records' chunks; returns a summary of the collection state."""
    current = current_settings(store)
    previous = load_manifest(collection)
    if rebuild:
        # The caller deletes the collection first (its schema may have
        # changed); here a rebuild only means "do not compare manifests".
        previous = None
    ensure_compatible(previous, current)

    chunks = split_documents(to_documents(records))
    if chunks:
        _replace_sources(client, store, collection, chunks)

    count = (
        client.count(collection_name=collection, exact=True).count
        if client.collection_exists(collection)
        else 0
    )
    manifest = {
        **current,
        "collection": collection,
        "repository": snapshot.repository,
        "ref_requested": snapshot.ref_requested,
        "sha": snapshot.sha,
        "chunk_count": count,
        "sources_indexed": len({chunk.metadata["source_id"] for chunk in chunks}),
        "rebuilt": rebuild,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    path = manifest_path(collection)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "collection": collection,
        "chunks": len(chunks),
        "points": count,
        "manifest": path,
        "manifest_data": manifest,
    }


def main() -> None:
    """The ingest command: collect files, split them, index them locally."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="public GitHub repository URL")
    parser.add_argument("--ref", default=None, help="branch/tag (default: the repository's default branch)")
    parser.add_argument("--path", action="append", default=[], help="file path to index (repeatable)")
    parser.add_argument("--discover-limit", type=int, default=10, help="files to discover when no --path is given")
    parser.add_argument("--rebuild", action="store_true", help="rebuild the collection after a settings change")
    args = parser.parse_args()

    gh = get_github()
    repo = get_repository(gh, args.repo)
    snapshot = resolve_ref(gh, args.repo, args.ref)

    collector = Collector(repo, snapshot)
    try:
        if args.path:
            for path in args.path:
                collector.add_file(path)
        else:
            discovered, warning = discover_files(repo, snapshot, limit=args.discover_limit)
            if warning:
                print(warning)
            for path in discovered:
                collector.add_file(path)
        records = [collector.sources[key] for key in sorted(collector.sources)]
    finally:
        collector.close()

    collection = collection_name(snapshot)
    client = open_qdrant()
    try:
        if args.rebuild:
            reset_collection(client, collection)
        store = build_vector_store(
            client,
            build_embeddings(),
            collection,
            sparse_embedding=build_sparse_embedding(),
            mode="hybrid",
        )
        result = index_records(client, store, collection, snapshot, records, rebuild=args.rebuild)
    finally:
        client.close()

    print(f"indexed {result['chunks']} chunk(s) from {len(records)} source(s) "
          f"-> {result['collection']} ({result['points']} points)")
    print(f"manifest: {result['manifest']}")


if __name__ == "__main__":
    main()

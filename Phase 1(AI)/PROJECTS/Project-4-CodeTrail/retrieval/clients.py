"""Provider and store clients, built from settings in one place.

Two rules from the plan live here:

  * the dense embedder sits behind one interface and is recorded in the index
    manifest -- local FastEmbed by default (no API key, no quota), Google
    Generative AI embeddings when ``EMBED_PROVIDER=google``;
  * the vector store is a local on-disk Qdrant, and one process owns it.
"""

from __future__ import annotations

import re

from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, SparseVectorParams, VectorParams

from config import settings
from models import RepoSnapshot, repo_slug

# Local model weights live in the project's ignored .cache/ directory.
FASTEMBED_CACHE = settings.data_dir.parent / ".cache" / "fastembed"

# Name of the sparse vector field in every collection we create. Passed
# explicitly to the store as well, so the schema we create and the schema we
# query cannot drift apart.
SPARSE_VECTOR_NAME = "langchain-sparse"


class LocalEmbeddings(Embeddings):
    """LangChain-compatible wrapper around fastembed's local ONNX embedder.

    langchain-qdrant ships the sparse FastEmbed wrapper but not the dense one,
    and langchain-community is an eval-only dependency here -- so this small
    adapter is the dependency-free way to plug a local embedder into the same
    interface the vector store expects.
    """

    def __init__(self, model_name: str, cache_dir: str) -> None:
        from fastembed import TextEmbedding

        self.model_name = model_name
        # First construction downloads the model weights (once, into .cache).
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()


def build_embeddings() -> Embeddings:
    """The configured dense embedder (local by default, Google on request)."""
    if settings.embed_provider == "fastembed":
        return LocalEmbeddings(
            model_name=settings.fastembed_embed_model,
            cache_dir=str(FASTEMBED_CACHE),
        )
    if settings.embed_provider == "google":
        api_key = settings.gemini_api_key.get_secret_value()
        if not api_key:
            raise ValueError("EMBED_PROVIDER=google requires GEMINI_API_KEY in .env")
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=settings.embed_model,
            google_api_key=api_key,
        )
    raise ValueError(f"unsupported EMBED_PROVIDER: {settings.embed_provider!r}")


def open_qdrant() -> QdrantClient:
    """The local on-disk vector store. One process owns it at a time."""
    return QdrantClient(path=str(settings.data_dir / "qdrant"))


def collection_name(snapshot: RepoSnapshot) -> str:
    """One collection per repository@snapshot; Qdrant-safe characters only."""
    slug = repo_slug(snapshot.repository).replace("/", "_")
    return re.sub(r"[^0-9a-zA-Z_-]", "_", f"codetrail_{slug}_{snapshot.sha[:12]}").lower()


def ensure_collection(client: QdrantClient, embeddings: Embeddings, collection: str) -> None:
    """Create the collection with the embedder's true dimension, if missing.

    Collections are created hybrid-capable (dense + sparse vectors): dense-only
    search works on the same schema, and switching retrieval modes must not
    require a rebuild. Local-mode Qdrant raises "collection not found" (rather
    than answering a not-found response), and the LangChain store validates
    the collection on construction -- so it has to exist before the store.
    """
    if client.collection_exists(collection):
        return
    dimension = len(embeddings.embed_query("dimension probe"))
    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        sparse_vectors_config={SPARSE_VECTOR_NAME: SparseVectorParams()},
    )


def clear_points(client: QdrantClient, collection: str) -> int:
    """Remove every point in the collection, returning how many were removed."""
    removed = 0
    while True:
        points, _ = client.scroll(
            collection, limit=512, with_payload=False, with_vectors=False
        )
        ids = [point.id for point in points]
        if not ids:
            return removed
        client.delete(collection_name=collection, points_selector=ids)
        removed += len(ids)


def reset_collection(
    client: QdrantClient, embeddings: Embeddings, collection: str
) -> int:
    """Empty the collection for an explicit rebuild, keeping its schema.

    Local-mode Qdrant has been observed to resurrect points from a deleted
    collection when the same name is recreated right after (Windows can leave
    segment files behind), so a rebuild clears points instead of deleting and
    recreating, and then verifies emptiness. The schema is only recreated when
    the embedder's dimension actually changed.
    """
    dimension = len(embeddings.embed_query("dimension probe"))
    if client.collection_exists(collection):
        info = client.get_collection(collection_name=collection)
        current = getattr(info.config.params.vectors, "size", None)
        if current == dimension:
            return clear_points(client, collection)
        client.delete_collection(collection)
    ensure_collection(client, embeddings, collection)
    return clear_points(client, collection)


def build_sparse_embedding():
    """Local BM25-style sparse embedder for hybrid retrieval."""
    from langchain_qdrant import FastEmbedSparse

    return FastEmbedSparse(model_name=settings.sparse_model, cache_dir=str(FASTEMBED_CACHE))


def build_vector_store(
    client: QdrantClient,
    embeddings: Embeddings,
    collection: str,
    *,
    sparse_embedding=None,
    mode: str = "dense",
):
    """A LangChain store for dense or hybrid retrieval over one collection."""
    from langchain_qdrant import QdrantVectorStore, RetrievalMode

    ensure_collection(client, embeddings, collection)
    if sparse_embedding is not None:
        # A collection created before hybrid support has no sparse field, and
        # Qdrant cannot add one to an existing collection here -- so the honest
        # answer is an explicit rebuild.
        info = client.get_collection(collection_name=collection)
        if not info.config.params.sparse_vectors:
            raise ValueError(
                f"collection {collection} has no sparse vectors (built before hybrid "
                "retrieval); rerun the ingest command with --rebuild"
            )
    retrieval_mode = RetrievalMode.HYBRID if mode == "hybrid" else RetrievalMode.DENSE
    return QdrantVectorStore(
        client=client,
        collection_name=collection,
        embedding=embeddings,
        sparse_embedding=sparse_embedding,
        retrieval_mode=retrieval_mode,
        sparse_vector_name=SPARSE_VECTOR_NAME,
    )

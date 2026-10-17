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
from qdrant_client.models import Distance, VectorParams

from config import settings
from models import RepoSnapshot, repo_slug

# Local model weights live in the project's ignored .cache/ directory.
FASTEMBED_CACHE = settings.data_dir.parent / ".cache" / "fastembed"


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

    Local-mode Qdrant raises "collection not found" (rather than answering a
    not-found response), and the LangChain store validates the collection on
    construction -- so the collection has to exist first, sized to the
    embedder's actual output dimension.
    """
    if client.collection_exists(collection):
        return
    dimension = len(embeddings.embed_query("dimension probe"))
    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
    )


def build_vector_store(client: QdrantClient, embeddings: Embeddings, collection: str):
    """The LangChain vector store bound to this client, collection, embedder."""
    from langchain_qdrant import QdrantVectorStore

    ensure_collection(client, embeddings, collection)
    return QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings)

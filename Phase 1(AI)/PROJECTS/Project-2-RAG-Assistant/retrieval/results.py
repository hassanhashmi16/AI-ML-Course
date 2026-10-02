"""The one result type every retriever returns.

Dense (Step 8), sparse (Step 9), and the fused/reranked pipeline (Step 11) all
speak this shape, so they can be mixed freely and nothing downstream has to know
which retriever produced a chunk.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Retrieved:
    """One chunk returned from a search.

    `score` is always "higher is better" so results are comparable at a glance
    (dense returns cosine similarity, sparse returns a text rank). Fusion in
    Step 11 deliberately ignores the score and uses only the ORDER, because two
    retrievers' scores are not on the same scale and cannot be added.
    """

    chunk_id: int
    content: str
    section: str
    source: str
    peak: str | None
    score: float

    def label(self) -> str:
        """Short human label, e.g. 'k2.txt > Climbing history'."""
        return f"{self.source} > {self.section}"

    def preview(self, width: int = 80) -> str:
        """First `width` characters of the body, flattened to one line."""
        body = self.content.split("\n", 1)[-1]  # drop the breadcrumb line
        return " ".join(body.split())[:width]

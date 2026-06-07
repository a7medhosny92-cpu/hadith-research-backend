"""Pluggable text embeddings for semantic search (production).

The production search is hybrid: FTS for lexical recall + vector similarity for
meaning. Embeddings sit behind a tiny :class:`Embedder` protocol so the model is
swappable and the heavy dependency (torch/sentence-transformers) stays optional.

:func:`load_embedder` returns a :class:`SentenceTransformerEmbedder` (the Arabic
model in settings) when the ``embeddings`` extra is installed, else a deterministic
:class:`HashingEmbedder` — a stdlib bag-of-hashes baseline so the vector pipeline is
exercisable anywhere (it is lexical, not semantic; it just keeps the plumbing live).
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, Sequence, runtime_checkable

from app.parsing.normalize import normalize_for_search


@runtime_checkable
class Embedder(Protocol):
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one L2-normalised vector per input text."""
        ...


class HashingEmbedder:
    """Deterministic hashing bag-of-words vectors (no ML deps). A baseline only."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in normalize_for_search(text).split():
                bucket = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dim
                vec[bucket] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            vectors.append([x / norm for x in vec])
        return vectors


class SentenceTransformerEmbedder:
    """Real semantic embeddings via sentence-transformers (lazy, optional dep)."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # lazy: optional extra

        self._model = SentenceTransformer(model_name)
        # sentence-transformers renamed get_sentence_embedding_dimension →
        # get_embedding_dimension; prefer the new name, fall back for older versions.
        get_dim = getattr(self._model, "get_embedding_dimension", None) \
            or self._model.get_sentence_embedding_dimension
        self.dim = int(get_dim())

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vecs = self._model.encode(list(texts), normalize_embeddings=True)
        return [v.tolist() for v in vecs]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # inputs are L2-normalised


def load_embedder(settings) -> Embedder:
    """Best available embedder: the configured ST model, else the hashing baseline."""
    try:
        return SentenceTransformerEmbedder(settings.embedding_model)
    except Exception:  # noqa: BLE001 — torch/model not available → baseline
        return HashingEmbedder()

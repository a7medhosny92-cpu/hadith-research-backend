"""Hybrid retrieval: fuse lexical (FTS) and semantic (vector) rankings.

Lexical search nails exact wording; semantic search catches meaning when the words
differ (synonyms, paraphrase). We run both and combine them with **Reciprocal Rank
Fusion** — a robust, score-free merge that just needs each side's ordering.

:class:`HybridSearcher` quacks like :meth:`HadithIndex.search`, so it's a drop-in for
retrieval (e.g. in /ask). With no vector index or embedder available it degrades
cleanly to pure lexical search, so nothing breaks before the corpus is embedded.
"""

from __future__ import annotations

from app.search.embeddings import Embedder
from app.search.index import HadithIndex, SearchHit
from app.search.vectors import VectorIndex


def rrf_fuse(rankings: list[list[int]], *, k: int = 60) -> list[int]:
    """Merge several best-first id rankings into one via Reciprocal Rank Fusion.

    Each id scores ``Σ 1/(k + rank)`` across the rankings it appears in; ``k`` damps
    the weight of low ranks. Ids seen in more than one ranking rise to the top.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, rid in enumerate(ranking):
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda rid: -scores[rid])


def _passes(hit: SearchHit, collection_id: int | None, grade: str | None) -> bool:
    if collection_id is not None and hit.book_id != collection_id:
        return False
    if grade is not None and hit.grade != grade:
        return False
    return True


class HybridSearcher:
    """Lexical + semantic retrieval over a shared id space, fused with RRF."""

    def __init__(
        self,
        lexical: HadithIndex,
        vectors: VectorIndex | None = None,
        embedder: Embedder | None = None,
        *,
        rrf_k: int = 60,
    ) -> None:
        self.lexical = lexical
        self.vectors = vectors
        self.embedder = embedder
        self.rrf_k = rrf_k

    def semantic_ready(self) -> bool:
        return bool(self.vectors is not None and self.embedder is not None and self.vectors.count())

    def search(
        self,
        query: str,
        *,
        limit: int | None = 20,
        collection_id: int | None = None,
        grade: str | None = None,
        field: str = "all",
        mode: str = "hybrid",
    ) -> list[SearchHit]:
        """Rank hadith for ``query``. ``mode``: ``lexical`` | ``semantic`` | ``hybrid``.

        Without a usable vector backend any mode falls back to lexical, so callers can
        always ask for ``hybrid`` and simply get the best available retrieval.
        ``limit=None`` means "no cap" — only meaningful for lexical search; the
        semantic/hybrid modes are inherently top-k, so a missing limit defaults to 50.
        """
        if mode == "lexical" or not self.semantic_ready():
            return self.lexical.search(
                query, limit=limit, collection_id=collection_id, grade=grade, field=field
            )

        limit = limit or 50
        filtered = collection_id is not None or grade is not None
        # Without a filter a modest candidate pool is enough. With one, most candidates
        # are discarded, so we must look deeper or matches ranked past the pool are lost
        # (a collection's only hits could sit beyond a small cutoff → empty result).
        pool = max(self.vectors.count(), limit) if filtered else max(limit * 4, 40)
        qvec = self.embedder.embed([query])[0]
        semantic_ids = [rid for rid, _ in self.vectors.search(qvec, k=pool)]
        if mode == "semantic":
            ordered = semantic_ids
        else:  # hybrid — the lexical side is filtered in SQL (exact, cheap)
            lexical_ids = [h.id for h in self.lexical.search(
                query, limit=pool, collection_id=collection_id, grade=grade, field=field)]
            ordered = rrf_fuse([lexical_ids, semantic_ids], k=self.rrf_k)

        out: list[SearchHit] = []
        for rid in ordered:
            hit = self.lexical.get(rid)
            if hit and _passes(hit, collection_id, grade):
                out.append(hit)
                if len(out) >= limit:
                    break
        return out

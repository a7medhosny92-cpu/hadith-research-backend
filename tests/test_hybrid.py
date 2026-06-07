"""Tests for hybrid retrieval (lexical + semantic, fused with RRF)."""

from __future__ import annotations

import pytest

from app.search import HadithIndex, HybridSearcher, VectorIndex, rrf_fuse
from app.search.embeddings import HashingEmbedder

SAMPLE = [
    {"book_id": 1284, "number": 1, "matn": "إنما الأعمال بالنيات", "isnad": "حدثنا الحميدي",
     "grade": "صحيح", "chapter": "بدء الوحي", "page": 1, "volume": "1"},
    {"book_id": 1727, "number": 3, "matn": "من كذب علي متعمدا فليتبوأ مقعده من النار",
     "isnad": "حدثنا أبو بكر", "grade": "صحيح", "chapter": "المقدمة", "page": 2, "volume": "1"},
    {"book_id": 1726, "number": 1, "matn": "الطهور شطر الإيمان والحمد لله تملأ الميزان",
     "isnad": "حدثنا القعنبي", "grade": "صحيح", "chapter": "الطهارة", "page": 3, "volume": "1"},
]


def _build():
    """A lexical index plus a vector index over the same rows (shared ids)."""
    lex = HadithIndex()
    lex.add(SAMPLE)
    emb = HashingEmbedder(dim=64)
    vec = VectorIndex(dim=64)
    ids, texts = zip(*list(lex.iter_for_embedding()))
    vec.add(list(ids), emb.embed(list(texts)))
    return lex, vec, emb


# ── RRF ───────────────────────────────────────────────────────────────────────
def test_rrf_rewards_agreement():
    # 30 appears high in both rankings → it should win.
    fused = rrf_fuse([[10, 20, 30], [30, 40, 50]])
    assert fused[0] == 30
    assert set(fused) == {10, 20, 30, 40, 50}


def test_rrf_empty():
    assert rrf_fuse([]) == []


# ── HybridSearcher ────────────────────────────────────────────────────────────
def test_falls_back_to_lexical_without_vectors():
    lex = HadithIndex()
    lex.add(SAMPLE)
    searcher = HybridSearcher(lex, None, None)
    assert not searcher.semantic_ready()
    hits = searcher.search("الأعمال بالنيات", mode="hybrid")
    assert hits and hits[0].number == 1  # identical to lexical


def test_semantic_ready_with_vectors():
    lex, vec, emb = _build()
    assert HybridSearcher(lex, vec, emb).semantic_ready()


def test_hybrid_retrieves_shared_ids():
    lex, vec, emb = _build()
    searcher = HybridSearcher(lex, vec, emb)
    hits = searcher.search("الأعمال بالنيات", limit=3, mode="hybrid")
    assert hits and hits[0].number == 1
    assert all(h.collection for h in hits)  # ids resolved to full records


def test_semantic_mode_returns_hits():
    lex, vec, emb = _build()
    searcher = HybridSearcher(lex, vec, emb)
    hits = searcher.search("كذب متعمدا", limit=3, mode="semantic")
    assert any(h.number == 3 for h in hits)


def test_filters_apply_in_hybrid():
    lex, vec, emb = _build()
    searcher = HybridSearcher(lex, vec, emb)
    hits = searcher.search("الإيمان", limit=5, collection_id=1726, mode="hybrid")
    assert all(h.book_id == 1726 for h in hits)


def test_limit_none_defaults_for_semantic():
    lex, vec, emb = _build()
    searcher = HybridSearcher(lex, vec, emb)
    # limit=None is fine for lexical (uncapped); semantic/hybrid coerce it to a top-k
    assert searcher.search("الإيمان", limit=None, mode="semantic") is not None


# A body-less row (chapter/bāb marker): empty matn, but a chapter heading that gets
# embedded — so semantic search *could* surface it. It must never appear in results.
BODYLESS = {"book_id": 1284, "number": 99, "matn": "  ", "isnad": "حدثنا الحميدي",
            "grade": None, "chapter": "إنما الأعمال بالنيات", "page": 9, "volume": "1"}


def _build_with_bodyless():
    lex = HadithIndex()
    lex.add([*SAMPLE, BODYLESS])
    emb = HashingEmbedder(dim=64)
    vec = VectorIndex(dim=64)
    ids, texts = zip(*list(lex.iter_for_embedding()))
    vec.add(list(ids), emb.embed(list(texts)))
    return lex, vec, emb


def test_semantic_skips_bodyless_rows():
    lex, vec, emb = _build_with_bodyless()
    searcher = HybridSearcher(lex, vec, emb)
    # its chapter heading is the query verbatim, so without the guard it would rank top
    hits = searcher.search("إنما الأعمال بالنيات", limit=10, mode="semantic")
    assert hits and all(h.matn.strip() for h in hits)
    assert all(h.number != 99 for h in hits)


def test_hybrid_skips_bodyless_rows():
    lex, vec, emb = _build_with_bodyless()
    searcher = HybridSearcher(lex, vec, emb)
    hits = searcher.search("إنما الأعمال بالنيات", limit=10, mode="hybrid")
    assert all(h.number != 99 for h in hits)

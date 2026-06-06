"""Filtered hybrid/semantic search and original-spelling snippets (audit SRCH-1/2)."""

from __future__ import annotations

from app.config import get_settings
from app.search import HadithIndex
from app.search.embeddings import load_embedder
from app.search.hybrid import HybridSearcher
from app.search.vectors import VectorIndex


def _searcher():
    idx = HadithIndex()
    recs = [{"book_id": 1, "number": i, "matn": "الصلاة عماد الدين وأساسه", "isnad": "حدثنا أ"}
            for i in range(1, 101)]
    recs += [{"book_id": 2, "number": i, "matn": "الصلاة خير موضوع فأكثر منها", "isnad": "حدثنا ب"}
             for i in range(1, 4)]
    idx.add(recs)
    emb = load_embedder(get_settings())
    vec = VectorIndex(dim=emb.dim)
    ids, texts = zip(*list(idx.iter_for_embedding()))
    vec.add(list(ids), emb.embed(list(texts)))
    return HybridSearcher(idx, vec, emb)


def test_filtered_hybrid_finds_matches_beyond_the_pool():
    hs = _searcher()
    for mode in ("hybrid", "semantic"):
        out = hs.search("الصلاة", limit=3, collection_id=2, mode=mode)
        assert out, f"{mode} returned nothing"
        assert all(h.book_id == 2 for h in out)


def test_snippet_keeps_original_orthography():
    idx = HadithIndex()
    idx.add([{"book_id": 1, "number": 1,
              "matn": "إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ وإنما لكل امرئ ما نوى", "isnad": "حدثنا"}])
    snip = idx.search("الأعمال")[0].snippet
    assert "الْأَعْمَالُ" in snip          # diacritics preserved (not the folded form)
    assert "«الْأَعْمَالُ»" in snip        # the match is highlighted

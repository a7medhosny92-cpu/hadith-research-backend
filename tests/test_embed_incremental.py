"""Incremental embedding: only new/changed matns are embedded (audit PERF-1)."""

from __future__ import annotations

from app.config import Settings
from app.search import HadithIndex
from scripts.embed import embed_corpus, seed_cache


def _index(settings, matns):
    idx = HadithIndex(settings.index_path)
    idx.add([{"book_id": 1, "number": i, "matn": m, "isnad": "حدثنا فلان"}
             for i, m in enumerate(matns, 1)])
    idx.close()


def _settings(tmp_path):
    s = Settings(data_dir=tmp_path)
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s


def test_second_run_reuses_all_vectors(tmp_path):
    s = _settings(tmp_path)
    _index(s, ["إنما الأعمال بالنيات", "من حسن إسلام المرء", "الدين النصيحة"])
    total, new, reused = embed_corpus(s, batch=2)
    assert (total, new, reused) == (3, 3, 0)            # cold cache → all embedded
    total, new, reused = embed_corpus(s, batch=2)
    assert (total, new, reused) == (3, 0, 3)            # warm cache → all reused


def test_only_changed_matn_is_re_embedded(tmp_path):
    s = _settings(tmp_path)
    _index(s, ["متن أول", "متن ثان"])
    embed_corpus(s)
    # re-index with one matn changed; row ids are reassigned but the cache is by content
    s.index_path.unlink()
    _index(s, ["متن أول", "متن ثالث معدّل"])
    total, new, reused = embed_corpus(s)
    assert total == 2 and new == 1 and reused == 1


def test_seed_cache_lets_next_embed_reuse(tmp_path):
    s = _settings(tmp_path)
    _index(s, ["حديث واحد", "حديث اثنان"])
    embed_corpus(s, use_cache=False)                    # build vectors.db without a cache
    assert not s.embed_cache_path.exists()
    assert seed_cache(s) == 2                           # seed the cache from vectors.db
    total, new, reused = embed_corpus(s)
    assert (new, reused) == (0, 2)                      # next embed reuses everything

"""Tests for the atomic rebuild helper (build-then-swap)."""

from __future__ import annotations

from app.search import HadithIndex
from scripts._atomic import rebuild

REC = [{"book_id": 1284, "number": 1, "matn": "إنما الأعمال بالنيات", "isnad": "س",
        "grade": "صحيح", "chapter": "بدء الوحي", "page": 1, "volume": "1"}]


def _build(tmp):
    idx = HadithIndex(tmp)
    idx.add(REC)
    return idx


def test_rebuild_creates_target_and_cleans_temp(tmp_path):
    target = tmp_path / "index.db"
    n = rebuild(target, _build)
    assert n == 1 and target.exists()
    assert not (tmp_path / "index.db.tmp").exists()      # temp swapped in, not left behind


def test_rebuild_replaces_existing_and_stays_queryable(tmp_path):
    target = tmp_path / "index.db"
    rebuild(target, _build)
    n = rebuild(target, _build)                           # rebuild over an existing file
    assert n == 1
    assert HadithIndex(target).count() == 1              # the swapped-in index works

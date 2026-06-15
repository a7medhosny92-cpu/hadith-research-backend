"""Tests for the atomic rebuild helper (build-then-swap)."""

from __future__ import annotations

import pytest

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


def test_parse_drops_stale_rijal_output(tmp_path):
    # a رجال book parsed-as-hadith in an earlier run leaves a processed/{id}.jsonl; the next parse
    # SKIPS it but must DELETE that stale output, else it lingers in the rebuilt hadith index
    # (تهذيب الكمال 3722's tarjamas resurfacing as bogus «hadith» chains in the audit).
    from scripts.parse import _drop_stale
    out_dir = tmp_path / "processed"
    sharh_dir = out_dir / "sharh"
    sharh_dir.mkdir(parents=True)
    (out_dir / "3722.jsonl").write_text("{}\n", encoding="utf-8")
    assert _drop_stale(out_dir, sharh_dir, 3722) is True
    assert not (out_dir / "3722.jsonl").exists()
    assert _drop_stale(out_dir, sharh_dir, 3722) is False   # idempotent — nothing left to drop


def test_compare_company_overlap_and_distinctive_sets():
    # The ②a-vs-②b lever: two سفيان with DISJOINT تلاميذ/شيوخ → Jaccard 0, all company distinctive.
    from scripts.compare_company import _names, _overlap
    a = [{"name": "وكيع", "count": 3}, {"name": "عبد الرزاق", "count": 1}]
    b = [{"name": "الحميدي", "count": 2}, {"name": "الشافعي", "count": 1}]
    jac, shared, only_a, only_b = _overlap(_names(a), _names(b))
    assert jac == 0.0 and not shared
    assert only_a == {"وكيع", "عبد الرزاق"} and only_b == {"الحميدي", "الشافعي"}
    # a shared تلميذ lifts the overlap (the ②b floor signal)
    jac2, shared2, _, _ = _overlap({"وكيع", "x"}, {"وكيع", "y"})
    assert shared2 == {"وكيع"} and jac2 == pytest.approx(1 / 3)


def test_audit_conflicts_holds_a_grave_trust_collision():
    # The رجال conflict sweep must (a) ignore a lone grave / unrelated names, and (b) report a
    # grave↔trustworthy collision as HELD — never DANGEROUS — now that _lookup holds it ambiguous.
    from scripts.audit_conflicts import sweep
    from app.rijal import RijalIndex
    rij = RijalIndex([
        {"name": "سعيد بن مرة", "grade": "متروك"},          # bare grave …
        {"name": "سعيد بن مرة الكوفي", "grade": "ثقة"},      # … shadowed by a fuller trustworthy namesake
        {"name": "زيد بن خالد الجهني", "grade": "صحابي"},    # unrelated — not a collision
    ])
    res = sweep(rij)
    assert not res["dangerous"]        # the _lookup hold fix means none sink a chain
    assert res["held"] == 1            # the «سعيد بن مرة» collision is held ambiguous (correct)

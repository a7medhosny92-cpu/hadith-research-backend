"""Double-opinion rijal: keep both critics' verdicts and expose divergence (P1.2)."""

from __future__ import annotations

from app.rijal.index import RijalIndex
from scripts.build_rijal import _add_opinion, merge_source


def test_both_opinions_kept_when_critics_differ():
    primary = [{"name": "فلان بن علان الكوفي", "grade": "ثقة", "source": "تقريب التهذيب (رقم 1)"}]
    for r in primary:                                  # the authority's own opinion
        _add_opinion(r, r["source"], r["grade"])
    secondary = [{"name": "فلان بن علان الكوفي", "grade": "صدوق", "source": "الكاشف (رقم 2)"}]

    merged, added, upgraded = merge_source(primary, secondary)
    ops = merged[0]["opinions"]
    assert {o["source"]: o["grade"] for o in ops} == {"تقريب التهذيب": "ثقة", "الكاشف": "صدوق"}
    # the verdict driver stays the authority's grade; it round-trips through the index
    d = RijalIndex(merged).lookup("فلان بن علان الكوفي").to_dict()
    assert d["grade"] == "ثقة" and len(d["opinions"]) == 2


def test_no_divergence_when_critics_agree():
    primary = [{"name": "ثقة بن ثقة الثقفي", "grade": "ثقة", "source": "تقريب التهذيب (رقم 9)"}]
    for r in primary:
        _add_opinion(r, r["source"], r["grade"])
    merged, *_ = merge_source(primary, [
        {"name": "ثقة بن ثقة الثقفي", "grade": "ثقة حافظ", "source": "الكاشف (رقم 9)"}])
    # both classify to ثقة → a single distinct opinion (UI shows nothing to flag)
    assert {o["grade"] for o in merged[0]["opinions"]} == {"ثقة"}

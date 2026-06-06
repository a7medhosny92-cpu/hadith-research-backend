"""Tests for scholars' rulings extraction (أحكام المحدّثين)."""

from __future__ import annotations

from app.qa.rulings import collect_rulings, extract_rulings, has_divergence, refine_with_routes


def _pairs(rulings):
    return [(r["scholar"], r["verdict"]) for r in rulings]


def test_attributed_verdicts_and_order():
    # Later scholar first in the text, but output is sorted by era (طبقة).
    r = extract_rulings("صحّحه ابن حجر وضعّفه الألباني")
    assert _pairs(r) == [("ابن حجر العسقلاني", "صحيح"), ("الألباني", "ضعيف")]
    assert r[0]["year"] < r[1]["year"]
    assert r[0]["era"] == "852هـ"          # هـ after the hijri year


def test_qala_with_verdict():
    r = extract_rulings("قال الترمذي هذا حديث حسن صحيح")
    assert ("الترمذي", "حسن صحيح") in _pairs(r)


def test_implicit_from_takhrij():
    r = extract_rulings("رواه البخاري في صحيحه")
    assert ("البخاري", "صحيح") in _pairs(r)
    assert r[0]["basis"] == "تخريج"


def test_implicit_shart_al_shaykhayn():
    r = extract_rulings("هذا حديث على شرط الشيخين ولم يخرجاه")
    assert {("البخاري", "صحيح"), ("مسلم", "صحيح")} <= set(_pairs(r))


def test_no_false_positive_without_scholar():
    assert extract_rulings("هذا الكلام جميل ولا يتعلق بالحكم") == []


def test_tirmidhi_composite_forms():
    assert ("الترمذي", "حسن صحيح غريب") in _pairs(
        extract_rulings("قال الترمذي هذا حديث حسن صحيح غريب")
    )
    assert ("الترمذي", "صحيح غريب") in _pairs(extract_rulings("قال الترمذي صحيح غريب"))
    assert ("الترمذي", "غريب") in _pairs(extract_rulings("قال الترمذي هذا حديث غريب"))


def test_hasan_sahih_carries_a_note():
    r = extract_rulings("قال الترمذي حسن صحيح")[0]
    assert r["verdict"] == "حسن صحيح" and r["note"]      # explanation attached


def test_refine_with_routes_resolves_hasan_sahih():
    multi = refine_with_routes([{"verdict": "حسن صحيح", "note": ""}], routes=3)
    assert "أكثر" in multi[0]["note"]               # more than one chain
    single = refine_with_routes([{"verdict": "حسن صحيح", "note": ""}], routes=1)
    assert "واحد" in single[0]["note"]              # a single chain


def test_collect_merges_and_detects_divergence():
    merged = collect_rulings(["صحّحه ابن حجر", "ضعّفه الألباني", "صحّحه ابن حجر"])
    assert len(merged) == 2                 # duplicate ابن حجر collapsed
    assert has_divergence(merged)           # صحيح vs ضعيف
    assert not has_divergence(extract_rulings("صحّحه ابن حجر"))

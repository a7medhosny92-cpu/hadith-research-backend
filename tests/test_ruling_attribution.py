"""Scholars' ruling attribution must be precise (audit RUL-1/2/3/4)."""

from __future__ import annotations

from app.qa.rulings import extract_rulings


def _pairs(text):
    return [(r["scholar"], r["verdict"]) for r in extract_rulings(text)]


def test_verdict_not_attributed_across_a_new_qala_clause():
    # the ضعيف belongs to al-Daraqutni's clause, never to al-Bukhari's
    pairs = _pairs("قال البخاري رجاله ثقات وقال الدارقطني هو ضعيف")
    assert ("البخاري", "ضعيف") not in pairs
    assert ("الدارقطني", "ضعيف") in pairs


def test_scholar_before_verb_is_recognised():
    assert _pairs("ابن حجر صححه") == [("ابن حجر العسقلاني", "صحيح")]
    assert _pairs("الألباني ضعفه في الضعيفة") == [("الألباني", "ضعيف")]


def test_takhrij_records_both_shaykhayn_anywhere_in_the_window():
    pairs = _pairs("رواه النسائي والبخاري ومسلم")
    assert ("البخاري", "صحيح") in pairs and ("مسلم", "صحيح") in pairs


def test_bare_muslim_is_not_imam_muslim():
    assert _pairs("قال رجل مسلم هذا صحيح") == []
    # but a takhrij by Muslim is still implicit صحيح
    assert _pairs("رواه مسلم") == [("مسلم", "صحيح")]

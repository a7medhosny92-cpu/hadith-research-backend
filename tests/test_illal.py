"""Stated hidden-defect (علل) extraction (roadmap P1.3)."""

from __future__ import annotations

from app.qa.rulings import collect_illal, extract_illal


def _types(text):
    return {d["type"] for d in extract_illal(text)}


def test_recognises_stated_defects_with_attribution():
    out = extract_illal("هذا حديث الصواب إرساله، وقد أعلّه الدارقطني")
    types = {d["type"]: d["scholar"] for d in out}
    assert "إرسال" in types
    assert types.get("علّة") == "الدارقطني"
    assert "تفرّد" in _types("تفرد به فلان ولم يروه غيره")
    assert "وقف" in _types("والصواب وقفه على الصحابي")


def test_negation_is_respected():
    assert extract_illal("قال ليس بمنكر بل هو صحيح") == []


def test_collect_merges_one_per_type():
    out = collect_illal(["وقفه ابن معين والصواب وقفه", "تفرد به راوٍ", "وقفه آخر"])
    assert {d["type"] for d in out} == {"وقف", "تفرّد"}      # «وقف» de-duplicated


def test_clean_text_has_no_false_defects():
    assert extract_illal("إنما الأعمال بالنيات وإنما لكل امرئ ما نوى") == []

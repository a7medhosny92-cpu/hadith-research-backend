"""Negation must cancel a verdict, never flip it positive (audit GRD-1/2/3)."""

from __future__ import annotations

from app.parsing.grading import extract_grade
from app.qa.rulings import extract_rulings
from app.rijal.grades import classify


def test_classify_negated_tawthiq_is_not_thiqa():
    assert classify("غير عدل") == ("غير معروف", None)
    assert classify("ليس بعدل") == ("غير معروف", None)
    # the positive forms still classify correctly
    assert classify("عدل")[0] == "ثقة"
    assert classify("ثقة حافظ")[0] == "ثقة"
    # an already-negative verdict is unaffected
    assert classify("ضعيف")[0] == "ضعيف"


def test_rulings_drop_negated_tashih():
    assert extract_rulings("لم يصحح الألباني هذا الحديث") == []
    assert extract_rulings("قال الترمذي حديث غير صحيح") == []
    # the positive statements are still recorded
    assert [(r["scholar"], r["verdict"]) for r in extract_rulings("وصححه الألباني")] == [("الألباني", "صحيح")]
    assert [(r["scholar"], r["verdict"]) for r in extract_rulings("قال الترمذي حسن صحيح")] == [("الترمذي", "حسن صحيح")]


def test_grade_extraction_is_negation_safe():
    # the grading-context cue must sit immediately before the grade, so an intervening
    # negator breaks the match — no positive grade is emitted
    assert extract_grade("إسناده غير صحيح") is None
    assert extract_grade("حديث ليس بصحيح") is None
    assert extract_grade("إسناده صحيح") == "صحيح"


def test_false_prophet_epithet_is_not_a_jarh():
    # a leaked matn «جاء مسيلمة الكذّاب إلى رسول الله ﷺ …» must NOT grade the narrator (أبو عامر
    # العقدي, ثقة) «كذّاب» and sink a صحيح البخاري chain — مسيلمة الكذّاب is a story character.
    assert classify("جاء مسيلمة الكذاب إلى رسول الله صلى الله عليه وسلم فلما قام") == ("غير معروف", None)
    assert classify("الأسود العنسي الكذاب")[0] == "غير معروف"
    # but a REAL كذّاب verdict is kept — even one that mentions forging «على رسول الله ﷺ»
    assert classify("كذاب")[0] == "كذاب"
    assert classify("كذاب يضع الحديث على رسول الله صلى الله عليه وسلم")[0] == "كذاب"
    assert classify("الأسود بن يزيد النخعي ثقة")[0] == "ثقة"   # a real narrator «الأسود» untouched

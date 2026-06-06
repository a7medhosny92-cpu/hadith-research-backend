"""The matn must not swallow an editorial/takhrij tail between quotes (audit PARSE-1)."""

from __future__ import annotations

from app.parsing.isnad_matn import split_isnad_matn


def test_editorial_tail_after_the_matn_is_dropped():
    _, matn, conf = split_isnad_matn(
        'حدثنا فلان يقول: "إنما الأعمال بالنيات" قال أبو عبد الله: ويقال "نية" بمعنى آخر'
    )
    assert conf == "quote"
    assert matn == "إنما الأعمال بالنيات"


def test_takhrij_reference_tail_is_dropped():
    _, matn, _ = split_isnad_matn('حدثنا فلان قال: "متن الحديث" تحفة الأشراف 123')
    assert matn == "متن الحديث"


def test_dialogue_spans_are_kept_whole():
    _, matn, _ = split_isnad_matn(
        'حدثنا فلان قال: «جاء رجل» فقال له النبي: «اذهب» فقال: «نعم»'
    )
    assert "جاء رجل" in matn and "اذهب" in matn and "نعم" in matn


def test_phrase_and_none_fallbacks_unchanged():
    assert split_isnad_matn("حدثنا فلان عن أنس قال: إنما الأعمال")[2] == "phrase"
    assert split_isnad_matn("حدثنا فلان عن أنس")[2] == "none"

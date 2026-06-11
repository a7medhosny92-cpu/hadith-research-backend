"""Tests for the matn audit — flagging likely matn-extraction errors (the متن «التدقيق»)."""

from __future__ import annotations

from app.parsing.matn_audit import flag_matn


def _codes(matn: str, isnad: str, chapter: str = "") -> set[str]:
    return {code for code, _ in flag_matn(matn, isnad, chapter)}


def test_a_clean_short_matn_is_not_flagged():
    # «إنما الأعمال بالنيات» is a COMPLETE 3-word matn — a plain chain isnad (no quoted span) must
    # NOT trip the empty/fragment flag. (Guards against the obvious false positive.)
    assert _codes(
        "إنما الأعمال بالنيات",
        "حدثنا الحميدي حدثنا سفيان عن يحيى عن محمد عن علقمة عن عمر قال سمعت النبي يقول",
    ) == set()


def test_empty_matn_on_a_real_hadith_is_flagged_V():
    assert "V" in _codes("", "حدثنا فلان عن فلان عن أبي هريرة أن رسول الله قال كذا وكذا وكذا وكذا")


def test_a_back_reference_with_no_matn_is_not_flagged():
    # «نحوه» / «بهذا الإسناد» legitimately carry no matn of their own — not an empty-matn error.
    assert _codes("نحوه", "حدثنا فلان عن فلان بهذا الإسناد نحوه") == set()


def test_isnad_material_in_the_matn_is_flagged_I():
    assert "I" in _codes("حدثنا فلان أن النبي ﷺ قال كذا وكذا", "عن أبي هريرة")
    assert "I" in _codes("عن أبي هريرة قال إنما الأعمال بالنيات", "حدثنا فلان")


def test_a_narration_verb_DEEP_in_a_complete_matn_is_not_flagged_I():
    # a chain verb in the MIDDLE of a complete matn is reported speech, not a head-leak: «… هذا
    # جبريل أخبرني …» (the Prophet quoting), «… ثم قال: حدّثني فلان …». Only a HEAD leak is an error.
    assert "I" not in _codes(
        "يا عثمان هذا جبريل أخبرني أن الله قد زوجك أم كلثوم بمثل صداق رقية", "حدثنا فلان")
    assert "I" not in _codes(
        "يدخل أهل الجنة الجنة وأهل النار النار ثم يقول الله أخرجوا من كان في قلبه إيمان", "حدثنا فلان عن أبي سعيد")


def test_a_backreference_chain_in_the_matn_is_not_flagged_I():
    # «حدّثنا فلان … مثله/نحوه/بهذا الإسناد» is a corroborating chain with no body — not a leak.
    assert "I" not in _codes("حدثنا شريك نحوه", "حدثنا فلان عن فلان")
    assert "I" not in _codes("حدثنا أبو معاوية عن الأعمش بهذا الإسناد مثله", "حدثنا فلان")


def test_akhraja_allah_is_body_not_a_takhrij_G():
    # «أخرجه الله» (God brought out) and «رواه عنه» (his companions narrated) are real body.
    assert "G" not in _codes("من قال لا إله إلا الله أخرجه الله من النار", "حدثنا فلان")
    assert "G" not in _codes("الحديث الذي رواه عنه أصحابه حق", "حدثنا فلان")


def test_a_grade_tail_in_the_matn_is_flagged_G():
    assert "G" in _codes(
        "من كذب علي متعمدا فليتبوأ مقعده من النار هذا حديث صحيح على شرط الشيخين",
        "حدثنا فلان عن فلان",
    )
    assert "G" in _codes("صلوا كما رأيتموني أصلي رواه البخاري", "حدثنا فلان")


def test_a_heading_or_verse_only_matn_is_flagged_Q():
    assert "Q" in _codes("باب ما جاء في النية", "")
    assert "Q" in _codes("﴿قل هو الله أحد﴾", "حدثنا فلان عن النبي ﷺ")
    # a matn that merely QUOTES a verse inside a real body is fine
    assert "Q" not in _codes(
        "كان النبي ﷺ يقرأ في الفجر ﴿قل هو الله أحد﴾ والمعوذتين دائما", "حدثنا فلان")

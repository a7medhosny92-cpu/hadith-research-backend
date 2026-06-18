"""قواعد تمييز المهمل — the curated شيخ-conditioned disambiguations."""

from __future__ import annotations

from app.rijal.qaida import resolve_qaida


def test_sufyan_by_shaykh():
    assert resolve_qaida("سفيان", "الأعمش") == "سفيان بن سعيد الثوري"
    assert resolve_qaida("سفيان", "منصور بن المعتمر") == "سفيان بن سعيد الثوري"
    assert resolve_qaida("سفيان", "عمرو بن دينار") == "سفيان بن عيينة"
    assert resolve_qaida("سفيان", "الزهري") == "سفيان بن عيينة"
    assert resolve_qaida("سُفْيَانُ", "الأَعْمَشِ") == "سفيان بن سعيد الثوري"   # vocalised


def test_hammad_and_hisham():
    assert resolve_qaida("حماد", "أيوب") == "حماد بن زيد"
    assert resolve_qaida("حماد", "ثابت البناني") == "حماد بن سلمة"
    assert resolve_qaida("هشام", "أبيه") == "هشام بن عروة"
    assert resolve_qaida("هشام", "قتادة") == "هشام الدستوائي"
    assert resolve_qaida("هشام", "ابن سيرين") == "هشام بن حسان"


def test_held_when_not_a_discriminator_or_not_bare():
    assert resolve_qaida("سفيان", "شعبة") is None             # شعبة doesn't discriminate
    assert resolve_qaida("سفيان بن عيينة", "الأعمش") is None  # already specified, not a bare homonym
    assert resolve_qaida("مالك", "نافع") is None              # no qā'ida for this name

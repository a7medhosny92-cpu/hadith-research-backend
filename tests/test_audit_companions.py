"""Companions-in-the-chains audit — how many صحابة actually narrate (scripts.audit_companions)."""

from __future__ import annotations

from app.rijal import RijalIndex
from scripts.audit_companions import audit


def test_counts_distinct_terminal_and_coverage_companions():
    """A chain node is a Companion when the base resolves it to «صحابي». They are tallied DISTINCT and by
    chain POSITION (freq); a صحابي whose grade rests only on الإصابة is flagged coverage-only; and the
    subset that narrate directly from the Prophet (``terminal_ids``) is the «الصحابة الرواة» count. A
    non-صحابي man (the Imam مالك) and the Prophet node are excluded."""
    records = [
        {"name": "مالك بن أنس الأصبحي", "grade": "ثقة"},                  # not a Companion
        {"name": "عبد الله بن عمر بن الخطاب", "grade": "صحابي"},          # Companion, in تقريب
        {"name": "أنس بن مالك الأنصاري", "grade": "صحابي"},               # Companion, in تقريب
        {"name": "هانئ بن نيار البلوي", "grade": "صحابي",                 # Companion, only-الإصابة
         "source": "الإصابة في تمييز الصحابة (ابن حجر)"},
    ]
    rijal = RijalIndex(records)
    # (id, name, freq) — ids 2/3/4 narrate from the Prophet (id 9), id 1 (مالك) is mid-chain only
    nodes = [
        (9, "النبي ﷺ", 300),                 # the Prophet node — excluded
        (1, "مالك بن أنس", 100),             # ثقة → not counted
        (2, "عبد الله بن عمر", 120),         # terminal Companion
        (3, "أنس بن مالك", 90),              # terminal Companion
        (4, "هانئ بن نيار", 4),              # terminal Companion, coverage-only
    ]
    res = audit(rijal, nodes, prophet_ids={9}, terminal_ids={2, 3, 4})

    assert res["distinct"] == 3                       # ابن عمر, أنس, هانئ — مالك excluded
    assert res["in_taqrib_kashif"] == 2               # ابن عمر, أنس
    assert res["coverage_only"] == 1                  # هانئ (الإصابة)
    assert res["positions"] == 120 + 90 + 4           # freq-weighted, Companions only
    assert res["total_positions"] == 300 + 100 + 120 + 90 + 4
    assert res["terminal_distinct"] == 3              # all three narrate «عن النبي ﷺ»
    assert res["terminal_positions"] == 120 + 90 + 4
    assert res["top"][0][0].startswith("عبد الله بن عمر")   # most-narrated first


def test_no_companions_when_base_has_none():
    """A chain of only later narrators (no صحابي in the base) tallies zero Companions."""
    rijal = RijalIndex([{"name": "سفيان بن عيينة الهلالي", "grade": "ثقة"}])
    nodes = [(1, "سفيان بن عيينة", 50), (2, "فلان المجهول لا وجود له", 3)]
    res = audit(rijal, nodes, prophet_ids=set(), terminal_ids=set())
    assert res["distinct"] == 0
    assert res["positions"] == 0
    assert res["terminal_distinct"] == 0


def test_coverage_namesake_does_not_exclude_a_real_companion():
    """A famous Companion (أبو هريرة الدوسي, in تقريب) must still count even though an obscure
    coverage namesake (من الثقات) shares his kunya — the coverage shadow is dropped first, mirroring
    the matcher. (Were it kept, the «all homonyms صحابي» gate would wrongly exclude أبو هريرة.)"""
    from scripts.audit_companions import _companion
    rijal = RijalIndex([
        {"name": "عبد الرحمن بن صخر الدوسي", "grade": "صحابي", "kunya": "أبو هريرة"},
        {"name": "محمد بن أيوب الواسطي", "grade": "ثقة", "kunya": "أبو هريرة",
         "source": "الثقات لمن لم يقع في الكتب الستة (رقم 96165)"},
    ])
    entry = _companion(rijal, "أبو هريرة")
    assert entry is not None and entry.category == "صحابي"

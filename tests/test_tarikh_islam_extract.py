"""تاريخ الإسلام (35100) — the comprehensive late-narrator extractor (الأصم-class coverage)."""

from __future__ import annotations

from app.parsing.tarikh_islam_extract import _ti_name, parse_entry
from app.rijal.grades import classify


def test_network_death_and_direct_grade():
    # a real-shape tarjama: «سمع X … وعنه Y … وكان ثقة … توفي سنة …» (al-Dhahabī's direct assessment)
    body = ("ولد سنة مائتين، وسمع عاصم بن يوسف، وطائفة، وعنه ابن عقدة، وأبو العباس الأصم، "
            "وآخرون. وكان ثقة صاحب حديث. توفي سنة تسع وستين ومائتين.")
    r = parse_entry(body, "أحمد بن محمد الكوفي")
    assert r["name"] == "أحمد بن محمد الكوفي"
    assert classify(r["grade"])[0] == "ثقة"            # «كان ثقة» → ثقة
    assert r["death_year"] == 269
    assert any("الأصم" in t for t in r["talamidh"])     # the الأصم-class captured as a تلميذ
    assert any("عاصم" in s for s in r["shuyukh"])


def test_attributed_verdict_form():
    r = parse_entry("سمع سفيان بن عيينة، وعنه ابن صاعد. قال ابن أبي حاتم: وهو صدوق.",
                    "علي بن عبد الله المخرمي")
    assert classify(r["grade"])[0] == "صدوق"


def test_no_default_grade_when_only_network():
    # coverage pattern: شيوخ/تلاميذ but no cited جرح/تعديل → «غير معروف» (no inclusion توثيق)
    r = parse_entry("سمع مالكا، وعنه البخاري.", "محمد بن يوسف الفربري")
    assert r is not None and r["grade"] == "غير معروف"


def test_event_and_section_heads_are_not_narrators():
    # the سيرة/مغازي events are NOT narrators — dropped by _ti_name's event stop-list (the محقق's study
    # sections like «الشهرة والعلمية» are dropped earlier, by the level/page filter in _tarjama_heads).
    assert _ti_name("غزوة بدر الكبرى") is None          # an event
    assert _ti_name("سرية عبد الله بن جحش") is None     # an event
    assert _ti_name("ذكر من استشهد على خيبر") is None   # a section
    assert _ti_name("وفاة سعد بن معاذ") is None         # an event («وفاة …»)
    # a real narrator heading (incl. a «ترجمة فلان» level-2 Companion head) is kept
    assert _ti_name("محمد بن يعقوب الأصم") == "محمد بن يعقوب الأصم"
    assert _ti_name("ترجمة جعفر بن أبي طالب") == "جعفر بن أبي طالب"

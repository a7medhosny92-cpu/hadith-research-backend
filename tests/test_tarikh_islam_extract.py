"""تاريخ الإسلام (35100) — the comprehensive late-narrator extractor (الأصم-class coverage)."""

from __future__ import annotations

from app.parsing.tarikh_islam_extract import parse_entry
from app.rijal.grades import classify


def test_network_death_and_direct_grade():
    # a real-shape tarjama: «سمع X … وعنه Y … وكان ثقة … توفي سنة …» (al-Dhahabī's direct assessment)
    body = ("الحافظ ولد سنة مائتين، وسمع عاصم بن يوسف، وطائفة، وعنه ابن عقدة، وأبو العباس الأصم، "
            "وآخرون. وكان ثقة صاحب حديث. توفي سنة تسع وستين ومائتين.")
    r = parse_entry(274, body, heading_name="أحمد بن محمد الكوفي")
    assert r["name"] == "أحمد بن محمد الكوفي"
    assert classify(r["grade"])[0] == "ثقة"            # «كان ثقة» → ثقة
    assert r["death_year"] == 269
    assert any("الأصم" in t for t in r["talamidh"])     # the الأصم-class captured as a تلميذ
    assert any("عاصم" in s for s in r["shuyukh"])


def test_attributed_verdict_form():
    r = parse_entry(280, "سمع سفيان بن عيينة، وعنه ابن صاعد. قال ابن أبي حاتم: وهو صدوق.",
                    heading_name="علي بن عبد الله المخرمي")
    assert classify(r["grade"])[0] == "صدوق"


def test_muqaddima_and_non_narrators_are_dropped():
    # a محقق-intro topic (a teaching post) — no network, no جرح → not a narrator
    assert parse_entry(1, "مشهد عروة، أو دار الحديث العروية، ودرس فيها بعده شرف الدين", "مشهد عروة") is None
    # a relative head (al-Dhahabī's daughter) — caught by the junk-head pre-filter
    assert parse_entry(6, "وقد أجاز لها غير واحد، سمع مع جده من أحمد", "ابنته أمة العزيز") is None
    # a bare name with no documented network and no verdict is held out (a topic, not a graded narrator)
    assert parse_entry(9, "من أهل بغداد.", "فلان بن فلان البغدادي") is None


def test_no_default_grade_when_only_network():
    # coverage pattern: شيوخ/تلاميذ but no cited جرح/تعديل → «غير معروف» (no inclusion توثيق)
    r = parse_entry(50, "سمع مالكا، وعنه البخاري.", heading_name="محمد بن يوسف الفربري")
    assert r is not None and r["grade"] == "غير معروف"

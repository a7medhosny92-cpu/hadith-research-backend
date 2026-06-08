"""Tests for the rijal (narrator gradings) subsystem and its use in /verify-isnad."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.qa.isnad import analyze_isnad
from app.rijal import RijalIndex, classify, load_seed


@pytest.fixture(scope="module")
def rijal() -> RijalIndex:
    return RijalIndex(load_seed())


# ── grade classification ────────────────────────────────────────────────────
def test_classify_reads_the_leading_verdict():
    assert classify("ثقة حافظ فقيه") == ("ثقة", 9)
    assert classify("ليس بثقة") == ("ضعيف", 2)          # not fooled by the embedded ثقة
    assert classify("لا بأس به") == ("صدوق", 7)
    assert classify("صدوق اختلط بأخرة") == ("صدوق له أوهام", 6)  # qualifier downgrades
    assert classify("متهم بالكذب") == ("كذاب", 0)
    assert classify("صحابي جليل") == ("صحابي", 10)
    assert classify("") == ("غير معروف", None)


# ── name lookup ─────────────────────────────────────────────────────────────
def test_seed_loads():
    assert RijalIndex(load_seed()).count() >= 40


def test_containment_distinguishes_a_man_from_his_longer_namesake(rijal):
    # «عمر بن الخطاب» must not collapse into his son «عبد الله بن عمر بن الخطاب»
    father = rijal.lookup("عمر بن الخطاب على المنبر")
    assert father.entry.name == "عمر بن الخطاب" and not father.ambiguous
    son = rijal.lookup("عبد الله بن عمر")
    assert son.entry.name.startswith("عبد الله بن عمر")


def test_shared_first_name_is_flagged_ambiguous(rijal):
    match = rijal.lookup("سفيان")  # ابن عيينة vs الثوري
    assert match.ambiguous
    assert any("الثوري" in alt for alt in match.alternatives)


def test_unknown_narrator_returns_none(rijal):
    assert rijal.lookup("فلان بن علان المجهول") is None


def test_bare_ism_does_not_match_someone_elses_kunya():
    # «معمر» (an ism) must NOT resolve to a man whose KUNYA is «أبو معمر» — citing the ism
    # is not citing the teknonym; only «أبو معمر» reaches the kunya-holder.
    rij = RijalIndex([
        {"name": "معمر بن راشد", "grade": "ثقة"},
        {"name": "إسماعيل بن إبراهيم", "kunya": "أبو معمر", "grade": "ثقة"},
    ])
    assert rij.lookup("معمر").entry.name == "معمر بن راشد"
    assert rij.lookup("أبو معمر").entry.name == "إسماعيل بن إبراهيم"


def test_ambiguous_match_is_held_not_graded_weak():
    # «زيد بن علي» beside a متروك namesake AND a ثقة one is مشترك: we don't know which, so the
    # uncertain متروك must NOT make the chain «ضعيف جدًا» — it's held (يُتوقَّف) — nor be audit-W-ed.
    from app.qa.isnad import analyze_isnad, overall_ruling
    from scripts.audit_isnad import _flag_chain
    rij = RijalIndex([
        {"name": "مالك بن أنس الأصبحي", "grade": "ثقة"},
        {"name": "أنس بن مالك", "grade": "صحابي"},
        {"name": "زيد بن علي الكوفي", "grade": "متروك"},
        {"name": "زيد بن علي البصري", "grade": "ثقة"},
    ])
    a = analyze_isnad("حدثنا مالك بن أنس، عن زيد بن علي، عن أنس بن مالك", rijal=rij)
    zayd = next(n for n in a.narrators if n["name"].startswith("زيد"))
    assert zayd["rijal"]["ambiguous"]                      # still shown as مشترك on the card
    assert overall_ruling(a.to_dict())["tone"] != "daif"   # uncertain متروك doesn't grade the chain
    codes = [c for c, _ in _flag_chain(a.narrators)]
    assert "A" in codes and "W" not in codes               # belongs to «مشترك», not «متروك»


def test_ambiguous_candidates_that_agree_keep_their_grade():
    # «الليث بن سعد» appears twice (الكاشف + تقريب spellings of the same man), both ثقة. It's
    # مشترك for display, but the agreed grade is usable — the chain must NOT be held «يُتوقَّف».
    from app.qa.isnad import analyze_isnad, overall_ruling
    rij = RijalIndex([
        {"name": "الليث بن سعد المصري", "grade": "ثقة"},
        {"name": "الليث بن سعد الفهمي", "grade": "ثقة"},
        {"name": "نافع مولى ابن عمر", "grade": "ثقة"},
        {"name": "عبد الله بن عمر بن الخطاب", "grade": "صحابي"},
    ])
    a = analyze_isnad("حدثنا الليث بن سعد، عن نافع، عن عبد الله بن عمر", rijal=rij)
    layth = next(n for n in a.narrators if n["name"].startswith("الليث"))
    assert layth["rijal"]["ambiguous"] and layth["rijal"]["grade_agreed"]
    assert overall_ruling(a.to_dict())["tone"] in ("sahih", "hasan")   # agreed ثقة used, not held


def test_kunya_alias_does_not_glue_onto_a_longer_name(rijal):
    # «أبو بكر بن أبي شيبة» (a 3rd-century حافظ) must NOT collapse into أبو بكر الصدّيق the
    # Companion just because «أبو بكر» is his kunya/alias — a teknonym matches reverse-only.
    assert rijal.lookup("أبو بكر بن أبي شيبة") is None
    # the Companion is still found when actually cited by the kunya — and a bare «أبو بكر»,
    # shared by several men, is correctly flagged مشترك rather than silently the صدّيق.
    assert rijal.lookup("أبو بكر").ambiguous


# ── chain assessment via analyze_isnad ──────────────────────────────────────
def test_thiqat_chain_is_graded_sound(rijal):
    a = analyze_isnad("حدثنا مالك، عن نافع، عن عبد الله بن عمر", rijal=rijal)
    assert [n["rijal"]["grade"] for n in a.narrators] == ["ثقة", "ثقة", "صحابي"]
    assert a.rijal_assessment["weakest_rank"] >= 7
    assert a.rijal_assessment["unknown"] == 0
    assert a.rijal_assessment["verdict"].startswith("رجال الإسناد")


def test_weak_link_drives_the_verdict(rijal):
    a = analyze_isnad("حدثنا وكيع، عن جابر بن يزيد الجعفي، عن أنس", rijal=rijal)
    assert a.rijal_assessment["weakest_rank"] == 2
    assert "ضعيف" in a.rijal_assessment["verdict"]


def test_prophet_is_not_graded_as_a_narrator(rijal):
    # «… عن النبي ﷺ قال» — the Prophet is the source, never looked up in the rijal
    a = analyze_isnad("حدثنا مالك، عن نافع، عن عبد الله بن عمر، عن النبي ﷺ قال", rijal=rijal)
    prophet = a.narrators[-1]
    assert prophet["is_prophet"] is True and prophet["rijal"] is None
    assert a.reaches_prophet
    # only the three gradable narrators are counted (the Prophet is excluded)
    assert a.rijal_assessment["known"] == 3 and a.rijal_assessment["unknown"] == 0


def test_mubham_unnamed_narrator_is_a_real_jahala(rijal):
    from app.qa.isnad import overall_ruling

    # «عن رجلٍ» — unnamed: a genuine جهالة (a defect in the text), not «unknown in our DB».
    a = analyze_isnad("حدثنا مالك، عن رجل، عن عبد الله بن عمر", rijal=rijal)
    rajul = next(n for n in a.narrators if n["name"] == "رجل")
    assert rajul["mubham"] is True and rajul["rijal"] is None
    assert a.rijal_assessment["mubham"] == 1
    # it weakens the chain even though مالك/ابن عمر are sound — and it's not a paused «يُتوقَّف»
    r = overall_ruling(a.to_dict())
    assert r["tone"] == "daif" and "مبهم" in r["reason"]


def test_unnamed_companion_is_not_flagged_mubham(rijal):
    # «رجلٌ من أصحاب النبي ﷺ» is an unnamed Companion — عدول, not a جهالة
    from app.qa.isnad import _is_mubham
    assert not _is_mubham("رجل من أصحاب النبي")
    assert _is_mubham("رجل") and _is_mubham("شيخ له") and _is_mubham("بعض أصحابه")


def test_analyze_without_rijal_is_unchanged():
    a = analyze_isnad("حدثنا مالك، عن نافع")
    assert a.rijal_assessment is None
    assert "rijal" not in a.narrators[0]


# ── API ─────────────────────────────────────────────────────────────────────
def test_api_verify_isnad_includes_gradings():
    client = TestClient(app)
    body = client.get(
        "/verify-isnad", params={"isnad": "حدثنا مالك، عن نافع، عن عبد الله بن عمر"}
    ).json()
    analysis = body["analysis"]
    assert analysis["rijal_assessment"]["known"] == 3
    assert analysis["narrators"][0]["rijal"]["grade"] == "ثقة"
    assert analysis["narrators"][0]["rijal"]["source"]  # attributed

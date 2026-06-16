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


def test_companion_ancestor_buried_in_a_nasab_is_not_the_narrator():
    # «إبراهيم بن سعد … بن عبد الرحمن بن عوف» is the great-grandson who actually narrates; the
    # Companion «عبد الرحمن بن عوف» is only an ancestor in his lineage, not the man citing the
    # hadith. The contained name must be the LEADING run (the cited man), not buried in the nasab.
    rij = RijalIndex([
        {"name": "إبراهيم بن سعد بن إبراهيم بن عبد الرحمن بن عوف الزهري", "grade": "ثقة"},
        {"name": "عبد الرحمن بن عوف", "grade": "صحابي"},
    ])
    m = rij.lookup("إبراهيم بن سعد بن إبراهيم بن عبد الرحمن بن عوف")
    assert m.entry.name.startswith("إبراهيم بن سعد") and m.entry.category != "صحابي"


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


def test_ibn_abi_X_is_the_descendant_not_the_kunya_grandfather():
    # «ابن أبي مليكة» is the تابعي عبد الله بن عبيد الله بن أبي مليكة, NEVER his grandfather أبو مليكة
    # (a صحابي). The «ابن» makes it a descendant reference, so the teknonym (reverse-kunya) match is
    # suppressed — else the bare «ابن أبي مليكة» folds to the kunya «أبو مليكة» and grabs the wrong
    # (صحابي) ancestor (a big source of false «صحابي mid-chain» flags).
    rij = RijalIndex([
        {"name": "زهير بن عبد الله", "kunya": "أبو مليكة", "grade": "صحابي"},
        {"name": "عبد الله بن عبيد الله بن أبي مليكة", "grade": "ثقة"},
    ])
    assert rij.lookup("ابن أبي مليكة").entry.name == "عبد الله بن عبيد الله بن أبي مليكة"
    # citing the grandfather BY his kunya (no «ابن») still reaches him — the teknonym is intact
    assert rij.lookup("أبو مليكة").entry.name == "زهير بن عبد الله"


def test_ibn_X_patronymic_does_not_match_the_eponym_named_X():
    # «ابن عمر» is the son عبد الله بن عمر, NEVER عمر himself nor any man whose ISM is عمر — «ابن»
    # makes عمر a FATHER, so he must sit non-leading. (Real bug: «ابن عمر» matched 134 عمر-named men,
    # held مشترك with the eponym عمر بن الخطاب; same for «ابن عباس».)
    rij = RijalIndex([
        {"name": "عمر بن الخطاب العدوي", "grade": "صحابي"},        # the eponym — he is عمر, not ابن عمر
        {"name": "عمر بن إبراهيم العبدي", "grade": "ثقة"},          # another man whose ism is عمر
        {"name": "عبد الله بن عمر بن الخطاب", "grade": "صحابي"},    # the son — IS «ابن عمر»
        {"name": "عبيد الله بن عمر العمري", "grade": "ثقة"},        # another son of عمر
    ])
    cands = [e.name for e in rij.candidates("ابن عمر", max_results=None)]
    assert any("عبد الله بن عمر" in n for n in cands)              # a son IS a candidate
    assert all(not n.startswith("عمر ") for n in cands)           # …no عمر-led eponym
    m = rij.lookup("ابن عمر")
    assert m is None or not m.entry.name.startswith("عمر ")        # lookup never picks the father
    # a bare ism citation «عمر بن الخطاب» (no «ابن») is unaffected — still reaches an عمر-led man
    assert rij.lookup("عمر بن الخطاب") is not None


def test_a_bare_grave_namesake_does_not_sink_a_fuller_trustworthy_one():
    # «إسحاق بن عمر» [متروك] (a bare, truncated entry) must NOT confidently grade a chain «ضعيف جدًا»
    # when a fuller, trustworthy «إسحاق بن عمر بن سليط الهذلي» also fits the bare citation — hold instead.
    rij = RijalIndex([
        {"name": "إسحاق بن عمر", "grade": "متروك"},
        {"name": "إسحاق بن عمر بن سليط الهذلي", "grade": "ثقة"},
    ])
    m = rij.lookup("إسحاق بن عمر")
    assert m.ambiguous and not m.grade_agreed          # held, never a confident متروك verdict
    # …but a LONE grave with no trustworthy namesake still resolves (he is genuinely weak)
    rij2 = RijalIndex([{"name": "أصبغ بن نباتة التميمي", "grade": "متروك"}])
    assert rij2.lookup("أصبغ بن نباتة").entry.category == "متروك"


def test_a_flipped_name_alias_does_not_stamp_its_grade_on_a_namesake():
    # محمد بن سعيد المصلوب «قلبوا اسمه على وجوه» → a flipped form «سعد بن سعيد» was extracted as one of
    # his aliases; as an exact 2-token containment it must NOT out-rank the innocent سعد بن سعيد
    # الأنصاري (a Muslim narrator) and stamp the forger's كذاب on a sound chain (→ «ضعيف جدًا»).
    rij = RijalIndex([
        {"name": "محمد بن سعيد بن حسان الأسدي المصلوب", "aliases": ["سعد بن سعيد"], "grade": "كذاب"},
        {"name": "سعد بن سعيد بن قيس الأنصاري", "grade": "صدوق"},
        {"name": "سعد بن سعيد المقبري", "grade": "لين الحديث"},
    ])
    m = rij.lookup("سعد بن سعيد")
    assert m is not None and m.entry.category != "كذاب"        # the forger no longer wins this name
    assert rij.lookup("محمد بن سعيد المصلوب").entry.category == "كذاب"   # …but is reachable by his own
    # a KUNYA alias is exempt — still reverse-matchable
    rij2 = RijalIndex([{"name": "محمد بن خازم الضرير", "aliases": ["أبو معاوية"], "grade": "ثقة"}])
    assert rij2.lookup("أبو معاوية").entry.name == "محمد بن خازم الضرير"


def test_a_complete_name_is_not_ambiguous_with_a_descendant_burying_it():
    # «محمد بن عبد الله بن جحش» (a صحابي) must NOT read «مشترك» with his descendant «إبراهيم بن محمد
    # بن عبد الله بن جحش» — the descendant merely carries the ancestor's nasab. When the query is
    # itself a complete man (a containment match), candidates() drops the non-prefix partials.
    rij = RijalIndex([
        {"name": "محمد بن عبد الله بن جحش الأسدي", "grade": "صحابي"},
        {"name": "إبراهيم بن محمد بن عبد الله بن جحش الأسدي", "grade": "صدوق"},
    ])
    cands = rij.candidates("محمد بن عبد الله بن جحش الأسدي", max_results=None)
    assert [c.name for c in cands] == ["محمد بن عبد الله بن جحش الأسدي"]   # only the man himself
    assert not rij.lookup("محمد بن عبد الله بن جحش الأسدي").ambiguous
    # but a bare nisba (no containment) still surfaces every bearer — genuine homonymy stays «مشترك»
    rij2 = RijalIndex([
        {"name": "محمد بن مسلم الزهري", "grade": "ثقة"},
        {"name": "مصعب بن سليم الزهري", "grade": "صدوق"},
    ])
    assert len(rij2.candidates("الزهري", max_results=None)) == 2


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


def test_divergent_name_does_not_wear_a_short_namesakes_sahabi_grade():
    # «الحسن بن علي بن زياد» (a late شيخ absent from the rijal) collapses onto the bare leading run
    # «الحسن بن علي» of the Companion الحسن بن علي بن أبي طالب → graded «صحابي». It carries «زياد»,
    # absent from the Companion's name, so it is a DIFFERENT man: the S flag must be suppressed.
    from scripts.audit_isnad import _flag_chain, _name_compatible
    assert not _name_compatible("الحسن بن علي بن زياد", "الحسن بن علي بن أبي طالب الهاشمي وقد صحبه")
    assert _name_compatible("عبد الله بن عمر بن الخطاب", "عبد الله بن عمر بن الخطاب العدوي")  # deeper ancestor — ok
    narrators = [
        {"name": "محمد بن يحيى", "rijal": {"name": "محمد بن يحيى الذهلي", "grade": "ثقة"}},
        {"name": "الحسن بن علي بن زياد",
         "rijal": {"name": "الحسن بن علي بن أبي طالب", "grade": "صحابي"}},   # mid-chain, divergent
        {"name": "سفيان", "rijal": {"name": "سفيان الثوري", "grade": "ثقة"}},
        {"name": "أنس بن مالك", "rijal": {"name": "أنس بن مالك", "grade": "صحابي"}},
    ]
    assert "S" not in [c for c, _ in _flag_chain(narrators)]


def test_compatible_sahabi_mid_chain_is_still_flagged_S():
    # the guard must not silence a GENUINE mid-chain Companion: «أنس بن مالك» (cited) is consistent
    # with the matched «أنس بن مالك الأنصاري», so the «صحابي في غير آخر السند» review flag stands.
    from scripts.audit_isnad import _flag_chain
    narrators = [
        {"name": "حماد", "rijal": {"name": "حماد بن سلمة", "grade": "ثقة"}},
        {"name": "أنس بن مالك", "rijal": {"name": "أنس بن مالك الأنصاري", "grade": "صحابي"}},
        {"name": "علقمة", "rijal": {"name": "علقمة بن وقاص", "grade": "ثقة"}},
        {"name": "عمر", "rijal": {"name": "عمر بن الخطاب", "grade": "صحابي"}},
    ]
    assert "S" in [c for c, _ in _flag_chain(narrators)]


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


def test_kinship_particle_refused():
    """A bare kinship possessive («أبيه»/«جده») identifies no one and must NOT match an entry that
    merely mentions it («جعفر بن أبي ثور واسم أبيه عكرمة»)."""
    from app.rijal.index import RijalIndex
    r = RijalIndex([{"name": "جعفر بن أبي ثور واسم أبيه عكرمة", "grade": "مقبول"}])
    assert r.lookup("أبيه") is None
    assert r.lookup("جده") is None


def test_a_companion_narrating_from_a_companion_is_not_flagged_S():
    # «ابن عباس عن عمر» — a younger Companion narrating from an older one is legitimate at any depth,
    # not a misplaced صحابي. The S flag is suppressed when the next link (the شيخ) is also a صحابي…
    from scripts.audit_isnad import _flag_chain
    sahabi_chain = [
        {"name": "قتادة", "rijal": {"name": "قتادة بن دعامة", "grade": "ثقة"}},
        {"name": "ابن عباس", "rijal": {"name": "عبد الله بن عباس", "grade": "صحابي"}},
        {"name": "عمر", "rijal": {"name": "عمر بن الخطاب", "grade": "صحابي"}},
        {"name": "النبي", "is_prophet": True},
    ]
    assert "S" not in [c for c, _ in _flag_chain(sahabi_chain)]
    # …but a Companion whose شيخ is NOT a Companion (a تابعي) deep in the chain is STILL suspect.
    odd_chain = [
        {"name": "حماد", "rijal": {"name": "حماد بن سلمة", "grade": "ثقة"}},
        {"name": "أنس", "rijal": {"name": "أنس بن مالك", "grade": "صحابي"}},
        {"name": "علقمة", "rijal": {"name": "علقمة بن وقاص", "grade": "ثقة"}},
        {"name": "عمر", "rijal": {"name": "عمر بن الخطاب", "grade": "صحابي"}},
    ]
    assert "S" in [c for c, _ in _flag_chain(odd_chain)]


def test_X_ibn_X_is_not_collapsed_to_the_bare_ism():
    # «معاذ بن معاذ» (ism = the father's name) is a real two-token name (معاذ بن معاذ العنبري القاضي,
    # a famous ثقة), NOT the bare «معاذ» — _clean_seq must keep the adjacent repeat, else it matches
    # every معاذ بن فلان and the famous narrator reads «مشترك» among twenty men.
    from app.rijal.index import _clean_seq
    assert _clean_seq("معاذ بن معاذ") == ["معاذ", "معاذ"]
    assert _clean_seq("محمد بن علي بن محمد") == ["محمد", "علي"]   # non-adjacent repeat still dropped
    rij = RijalIndex([
        {"name": "معاذ بن معاذ العنبري", "grade": "ثقة"},
        {"name": "معاذ بن خالد العسقلاني", "grade": "صدوق"},
        {"name": "معاذ بن هشام الدستوائي", "grade": "صدوق"},
    ])
    m = rij.lookup("معاذ بن معاذ")
    assert m.entry.name == "معاذ بن معاذ العنبري" and not m.ambiguous   # the one real «معاذ بن معاذ»
    assert len(rij.candidates("معاذ بن معاذ", max_results=None)) == 1   # not every معاذ بن فلان


def test_companion_by_description_is_recovered_from_an_empty_grade():
    # عبد الرحمن بن عوف (one of العشرة المبشرة) had his Companion status «أحد العشرة أسلم قديمًا …»
    # leaked into the NAME while the grade field was empty → he was mis-graded «غير معروف» (مجهول), so
    # a chain through a major صحابي read «راوٍ مجهول». classify now reads the description, and add()
    # recovers a POSITIVE grade from the name when the grade is silent.
    from app.rijal.grades import classify
    assert classify("أحد العشرة أسلم قديمًا ومناقبه شهيرة") == ("صحابي", 10)
    assert classify("مذكور في الصحابة")[0] == "صحابي"
    assert classify("متهم")[0] == "متروك" and classify("ليس بالقوي")[0] == "لين"
    rij = RijalIndex([{"name": "عبد الرحمن بن عوف الزهري أحد العشرة أسلم قديمًا", "grade": "غير محدد"}])
    assert rij._entries[0].category == "صحابي"
    # a NEGATIVE word in a NAME must NOT be recovered — only a positive one (never sink a sound chain)
    rij2 = RijalIndex([{"name": "فلان بن فلان صاحب الضعيف", "grade": ""}])
    assert rij2._entries[0].category == "غير معروف"


def test_high_status_unknown_is_recovered_by_the_curated_anchor():
    # A famous Companion / major تابعي whose grade was never extracted must not read «مجهول» — the
    # curated, closed anchor (companions.py) grades him; a GRADED namesake must NOT be anchored.
    rij = RijalIndex([
        {"name": "أبي بن كعب بن قيس الأنصاري", "grade": "غير محدد"},     # Companion, empty grade
        {"name": "سعيد بن المسيب بن حزن المخزومي", "grade": ""},          # major تابعي ثقة, empty grade
        {"name": "عمر بن الخطاب السجستاني", "grade": "صدوق"},             # graded namesake → NOT anchored
    ])
    by = {e.name: e.category for e in rij._entries}
    assert by["أبي بن كعب بن قيس الأنصاري"] == "صحابي"
    assert by["سعيد بن المسيب بن حزن المخزومي"] == "ثقة"
    assert by["عمر بن الخطاب السجستاني"] == "صدوق"      # safety: an existing grade is never overridden


def test_coverage_only_namesake_does_not_shadow_a_real_narrator():
    """A bare/kunya citation resolves to the REAL narrator, not held «مشترك» because an obscure
    الإصابة/الثقات namesake shares the name. «أبي هريرة» = the Companion الدوسي, not a محمد who merely
    carries the kunya; «سفيان» stays the honest عيينة/الثوري tie (coverage dropped); a coverage man is
    kept only when he is the SOLE option."""
    from app.rijal.index import RijalIndex
    T = "تقريب التهذيب (رقم 8609)"
    TH = "الثقات ممن لم يقع في الكتب الستة (رقم 96165)"
    idx = RijalIndex([
        {"name": "عبد الرحمن بن صخر الدوسي", "kunya": "أبو هريرة", "grade": "صحابي", "source": T},
        {"name": "محمد بن أيوب الواسطي", "kunya": "أبو هريرة", "grade": "ثقة", "source": TH},
        {"name": "سفيان بن عيينة", "grade": "ثقة", "source": T},
        {"name": "سفيان بن سعيد الثوري", "grade": "ثقة", "source": T},
        {"name": "سفيان بن أسد", "grade": "ثقة", "source": TH},
        {"name": "معاوية بن صالح الجهني", "grade": "ثقة", "source": TH},
    ])
    abu = idx.lookup("أبي هريرة")
    assert abu.entry.name == "عبد الرحمن بن صخر الدوسي" and not abu.ambiguous
    suf = idx.lookup("سفيان")
    assert suf.ambiguous and set(suf.alternatives + [suf.entry.name]) == {"سفيان بن عيينة", "سفيان بن سعيد الثوري"}
    sole = idx.lookup("معاوية بن صالح الجهني")
    assert sole.entry.name == "معاوية بن صالح الجهني" and not sole.ambiguous


def test_candidates_also_drops_coverage_namesakes():
    """candidates() (read by the terminal-صحابي promotion in analyze_isnad) drops a coverage namesake too,
    so a terminal «أبي هريرة» resolves to the Companion, not held among obscure same-kunya men."""
    from app.rijal.index import RijalIndex
    idx = RijalIndex([
        {"name": "عبد الرحمن بن صخر الدوسي", "kunya": "أبو هريرة", "grade": "صحابي",
         "source": "تقريب التهذيب (رقم 8609)"},
        {"name": "أبو هريرة الواسطي", "kunya": "أبو هريرة", "grade": "صحابي",
         "source": "الإصابة في تمييز الصحابة (رقم 9767)"},
    ])
    assert [c.name for c in idx.candidates("أبي هريرة")] == ["عبد الرحمن بن صخر الدوسي"]


def test_ibn_X_resolves_to_the_son_not_the_eponym_father():
    """«ابن عمر» is the son عبد الله بن عمر, never the eponym father عمر بن الخطاب (whose bare «عمر» form
    would otherwise lead-match the containment branch) nor any man merely NAMED عمر."""
    from app.rijal.index import RijalIndex
    idx = RijalIndex([
        {"name": "عمر بن الخطاب", "aliases": ["عمر", "الفاروق"], "grade": "صحابي", "source": "seed"},
        {"name": "عبد الله بن عمر بن الخطاب", "grade": "صحابي", "source": "seed"},
    ])
    m = idx.lookup("ابن عمر")
    assert m.entry.name == "عبد الله بن عمر بن الخطاب" and not m.ambiguous
    assert idx.lookup("عمر بن الخطاب").entry.name == "عمر بن الخطاب"


def test_prominence_prior_prefers_the_prolific_narrator():
    """The corpus-frequency prior breaks a tie toward the much-narrated man: «ابن عمر» → عبد الله بن عمر
    (the prolific son), not an obscure same-father namesake; «سفيان» stays the honest عيينة/الثوري tie."""
    from app.rijal.index import RijalIndex
    entries = [
        {"name": "عبد الله بن عمر بن الخطاب", "grade": "صحابي", "source": "seed"},
        {"name": "عبيد الله بن عمر", "grade": "ثقة", "source": "تقريب التهذيب (رقم 8609)"},
        {"name": "سفيان بن عيينة", "grade": "ثقة", "source": "تقريب التهذيب (رقم 8609)"},
        {"name": "سفيان بن سعيد الثوري", "grade": "ثقة", "source": "تقريب التهذيب (رقم 8609)"},
    ]
    idx = RijalIndex(entries)
    assert idx.lookup("ابن عمر").ambiguous                       # no prominence → held among the sons
    idx.set_prominence({"عبد الله بن عمر بن الخطاب": 5000, "عبيد الله بن عمر": 200,
                        "سفيان بن عيينة": 3000, "سفيان بن سعيد الثوري": 2500})
    ibn_umar = idx.lookup("ابن عمر")
    assert ibn_umar.entry.name == "عبد الله بن عمر بن الخطاب" and not ibn_umar.ambiguous
    assert idx.lookup("سفيان").ambiguous                         # both prolific → honest tie kept


def test_candidates_cache_is_invalidated_by_set_prominence():
    """candidates() is memoised (the joint resolver calls it per link over tens of thousands of chains);
    the cache must refresh when prominence changes, or a stale homonym set survives."""
    from app.rijal.index import RijalIndex
    idx = RijalIndex([
        {"name": "سفيان بن سعيد الثوري", "grade": "ثقة", "source": "تقريب التهذيب (رقم 8609)"},
        {"name": "سفيان بن عيينة", "grade": "ثقة", "source": "تقريب التهذيب (رقم 8609)"},
    ])
    assert len(idx.candidates("سفيان")) == 2                     # warm the cache
    idx.set_prominence({"سفيان بن سعيد الثوري": 5000, "سفيان بن عيينة": 100})
    assert [c.name for c in idx.candidates("سفيان")] == ["سفيان بن سعيد الثوري"]   # not the stale 2


def test_grave_never_shadows_a_trustworthy_namesake_via_filters():
    """DANGEROUS class: a bare «محمد بن الزبير» must NOT confidently resolve to the prolific متروك
    (الحنظلي) when a ثقة namesake (مولى المعيطيين, from الثقات/coverage) was equally cited — the
    coverage drop AND the prominence prior must not be the reason a sound chain is sunk → HELD."""
    from app.rijal.index import RijalIndex
    from scripts.audit_conflicts import sweep
    idx = RijalIndex([
        {"name": "محمد بن الزبير الحنظلي البصري", "grade": "متروك",
         "source": "تقريب التهذيب (رقم 8609)"},
        {"name": "محمد بن الزبير مولى المعيطيين أبو بشر", "grade": "ثقة",
         "source": "الثقات لمن لم يقع في الكتب الستة (رقم 96165)"},
    ])
    idx.set_prominence({"محمد بن الزبير الحنظلي البصري": 500,
                        "محمد بن الزبير مولى المعيطيين أبو بشر": 5})
    m = idx.lookup("محمد بن الزبير")
    assert m.ambiguous and not m.grade_agreed          # held, NOT graded متروك
    assert sweep(idx)["dangerous"] == []               # the conflict sweep agrees: not dangerous


def test_candidates_display_shows_all_homonyms_not_the_prolific_few():
    """The «راوٍ» picker (narrator_dossier) must list ALL homonyms — «عبد الله» is many men for the
    user to choose from, not the two ابادلة the chain-time prominence prior keeps. So the display path
    calls candidates(apply_prominence=False)."""
    from app.rijal.index import RijalIndex
    idx = RijalIndex([
        {"name": "عبد الله بن عباس", "grade": "صحابي", "source": "seed"},
        {"name": "عبد الله بن المبارك", "grade": "ثقة", "source": "تقريب التهذيب (رقم 8609)"},
    ])
    idx.set_prominence({"عبد الله بن عباس": 5000, "عبد الله بن المبارك": 50})
    assert len(idx.candidates("عبد الله", apply_prominence=True)) == 1     # chain-time: collapses
    assert len(idx.candidates("عبد الله", apply_prominence=False)) == 2    # display: all of them


def test_single_token_laqab_captured_only_from_a_strong_cue():
    """A famous one-word laqab «غندر/بندار» from a STRONG cue («المعروف/الملقب بـ») is captured as an
    alias (the lever for غندر = محمد بن جعفر صاحب شعبة, mis-attributed for want of this unification). But
    a WEAK alternate-name cue («ويقال/يقال له») must NOT yield a one-word alias — «ويقال نافع» for the
    متروك نفيع بن الحارث would shadow the famous نافع مولى ابن عمر."""
    from app.parsing.rijal_extract import _aliases
    assert "غندر" in _aliases("محمد بن جعفر الهذلي البصري المعروف بغندر سمع شعبة")
    assert "بندار" in _aliases("محمد بن بشار الملقب ببندار حافظ")
    assert "الأعمش" in _aliases("سليمان بن مهران المشهور بالأعمش")          # an ال-nisba still works
    assert _aliases("نفيع بن الحارث أبو داود الأعمى ويقال نافع") == []      # weak cue → no «نافع» alias
    assert _aliases("محمد بن جعفر البزاز أبو جعفر المدائني") == []          # no cue → no spurious alias

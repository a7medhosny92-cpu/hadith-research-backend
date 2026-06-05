"""Tests for the offline Arabic knowledge engine (data + phonology + tajwīd)."""

from __future__ import annotations

import unicodedata

import pytest

from app.arabic import data, phonology, tajweed, morphology, iraab


def _n(s: str) -> str:
    return unicodedata.normalize("NFC", s)


# --- knowledge base loads ---------------------------------------------------

def test_knowledge_files_load():
    assert len(data.letters()["letters"]) == 29   # 28 letters + hamza
    assert len(data.awzan()["forms"]) == 10
    assert len(data.levels()["levels"]) == 6
    assert data.tajweed()["nun_sakina_tanwin"]["rules"]["iqlab"]["letters"] == ["ب"]


# --- phonology --------------------------------------------------------------

def test_letter_profile_dad():
    d = phonology.get("ض")
    assert d.translit == "ḍād"
    assert d.region == "lisan"
    assert d.heavy is True
    # ḍād is the classic heavy emphatic: jahr, rakhāwa, istiʿlāʾ, iṭbāq, istiṭāla
    for attr in ["جهر", "رخاوة", "استعلاء", "إطباق", "استطالة"]:
        assert attr in d.sifat


def test_letter_profile_taa_is_light_whispered_stop():
    t = phonology.get("ت")
    assert t.heavy is False
    assert "همس" in t.sifat       # whispered
    assert "شدة" in t.sifat       # plosive/stop


def test_each_letter_has_one_of_each_contrasting_pair():
    pairs = [("همس", "جهر"), ("استعلاء", "استفال"), ("إطباق", "انفتاح"),
             ("إذلاق", "إصمات")]
    for info in data.letters()["letters"]:
        s = set(phonology.get(info["letter"]).sifat)
        for a, b in pairs:
            assert (a in s) ^ (b in s), (info["letter"], a, b)


def test_sun_and_moon_letters():
    assert phonology.is_sun("ش") is True     # sun letter
    assert phonology.is_sun("ق") is False    # moon letter


# --- tajwīd analyzer --------------------------------------------------------

@pytest.mark.parametrize("text,expected_key", [
    ("مِنْ رَبِّهِمْ", "idgham_no_ghunna"),     # nūn + ر
    ("مِنْ بَعْدِ", "iqlab"),                    # nūn + ب
    ("مَنْ يَقُولُ", "idgham_ghunna"),          # nūn + ي
    ("مِنْ هَادٍ", "izhar"),                     # nūn + ه (throat)
    ("مِنْ شَيْءٍ", "ikhfa"),                    # nūn + ش
    ("عَلِيمٌ حَكِيمٌ", "izhar"),                # tanwīn + ح
    ("غَفُورًا رَحِيمًا", "idgham_no_ghunna"),  # tanwīn (skip silent alif) + ر
])
def test_nun_sakina_and_tanwin(text, expected_key):
    keys = [f.key for f in tajweed.analyze(text)]
    assert expected_key in keys


def test_mim_sakina_rules():
    assert "ikhfa_shafawi" in [f.key for f in tajweed.analyze("لَهُمْ بِهِ")]   # م + ب
    assert "idgham_shafawi" in [f.key for f in tajweed.analyze("هُمْ مِنْ")]    # م + م


def test_qalqala_sughra_and_kubra():
    assert "qalqala_sughra" in [f.key for f in tajweed.analyze("يَدْخُلُونَ")]  # دْ mid-word
    assert "qalqala_kubra" in [f.key for f in tajweed.analyze("أَحَدْ")]        # د at a stop


def test_madd_muttasil_detected():
    assert "madd_muttasil" in [f.key for f in tajweed.analyze("جَاءَ")]         # ا + hamza


def test_lam_shamsiyya_and_qamariyya():
    assert "lam_shamsiyya" in [f.key for f in tajweed.analyze("الرَّحْمٰنِ")]   # ال + ر (sun)
    assert "lam_qamariyya" in [f.key for f in tajweed.analyze("الْقَمَرِ")]     # ال + ق (moon)


def test_dagger_alif_is_not_a_base_letter():
    # الرحمٰن: the م carries a superscript alef (madd mark), so it is NOT mīm sākina
    keys = [f.key for f in tajweed.analyze("الرَّحْمٰنِ")]
    assert "izhar_shafawi" not in keys


def test_findings_have_spans_into_text():
    text = "مِنْ بَعْدِ"
    for f in tajweed.analyze(text):
        s, e = f.span
        assert 0 <= s < e <= len(text)


# --- morphology (ṣarf) ------------------------------------------------------

@pytest.mark.parametrize("root,form,madi,mudari,amr", [
    ("كتب", 1, "كَتَبَ", "يَكْتُبُ", "اُكْتُبْ"),
    ("علم", 2, "عَلَّمَ", "يُعَلِّمُ", "عَلِّمْ"),
    ("قتل", 3, "قَاتَلَ", "يُقَاتِلُ", "قَاتِلْ"),
    ("خرج", 4, "أَخْرَجَ", "يُخْرِجُ", "أَخْرِجْ"),
    ("علم", 5, "تَعَلَّمَ", "يَتَعَلَّمُ", "تَعَلَّمْ"),
    ("كتب", 6, "تَكَاتَبَ", "يَتَكَاتَبُ", "تَكَاتَبْ"),
    ("كسر", 7, "اِنْكَسَرَ", "يَنْكَسِرُ", "اِنْكَسِرْ"),
    ("جمع", 8, "اِجْتَمَعَ", "يَجْتَمِعُ", "اِجْتَمِعْ"),
    ("غفر", 10, "اِسْتَغْفَرَ", "يَسْتَغْفِرُ", "اِسْتَغْفِرْ"),
])
def test_conjugation_anchors(root, form, madi, mudari, amr):
    c = morphology.conjugate(list(root), form)
    assert c.madi["3ms"] == _n(madi)
    assert c.mudari["3ms"] == _n(mudari)
    assert c.amr["2ms"] == _n(amr)


@pytest.mark.parametrize("root,expected", [
    ("صبر", "اِصْطَبَرَ"),   # ص → infix ط
    ("زهر", "اِزْدَهَرَ"),   # ز → infix د
    ("طلع", "اِطَّلَعَ"),    # ط → idghām
])
def test_form8_assimilation(root, expected):
    assert morphology.conjugate(list(root), 8).madi["3ms"] == _n(expected)


def test_madi_paradigm_spot_checks():
    c = morphology.conjugate(list("كتب"), 1)        # mud_v2 = ḍamma
    assert c.madi["3mp"] == _n("كَتَبُوا")          # silent alif after wāw
    assert c.madi["1s"] == _n("كَتَبْتُ")
    assert c.mudari["2fs"] == _n("تَكْتُبِينَ")
    assert c.mudari["3fp"] == _n("يَكْتُبْنَ")


def test_mushtaqqat():
    assert morphology.conjugate(list("كتب"), 1).mushtaqqat == {
        "اسم الفاعل": _n("كَاتِب"), "اسم المفعول": _n("مَكْتُوب"), "المصدر": "سماعي"}
    m2 = morphology.conjugate(list("علم"), 2).mushtaqqat
    assert m2["اسم الفاعل"] == _n("مُعَلِّم")
    assert m2["اسم المفعول"] == _n("مُعَلَّم")
    assert m2["المصدر"] == _n("تَعْلِيم")
    assert morphology.conjugate(list("غفر"), 10).mushtaqqat["المصدر"] == _n("اِسْتِغْفَار")


def test_unsupported_weak_verb_is_rejected():
    assert morphology.is_sound(list("قول")) is False   # ق-و-ل has a weak و
    with pytest.raises(morphology.UnsupportedVerb):
        morphology.conjugate(list("قول"), 1)


def test_identify_candidates():
    assert {"form": 10, "root": ["غ", "ف", "ر"]} in morphology.identify("استغفر")["candidates"]
    assert {"form": 8, "root": ["ز", "ه", "ر"]} in morphology.identify("ازدهر")["candidates"]
    # a bare 3-letter skeleton is ambiguous between Forms I and II
    forms = {c["form"] for c in morphology.identify("كتب")["candidates"]}
    assert {1, 2} <= forms


# --- iʿrāb (naḥw) -----------------------------------------------------------

def _funcs(sentence):
    return [(w.bare, w.function, w.read_case, w.expected_case) for w in
            iraab.analyze(sentence).words]


def test_read_case_from_diacritics():
    assert iraab.read_case("الْوَلَدُ")[0] == iraab.RAF
    assert iraab.read_case("الْكِتَابَ")[0] == iraab.NASB
    assert iraab.read_case("الْبَيْتِ")[0] == iraab.JARR
    assert iraab.read_case("مُجْتَهِدًا")[0] == iraab.NASB   # skip silent tanwīn-alif


def test_verbal_sentence_fail_and_mafool():
    a = iraab.analyze("قَرَأَ الْوَلَدُ الْكِتَابَ")
    assert a.kind == "جملة فعلية"
    assert (a.words[1].function, a.words[1].read_case) == ("فاعل", iraab.RAF)
    assert (a.words[2].function, a.words[2].read_case) == ("مفعول به", iraab.NASB)
    assert a.words[1].ok and a.words[2].ok


def test_nominal_sentence_mubtada_khabar():
    a = iraab.analyze("الْوَلَدُ مُجْتَهِدٌ")
    assert a.kind == "جملة اسمية"
    assert [w.function for w in a.words] == ["مبتدأ", "خبر"]
    assert all(w.read_case == iraab.RAF and w.ok for w in a.words)


def test_inna_and_sisters():
    a = iraab.analyze("إِنَّ اللَّهَ غَفُورٌ")
    assert a.words[1].function == "اسم إنّ" and a.words[1].expected_case == iraab.NASB
    assert a.words[2].function == "خبر إنّ" and a.words[2].expected_case == iraab.RAF
    assert a.words[1].ok and a.words[2].ok


def test_kana_and_sisters():
    a = iraab.analyze("كَانَ الطَّالِبُ مُجْتَهِدًا")
    assert a.words[1].function == "اسم كان" and a.words[1].read_case == iraab.RAF
    assert a.words[2].function == "خبر كان" and a.words[2].read_case == iraab.NASB
    assert a.words[1].ok and a.words[2].ok


def test_jarr_and_idafa():
    assert ("البيت", "اسم مجرور", iraab.JARR, iraab.JARR) in _funcs("فِي الْبَيْتِ")
    a = iraab.analyze("كِتَابُ الْوَلَدِ")
    assert a.words[1].function == "مضاف إليه" and a.words[1].read_case == iraab.JARR


def test_iraab_flags_wrong_case():
    # الكتابُ as object should be naṣb; written marfūʿ → flagged as a mismatch
    a = iraab.analyze("قَرَأَ الْوَلَدُ الْكِتَابُ")
    obj = a.words[2]
    assert obj.function == "مفعول به" and obj.expected_case == iraab.NASB
    assert obj.read_case == iraab.RAF and obj.ok is False


def test_madi_verb_is_mabni_no_case():
    a = iraab.analyze("ذَهَبَ الْوَلَدُ")
    assert a.words[0].pos == "فعل" and a.words[0].read_case is None


# --- web API layer (called directly; no HTTP server needed) -----------------

def test_web_endpoints():
    from app.arabic import web

    assert web.health()["capabilities"]["iraab"] is True
    assert len(web.letters()["letters"]) == 29
    assert web.letter("ض")["heavy"] is True

    tj = web.analyze_tajweed(web.TextIn(text="مِنْ بَعْدِ"))
    assert "iqlab" in [f["key"] for f in tj["findings"]]

    cj = web.conjugate(web.ConjugateIn(root="كتب", form=1))
    assert cj["madi"]["3ms"] == _n("كَتَبَ")
    assert "pronouns" in cj

    ir = web.analyze_iraab(web.SentenceIn(sentence="الْوَلَدُ مُجْتَهِدٌ"))
    assert ir["kind"] == "جملة اسمية"
    assert ir["words"][0]["function"] == "مبتدأ"

    assert len(web.levels()["levels"]) == 6
    assert "roots" in web.vocabulary()


def test_web_conjugate_rejects_weak_verb():
    from fastapi import HTTPException
    from app.arabic import web
    with pytest.raises(HTTPException):
        web.conjugate(web.ConjugateIn(root="قول", form=1))

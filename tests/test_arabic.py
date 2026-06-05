"""Tests for the offline Arabic knowledge engine (data + phonology + tajwīd)."""

from __future__ import annotations

import pytest

from app.arabic import data, phonology, tajweed


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

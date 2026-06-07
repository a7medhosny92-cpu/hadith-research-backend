"""Tests for isnad structural analysis (/verify-isnad)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.qa.isnad import analyze_isnad, overall_ruling
from app.routers.search import get_index
from app.search import HadithIndex


def _analysis(weakest, unknown=0, anana=False):
    return {"rijal_assessment": {"weakest_rank": weakest, "unknown": unknown},
            "has_anana": anana}

CHAIN = (
    "حدثنا الحميدي، حدثنا سفيان، حدثنا يحيى بن سعيد، "
    "عن محمد بن إبراهيم، عن علقمة بن وقاص، عن عمر بن الخطاب"
)


def test_parses_narrators_and_modes():
    a = analyze_isnad(CHAIN)
    names = [n["name"] for n in a.narrators]
    assert a.length == 6
    assert "سفيان" in names
    assert any("يحيى" in n for n in names)
    assert a.modes == {"سماع": 3, "عنعنة": 3}
    assert a.has_anana and not a.has_tahwil


def test_anna_opens_a_marfu_report_to_the_prophet():
    # «… عن ابن عمر أنّ رسول الله ﷺ قال …» — «أنّ» must end the narrator and let the
    # Prophet be terminal, not glue «أن رسول الله» onto «ابن عمر».
    a = analyze_isnad("عن سالم عن ابن عمر أن رسول الله صلى الله عليه وسلم قال خذوا")
    names = [n["name"] for n in a.narrators]
    assert names[:2] == ["سالم", "ابن عمر"]
    assert a.reaches_prophet                              # marfūʿ — reaches the Prophet
    assert not any("أن" in n.split() for n in names)      # no «… أن رسول الله» bogus node


def test_anna_with_non_prophet_subject_ends_the_chain():
    # «… عن ابن عمر أنّ رجلاً سأل …» — not marfūʿ; the chain stops, no bogus «رجلا» narrator.
    names = [n["name"] for n in analyze_isnad("عن ابن عمر أن رجلا سأل النبي").narrators]
    assert names == ["ابن عمر"]


def test_detects_tahwil_with_waw_connectors():
    a = analyze_isnad("حدثنا أبو بكر، حدثنا غندر، عن شعبة ح وحدثنا محمد، عن منصور")
    assert a.has_tahwil
    # the waw-prefixed connector is recognised, so محمد is its own narrator
    assert any(n["name"] == "محمد" for n in a.narrators)


def test_reaches_prophet():
    assert analyze_isnad("حدثنا فلان، عن أنس، عن النبي صلى الله عليه وسلم").reaches_prophet
    assert not analyze_isnad("حدثنا فلان، عن أنس").reaches_prophet


# ── matn must not leak into the last narrator (audit ISN-1/2/3) ───────────────
def test_matn_does_not_leak_into_last_narrator():
    a = analyze_isnad("حدثنا الحميدي حدثنا سفيان عن عمر بن الخطاب "
                      "عن النبي صلى الله عليه وسلم قال إنما الأعمال بالنيات")
    names = [n["name"] for n in a.narrators]
    assert names == ["الحميدي", "سفيان", "عمر بن الخطاب", "النبي صلى الله عليه وسلم"]
    assert not any("الأعمال" in n or "إنما" in n for n in names)


def test_matn_stops_at_qala_for_any_chain_end():
    a = analyze_isnad("عن أبي هريرة قال إنما الأعمال بالنيات")
    assert [n["name"] for n in a.narrators] == ["أبي هريرة"]


def test_qala_followed_by_transmission_is_connective():
    a = analyze_isnad("حدثنا فلان قال حدثنا علان عن أنس")
    assert [n["name"] for n in a.narrators] == ["فلان", "علان", "أنس"]


def test_reaches_prophet_is_false_for_mawquf_mentioning_prophet():
    # the matn mentions the Prophet but the chain stops at a Companion → not marfūʿ
    a = analyze_isnad("حدثنا فلان عن عمر قال كان النبي صلى الله عليه وسلم")
    assert not a.reaches_prophet


# ── overall ruling (الحكم على الإسناد) ───────────────────────────────────────
def test_ruling_all_thiqat_connected_is_sahih():
    r = overall_ruling(_analysis(9), {"total": 5, "seen": 5})
    assert r["tone"] == "sahih" and r["grade"] == "صحيح"


def test_ruling_sadduq_is_hasan():
    assert overall_ruling(_analysis(7))["tone"] == "hasan"


def test_ruling_weakest_matruk_is_very_weak():
    r = overall_ruling(_analysis(1))
    assert r["tone"] == "daif" and "جدًا" in r["grade"]


def test_ruling_break_overrides_strong_rijal():
    # rijal all ثقات, but a chain link is unseen → ضعيف للانقطاع
    r = overall_ruling(_analysis(9), {"total": 5, "seen": 3})
    assert r["tone"] == "daif" and "انقطاع" in r["reason"]


def test_ruling_unknown_narrators_hold_the_verdict():
    r = overall_ruling(_analysis(9, unknown=2))
    assert r["tone"] == "other" and "يُتوقَّف" in r["grade"]


def test_ruling_anana_caveats_a_sound_chain():
    r = overall_ruling(_analysis(9, anana=True), {"total": 5, "seen": 5})
    assert r["tone"] == "sahih" and "السماع" in r["reason"]


def test_ruling_unknown_rijal_not_judged():
    assert overall_ruling(_analysis(None))["tone"] == "other"


# ── API ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def client() -> TestClient:
    idx = HadithIndex()
    idx.add([{
        "book_id": 1284, "number": 1, "matn": "إنما الأعمال بالنيات",
        "isnad": CHAIN, "grade": "صحيح", "chapter": "بدء الوحي", "page": 179, "volume": "1",
    }])
    app.dependency_overrides[get_index] = lambda: idx
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_verify_by_text(client):
    r = client.get("/verify-isnad", params={"isnad": CHAIN})
    assert r.status_code == 200
    body = r.json()
    assert body["analysis"]["length"] == 6
    # the bottom-line verdict is always present
    assert {"grade", "tone", "reason", "disclaimer"} <= body["ruling"].keys()


def test_api_verify_by_hadith_id(client):
    hid = client.get("/search", params={"q": "الأعمال"}).json()["results"][0]["id"]
    body = client.get("/verify-isnad", params={"hadith_id": hid}).json()
    assert body["analysis"]["modes"]["عنعنة"] == 3


def test_api_verify_requires_input(client):
    assert client.get("/verify-isnad").status_code == 422
    assert client.get("/verify-isnad", params={"hadith_id": 999999}).status_code == 404

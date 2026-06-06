"""Tests for the /ask retrieval-grounded answer (hadith + linked شرح)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.qa import answer_question
from app.qa.llm import synthesizer_for_engine
from app.routers import ask as ask_router
from app.routers.ask import get_sharh_index
from app.routers.search import get_index
from app.search import HadithIndex, SharhIndex

HADITH = [
    {
        "book_id": 1284, "number": 1,
        "matn": "إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ", "isnad": "حدثنا الحميدي",
        "grade": "صحيح", "chapter": "بدء الوحي", "page": 179, "volume": "1",
    },
    {
        "book_id": 1727, "number": 3,
        "matn": "مَنْ كَذَبَ عَلَيَّ مُتَعَمِّدًا", "isnad": "حدثنا أبو بكر",
        "grade": "صحيح", "chapter": "المقدمة", "page": 10, "volume": "1",
    },
]

SHARH = [
    {
        "book_id": 1673, "sharh": "فتح الباري", "base_id": 1284, "base_name": "صحيح البخاري",
        "hadith_number": 1, "chapter": "بدء الوحي", "page": 11, "page_id": 495,
        "text": "قوله إنما الأعمال بالنيات أي الأعمال الصالحة، والنية شرط في صحة العمل عند الجمهور.",
    },
    {
        "book_id": 5756, "sharh": "عمدة القاري", "base_id": 1284, "base_name": "صحيح البخاري",
        "hadith_number": 1, "chapter": "بدء الوحي", "page": 20, "page_id": 510,
        "text": "النية محلها القلب وهي قصد الشيء مقترنا بفعله.",
    },
]


@pytest.fixture
def hadith_index() -> HadithIndex:
    idx = HadithIndex()
    idx.add(HADITH)
    return idx


@pytest.fixture
def sharh_index() -> SharhIndex:
    idx = SharhIndex()
    idx.add(SHARH)
    return idx


def test_answer_links_commentary_to_top_hadith(hadith_index, sharh_index):
    out = answer_question("الأعمال بالنيات", hadith_index, sharh_index)
    assert out["mode"] == "extractive"
    assert out["hadith"][0]["number"] == 1
    # commentary is the one linked to Bukhari #1, surfaced by question relevance
    assert out["sharh"] and out["sharh"][0]["hadith_number"] == 1
    assert out["sharh"][0]["sharh"] == "فتح الباري"
    assert out["hadith"][0]["matn"] in out["answer"]  # matn quoted verbatim
    assert "فتح الباري" in out["answer"]               # commentary attributed


def test_answer_without_match(hadith_index, sharh_index):
    out = answer_question("السيارات الكهربائية الحديثة", hadith_index, sharh_index)
    assert out["hadith"] == [] and out["sharh"] == []
    assert "لم أعثر" in out["answer"]


def test_synthesizer_is_used_when_provided(hadith_index, sharh_index):
    out = answer_question(
        "النية", hadith_index, sharh_index,
        synthesize=lambda q, h, s: f"ملخص: {q} (مصادر: {len(h)} حديث، {len(s)} شرح)",
    )
    assert out["mode"] == "llm"
    assert out["answer"].startswith("ملخص: النية")


def test_k_sharh_zero_skips_commentary(hadith_index, sharh_index):
    out = answer_question("الأعمال بالنيات", hadith_index, sharh_index, k_sharh=0)
    assert out["sharh"] == []


# ── API ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def client(hadith_index, sharh_index) -> TestClient:
    app.dependency_overrides[get_index] = lambda: hadith_index
    app.dependency_overrides[get_sharh_index] = lambda: sharh_index
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_ask(client):
    r = client.get("/ask", params={"q": "الأعمال بالنيات"})
    assert r.status_code == 200
    body = r.json()
    assert body["hadith"][0]["collection"] == "صحيح البخاري"
    assert body["sharh"][0]["sharh"] == "فتح الباري"
    assert body["hadith"][0]["matn"] in body["answer"]


def test_api_ask_requires_question(client):
    assert client.get("/ask").status_code == 422


# ── LLM engine switch (local ↔ remote ↔ off) ──────────────────────────────────
def test_synthesizer_for_engine_mapping():
    s = get_settings()
    assert synthesizer_for_engine("off", s) is None
    # local/remote build a callable lazily — no litellm import, no network here
    assert callable(synthesizer_for_engine("local", s))
    assert callable(synthesizer_for_engine("remote", s))
    with pytest.raises(ValueError):
        synthesizer_for_engine("bogus", s)


def test_resolve_engine_auto_follows_default():
    s = get_settings()  # default engine ships as "off"
    assert ask_router.resolve_engine("auto", s) == s.llm_default_engine
    for eng in ("local", "remote", "off"):
        assert ask_router.resolve_engine(eng, s) == eng


def test_api_ask_engine_off_is_extractive(client):
    body = client.get("/ask", params={"q": "الأعمال بالنيات", "engine": "off"}).json()
    assert body["mode"] == "extractive"
    assert body["engine"] == "off"


def test_api_ask_engine_routes_to_llm(client, monkeypatch):
    # Swap in a fake brain so no real model or network is touched.
    monkeypatch.setattr(
        ask_router, "build_synthesizer",
        lambda engine, settings, model=None: (lambda q, h, s: f"[{engine}] {q}"),
    )
    body = client.get("/ask", params={"q": "النية", "engine": "remote"}).json()
    assert body["mode"] == "llm"
    assert body["engine"] == "remote"
    assert body["answer"] == "[remote] النية"


def test_api_ask_rejects_unknown_engine(client):
    assert client.get("/ask", params={"q": "النية", "engine": "wat"}).status_code == 422


def test_api_ask_falls_back_when_engine_unavailable(client, monkeypatch):
    # The chosen brain is unreachable (Ollama down / missing key / no litellm): the
    # synthesizer raises. /ask must still answer — extractively — with a warning.
    def boom(engine, settings, model=None):
        def _raise(q, h, s):
            raise RuntimeError("engine unavailable")
        return _raise

    monkeypatch.setattr(ask_router, "build_synthesizer", boom)
    body = client.get("/ask", params={"q": "الأعمال بالنيات", "engine": "remote"}).json()
    assert body["mode"] == "extractive"   # fell back, did not 500
    assert body["engine"] == "off"
    assert "warning" in body

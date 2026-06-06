"""Tests for the narrator network (graph, /narrator, isnad continuity)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rijal.graph import NarratorGraph
from app.routers.search import get_index
from app.routers.verify_isnad import get_graph
from app.search import HadithIndex


@pytest.fixture
def graph() -> NarratorGraph:
    g = NarratorGraph()
    # Two routes onto the same مالك → نافع → ابن عمر → النبي backbone.
    g.add_chain(["قتيبة", "مالك", "نافع", "ابن عمر", "النبي"])
    g.add_chain(["يحيى بن يحيى", "مالك", "نافع", "ابن عمر", "النبي"])
    g.commit()
    return g


# ── graph core ────────────────────────────────────────────────────────────────
def test_teachers_and_students(graph):
    teachers = {t["name"] for t in graph.teachers("مالك")}
    students = {s["name"] for s in graph.students("نافع")}
    assert "نافع" in teachers          # مالك narrates from نافع
    assert "مالك" in students          # مالك narrates from نافع → مالك is its student


def test_link_weight_counts_repeats(graph):
    assert graph.link_weight("مالك", "نافع") == 2     # both routes share this link
    assert graph.link_weight("قتيبة", "مالك") == 1
    assert graph.link_weight("نافع", "قتيبة") == 0     # not a real link


def test_resolve_by_subset(graph):
    node = graph.resolve("ابن عمر")
    assert node is not None and "عمر" in node.name


def test_disambiguates_shared_name():
    g = NarratorGraph()
    g.add_chain(["وكيع", "سفيان", "منصور", "إبراهيم"])           # context ⇒ al-Thawrī
    g.add_chain(["الحميدي", "سفيان", "عمرو بن دينار", "عطاء"])   # context ⇒ Ibn ʿUyayna
    g.commit()
    names = {n.name for n in g._nodes()}
    assert "سفيان الثوري" in names and "سفيان بن عيينة" in names   # split into two people
    assert any(t["name"] == "منصور" for t in g.teachers("سفيان الثوري"))
    assert any(t["name"] == "عمرو بن دينار" for t in g.teachers("سفيان بن عيينة"))


# ── /narrator endpoint ──────────────────────────────────────────────────────────
@pytest.fixture
def client(graph) -> TestClient:
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_index] = lambda: HadithIndex()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_narrator(client):
    body = client.get("/narrator", params={"name": "مالك"}).json()
    assert "نافع" in {t["name"] for t in body["teachers"]}
    students = {s["name"] for s in body["students"]}
    assert {"قتيبة", "يحيى بن يحيى"} <= students


def test_api_narrator_unknown(client):
    assert client.get("/narrator", params={"name": "شخص مجهول تماما هنا"}).status_code == 404


def test_api_narrator_has_summary_and_sources(client):
    body = client.get("/narrator", params={"name": "مالك"}).json()
    assert "شيخًا" in body["summary"] and "راويًا" in body["summary"]   # composed profile
    assert any("أسانيد" in s["from"] for s in body["sources"])          # provenance shown


# ── isnad continuity via the graph ─────────────────────────────────────────────
def test_verify_isnad_reports_continuity(client):
    body = client.get("/verify-isnad", params={"isnad": "حدثنا قتيبة عن مالك عن نافع"}).json()
    cont = body["continuity"]
    seen = {(l["from"], l["to"]): l["seen"] for l in cont["links"]}
    assert seen[("مالك", "نافع")] is True          # a known link
    assert cont["seen"] >= 1 and cont["total"] == len(cont["links"])


def test_verify_isnad_flags_unseen_link(client):
    # فلان → علان is never in the corpus → flagged as not-seen (possible انقطاع).
    body = client.get("/verify-isnad", params={"isnad": "حدثنا فلان عن علان"}).json()
    assert body["continuity"]["seen"] == 0

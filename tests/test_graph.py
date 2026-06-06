"""Tests for the narrator network (NarratorGraph) — Prophet/relatives/disambiguation."""

from __future__ import annotations

from app.rijal.graph import NarratorGraph, is_prophet


def test_is_prophet_matches_core_not_matn():
    assert is_prophet("النبي")
    assert is_prophet("رسول الله")
    assert is_prophet("النبي صلى الله عليه وسلم")
    assert not is_prophet("النبي مثله")          # matn word — not the Prophet
    assert not is_prophet("محمد بن إسماعيل")     # a narrator named محمد is not the Prophet
    assert not is_prophet("")


def test_prophet_variants_collapse_to_one_node():
    g = NarratorGraph(":memory:")
    for teacher in ("النبي صلى الله عليه وسلم", "رسول الله صلى الله عليه وسلم", "النبي"):
        g.add_chain(["مالك", "عمر بن الخطاب", teacher])
    g.commit()
    teachers = g.teachers("عمر بن الخطاب")
    assert len(teachers) == 1
    assert teachers[0]["name"] == "النبي ﷺ"
    assert teachers[0]["count"] == 3


def test_relatives_make_no_hub_node_and_break_the_chain():
    g = NarratorGraph(":memory:")
    g.add_chain(["عمرو بن شعيب", "أبيه", "جده"])
    g.add_chain(["بهز بن حكيم", "أبيه", "جده"])
    g.commit()
    # «أبيه»/«جده» are not nodes, so they never become a shared teacher/student hub
    assert g.resolve("أبيه") is None
    assert g.resolve("جده") is None
    assert g.teachers("عمرو بن شعيب") == []


def test_disambiguates_sufyan_from_neighbours():
    g = NarratorGraph(":memory:")
    g.add_chain(["الحميدي", "سفيان", "عمرو بن دينار"])   # → ابن عيينة
    g.add_chain(["وكيع", "سفيان", "الأعمش"])              # → الثوري
    g.commit()
    assert g.resolve("سفيان بن عيينة") is not None
    assert g.resolve("سفيان الثوري") is not None


def test_disambiguates_from_a_marker_several_links_away():
    # the telltale شيخ is not the immediate neighbour (audit RIJ-2)
    g = NarratorGraph(":memory:")
    g.add_chain(["تلميذ مجهول", "سفيان", "وكيع", "الأعمش"])          # → الثوري
    g.add_chain(["راوٍ آخر", "سفيان", "ابن أبي عمر", "عمرو بن دينار"])  # → ابن عيينة
    g.commit()
    assert g.resolve("سفيان الثوري") is not None
    assert g.resolve("سفيان بن عيينة") is not None

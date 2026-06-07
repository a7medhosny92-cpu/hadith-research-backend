"""Name unification (توحيد الاسم/الكنية/اللقب): the رجال-backed canonicalizer.

Covers the exact cases from a real راوٍ card — the same man split into many nodes
because he is written short/long, by ism/nasab/kunya/laqab — and the safety guards
that stop us from ever fusing two *different* men.
"""

from __future__ import annotations

from app.parsing.rijal_extract import _aliases
from app.rijal.canon import Canonicalizer
from app.rijal.graph import NarratorGraph
from app.rijal.index import RijalIndex, _clean_tokens

# A small authority resembling the full DB: full names, some kunya, a few homonyms.
ENTRIES = [
    {"name": "عبد الرحمن بن صخر الدوسي", "kunya": "أبو هريرة", "grade": "صحابي"},
    {"name": "عمر بن الخطاب", "aliases": ["الفاروق"], "kunya": "أبو حفص", "grade": "صحابي"},
    {"name": "عطاء بن يزيد الليثي", "grade": "ثقة"},
    {"name": "سعيد بن المسيب", "grade": "ثقة"},
    {"name": "سعيد بن جبير", "grade": "ثقة"},
    {"name": "عبيد الله بن عبد الله بن عتبة", "grade": "ثقة"},
    {"name": "عبد الله بن عمر", "grade": "صحابي"},
    {"name": "أنس بن مالك", "grade": "صحابي"},
    {"name": "أنس بن سيرين", "grade": "ثقة"},
    {"name": "الزهري", "grade": "ثقة"},
]


def _canon(associations=None):
    return Canonicalizer(RijalIndex(ENTRIES), associations=associations)


# ── Tier 1: confident, context-free merges ───────────────────────────────────────
def test_kunya_resolves_to_real_name():
    assert _canon().canonical("أبو هريرة") == "عبد الرحمن بن صخر الدوسي"


def test_laqab_resolves_to_real_name():
    assert _canon().canonical("الفاروق") == "عمر بن الخطاب"


def test_short_form_merges_into_full_name():
    # عطاء بن يزيد ↦ عطاء بن يزيد الليثي  (a unique nisba completion)
    assert _canon().canonical("عطاء بن يزيد") == "عطاء بن يزيد الليثي"


def test_nasab_fragment_resolves():
    # ابن المسيب ↦ سعيد بن المسيب  (the ism and the nasab fragment are the same man)
    assert _canon().canonical("ابن المسيب") == "سعيد بن المسيب"
    assert _canon().canonical("عبيد الله") == "عبيد الله بن عبد الله بن عتبة"


# ── safety: never fuse two different men ──────────────────────────────────────────
def test_order_guard_blocks_false_merge():
    # «عبد الله» must NOT collapse into «عبيد الله بن عبد الله بن عتبة» (different man) —
    # the shared tokens are out of order — it resolves to its own entry instead.
    c = _canon()
    assert c.canonical("عبد الله") == "عبد الله بن عمر"
    assert c.canonical("عبد الله") != c.canonical("عبيد الله")


def test_unknown_name_is_left_unchanged():
    assert _canon().canonical("راوٍ مجهول لا وجود له") == "راوٍ مجهول لا وجود له"


def test_ambiguous_without_context_kept_as_surface():
    # سعيد is shared (المسيب / جبير); with nothing to decide, keep the surface form.
    assert _canon().canonical("سعيد") == "سعيد"


# ── Tier 2: context decides between homonyms ──────────────────────────────────────
def test_context_disambiguates_shared_ism():
    assoc = {
        "سعيد بن المسيب": set(_clean_tokens("أبو هريرة")),
        "سعيد بن جبير": set(_clean_tokens("ابن عباس")),
    }
    c = _canon(assoc)
    assert c.canonical("سعيد", frozenset(_clean_tokens("أبو هريرة"))) == "سعيد بن المسيب"
    assert c.canonical("سعيد", frozenset(_clean_tokens("ابن عباس"))) == "سعيد بن جبير"


def test_context_tie_keeps_surface():
    # both candidates fit the context equally → no confident pick → surface kept.
    assoc = {"سعيد بن المسيب": {"شعبة"}, "سعيد بن جبير": {"شعبة"}}
    assert _canon(assoc).canonical("سعيد", frozenset({"شعبة"})) == "سعيد"


# ── integration with the graph ───────────────────────────────────────────────────
def test_graph_merges_variants_with_canon():
    g = NarratorGraph()
    canon = _canon()
    g.add_chain(["الزهري", "عطاء بن يزيد الليثي", "النبي"], canon=canon)
    g.add_chain(["الزهري", "عطاء بن يزيد", "النبي"], canon=canon)
    g.commit()
    teachers = {t["name"] for t in g.teachers("الزهري")}
    assert "عطاء بن يزيد الليثي" in teachers
    assert "عطاء بن يزيد" not in teachers            # the short form merged into the full


def test_graph_without_canon_is_unchanged():
    # backward compatible: no canonicalizer → the old surface-form behaviour.
    g = NarratorGraph()
    g.add_chain(["الزهري", "عطاء بن يزيد الليثي", "النبي"])
    g.add_chain(["الزهري", "عطاء بن يزيد", "النبي"])
    g.commit()
    teachers = {t["name"] for t in g.teachers("الزهري")}
    assert {"عطاء بن يزيد الليثي", "عطاء بن يزيد"} <= teachers   # both kept separate


def test_two_pass_context_merges_bare_ism():
    """The build's two-pass flow: pass 1 (confident) learns each man's company, pass 2
    uses it to fold a bare ism (أنس) onto the right person from the chain context."""
    rij = RijalIndex(ENTRIES)
    chains = [
        ["الزهري", "أنس بن مالك", "النبي"],   # full form — its company includes الزهري
        ["محمد", "أنس بن سيرين", "النبي"],     # the other أنس — different company
        ["الزهري", "أنس", "النبي"],            # bare — should fold onto أنس بن مالك
    ]
    canon0 = Canonicalizer(rij)
    g0 = NarratorGraph()
    for ch in chains:
        g0.add_chain(ch, canon=canon0)
    g0.commit()
    profiles = {
        name: set().union(*(_clean_tokens(nb) for nb in neigh)) if neigh else set()
        for name, neigh in g0.adjacency().items()
    }
    canon1 = Canonicalizer(rij, associations=profiles)
    g1 = NarratorGraph()
    for ch in chains:
        g1.add_chain(ch, canon=canon1)
    g1.commit()
    teachers = {t["name"] for t in g1.teachers("الزهري")}
    assert "أنس بن مالك" in teachers
    assert "أنس" not in teachers              # bare أنس disambiguated by context


# ── Part 3: laqab/shuhra extraction from the biography ────────────────────────────
def test_alias_extraction_is_conservative():
    assert _aliases("محمد بن عبد الرحمن المعروف بابن أبي ذئب ثقة") == ["ابن أبي ذئب"]
    assert _aliases("سليمان بن مهران المعروف بالأعمش ثقة حافظ") == ["الأعمش"]
    assert _aliases("فلان يقال له ابن علية ثقة") == ["ابن علية"]
    assert _aliases("عبد الله المعروف بالدارمي صاحب المسند ثقة") == ["الدارمي"]
    # never invents one: «المشهور بشر» (a man named بشر) yields nothing
    assert _aliases("بشر بن المفضل المشهور بشر ثقة") == []
    assert _aliases("إنما الأعمال بالنيات") == []

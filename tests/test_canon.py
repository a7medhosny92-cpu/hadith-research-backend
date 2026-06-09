"""Name unification (توحيد الاسم/الكنية/اللقب): the رجال-backed canonicalizer.

Covers the exact cases from a real راوٍ card — the same man split into many nodes
because he is written short/long, by ism/nasab/kunya/laqab — and the safety guards
that stop us from ever fusing two *different* men.
"""

from __future__ import annotations

from app.parsing.rijal_extract import _aliases
from app.rijal.canon import Canonicalizer
from app.rijal.graph import NarratorGraph, _is_relative, is_unnamed_kin
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


def test_chain_company_overrides_a_confident_namesake():
    """«La catena prima del nome»: a متروك *bare* namesake would win on the name alone
    (most specific), but the chain's company — he narrates from محمد بن عمرو up to ابن أبي
    شيبة — belongs to محمد بن بشر العبدي [ثقة]. The chain must decide, not the bare name."""
    rij = RijalIndex([
        {"name": "محمد بن بشر", "grade": "متروك"},              # a bare namesake
        {"name": "محمد بن بشر العبدي", "grade": "ثقة"},          # the man the chain points to
    ])
    company = _clean_tokens("محمد بن عمرو أبو بكر بن أبي شيبة أبو سلمة")
    canon = Canonicalizer(rij, associations={"محمد بن بشر العبدي": set(company)})
    # with the chain context, identity is taken from the company → العبدي (ثقة)
    assert canon.canonical("محمد بن بشر", frozenset(company)) == "محمد بن بشر العبدي"
    # without the chain, the name alone gives only the most-specific (bare) namesake
    assert canon.canonical("محمد بن بشر") == "محمد بن بشر"


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


# ── the «أبي» bug: «my father» must not become a hub, but IS a real person ────────
def test_bare_kinship_is_a_relative_marker():
    # first- and third-person kinship, plus a bare kunya particle, aren't plain narrators.
    for w in ("أبي", "أمي", "جدي", "أخي", "عمي", "خالي", "أبو", "أبا", "أبيه", "جده"):
        assert _is_relative(w), w


def test_my_father_resolves_to_the_real_man_not_a_hub():
    # «حدثني أبي» must create no «أبي» hub — it resolves to the real father from the nasab.
    g = NarratorGraph()
    g.add_chain(["عبد الله بن أحمد بن حنبل", "أبي", "الأعمش"])   # أبي = أحمد بن حنبل
    g.commit()
    names = {n.name for n in g._nodes()}
    assert "أبي" not in names                                    # no bogus father-of-all hub
    assert "أحمد بن حنبل" in names                               # resolved to the real man
    assert {t["name"] for t in g.teachers("عبد الله بن أحمد بن حنبل")} == {"أحمد بن حنبل"}


def test_apposition_father_is_resolved():
    g = NarratorGraph()
    g.add_chain(["أبي بردة", "أبيه أبي موسى", "النبي"])          # apposition names the father
    g.commit()
    assert {t["name"] for t in g.teachers("أبي بردة")} == {"أبي موسى"}


def test_person_named_ubayy_is_kept_not_treated_as_pronoun():
    # أُبَيّ بن كعب (a Companion) is a PERSON — «أبي بن …» must survive as a node.
    g = NarratorGraph()
    g.add_chain(["الحسن", "أبي بن كعب", "النبي"])
    g.commit()
    node = g.resolve("أبي بن كعب")
    assert node is not None and "كعب" in node.name
    assert {t["name"] for t in g.teachers("الحسن")} == {"أبي بن كعب"}


def test_unnamed_ancestor_keeps_the_link_anchored():
    # an unidentifiable grandfather is kept as «جدّ X» (anchored), so the link survives.
    g = NarratorGraph()
    g.add_chain(["عمرو بن شعيب", "أبيه", "جده", "النبي"])
    g.add_chain(["بهز بن حكيم", "أبيه", "جده", "النبي"])
    g.commit()
    assert {t["name"] for t in g.teachers("شعيب")} == {"جدّ عمرو بن شعيب"}
    assert is_unnamed_kin("جدّ عمرو بن شعيب")
    assert "جدّ عمرو بن شعيب" != "جدّ بهز بن حكيم"          # anchored, so no shared hub


def test_unnamed_ancestor_is_not_misgraded():
    from app.qa.dossier import narrator_dossier
    g = NarratorGraph()
    g.add_chain(["عمرو بن شعيب", "أبيه", "جده", "النبي"])
    g.commit()
    rij = RijalIndex([{"name": "عمرو بن شعيب", "grade": "ثقة"}])
    d = narrator_dossier("جدّ عمرو بن شعيب", g, rij)
    assert d is not None and d["grade"] is None            # NOT graded as عمرو بن شعيب himself
    nb = narrator_dossier("شعيب", g, rij)
    grandfather = next(t for t in nb["teachers"] if is_unnamed_kin(t["name"]))
    assert grandfather["grade"] is None                    # nor as a neighbour


def test_all_kinship_relations_are_anchored():
    # the placeholder applies to EVERY unidentified kinship link, not just the father.
    g = NarratorGraph()
    g.add_chain(["مسدد بن مسرهد", "أخيه", "النبي"])     # brother  → أخو …
    g.add_chain(["وكيع بن الجراح", "أمه", "النبي"])      # mother   → والدة …
    g.add_chain(["يحيى بن سعيد", "عمه", "النبي"])        # uncle    → عمّ …
    g.commit()
    assert {t["name"] for t in g.teachers("مسدد بن مسرهد")} == {"أخو مسدد بن مسرهد"}
    assert {t["name"] for t in g.teachers("وكيع بن الجراح")} == {"والدة وكيع بن الجراح"}
    assert {t["name"] for t in g.teachers("يحيى بن سعيد")} == {"عمّ يحيى بن سعيد"}
    for ph in ("أخو مسدد بن مسرهد", "والدة وكيع بن الجراح", "عمّ يحيى بن سعيد"):
        assert is_unnamed_kin(ph)


def test_rebuild_upgrades_placeholder_when_data_improves():
    # «… عن أبيه عن جده» — when richer رجال data later names the man, a *rebuild* promotes
    # the placeholder to the real person (the build reads current data from scratch).
    chains = [["بهز بن حكيم", "أبيه", "جده", "النبي"]]

    def build(entries):
        canon = Canonicalizer(RijalIndex(entries))
        g = NarratorGraph()
        for ch in chains:
            g.add_chain(ch, canon=canon)
        g.commit()
        return {n.name for n in g._nodes()}

    sparse = build([{"name": "بهز بن حكيم", "grade": "صدوق"}])
    assert any(is_unnamed_kin(n) for n in sparse)                       # grandfather unnamed
    rich = build([{"name": "بهز بن حكيم بن معاوية بن حيدة", "grade": "صدوق"}])
    assert not any(is_unnamed_kin(n) for n in rich)                     # …now named
    assert "معاوية بن حيدة" in rich                                     # the real grandfather


def test_lookup_refuses_bare_kinship_particles():
    # «أبي» must NOT resolve to «عائشة بنت أبي بكر» (matched through «بنت أبي بكر»).
    rij = RijalIndex([
        {"name": "عائشة بنت أبي بكر", "kunya": "أم عبد الله", "grade": "صحابي", "death_year": 57},
        {"name": "عبد الله بن عمر", "grade": "صحابي"},
    ])
    for q in ("أبي", "أبو", "أبا", "أم", "عبد"):
        assert rij.lookup(q) is None, q
    assert rij.lookup("عبد الله بن عمر") is not None        # a real name still resolves


def test_canon_keeps_bare_particle_as_surface():
    # the canonicalizer leaves a bare particle untouched (no false identity).
    assert _canon().canonical("أبي") == "أبي"


def test_verdict_identifies_a_shared_name_from_the_chain_company():
    """تمييز المهمل: «جعفر بن محمد» beside محمد الباقر/جابر is الصادق (ثقة), not a مجهول
    namesake. The verdict must pick the man whose recorded company fits the chain."""
    from app.qa.isnad import analyze_isnad

    rijal = RijalIndex([
        {"name": "جعفر بن محمد الصادق", "grade": "ثقة"},
        {"name": "جعفر بن محمد البلخي", "grade": "مجهول"},
        {"name": "محمد الباقر", "grade": "ثقة"},
        {"name": "جابر بن عبد الله", "grade": "صحابي"},
        {"name": "سفيان الثوري", "grade": "ثقة"},
    ])
    chain = "حدثنا سفيان الثوري، عن جعفر بن محمد، عن محمد الباقر، عن جابر بن عبد الله"

    # context-free: the bare «جعفر بن محمد» is a real homonym → flagged, never a confident grade
    bare = analyze_isnad(chain, rijal=rijal)
    jb = next(n for n in bare.narrators if n["name"].startswith("جعفر"))
    assert jb["rijal"]["ambiguous"]

    # with the chain's company as context, it resolves to الصادق and grades HIM (ثقة)
    assoc = {
        "جعفر بن محمد الصادق": set(_clean_tokens("محمد الباقر جابر بن عبد الله سفيان الثوري")),
        "جعفر بن محمد البلخي": set(_clean_tokens("فلان الكوفي علان البصري")),
    }
    canon = Canonicalizer(rijal, associations=assoc)
    res = analyze_isnad(chain, rijal=rijal, canon=canon)
    jr = next(n for n in res.narrators if n["name"].startswith("جعفر"))
    assert jr["rijal"]["name"] == "جعفر بن محمد الصادق" and jr["rijal"]["grade"] == "ثقة"


def test_held_in_context_not_overridden_by_narrow_lookup_group():
    """The «يونس عن الزهري» bug: when the FULL homonym set ties in context (no confident pick), a
    narrower lookup group must not override the hold and pick a spurious winner (يونس بن عبيد)."""
    rij = RijalIndex([
        {"name": "يونس بن يزيد الأيلي", "grade": "ثقة"},
        {"name": "يونس بن عبيد البصري", "grade": "ثقة"},
        {"name": "يونس بن أبي إسحاق السبيعي", "grade": "صدوق"},
    ])
    assoc = {
        "يونس بن يزيد الأيلي": set(_clean_tokens("الزهري ابن وهب")),
        "يونس بن عبيد البصري": set(_clean_tokens("الزهري الحسن")),
    }
    c = Canonicalizer(rij, associations=assoc)
    # both keep company with الزهري → tie → HOLD the surface, never a confident عبيد
    assert c.canonical("يونس", frozenset(_clean_tokens("الزهري"))) == "يونس"

"""Tests for isnad structural analysis (/verify-isnad)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.qa.isnad import analyze_isnad, continuity, overall_ruling
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


def test_kinship_reference_resolves_to_the_ancestor():
    """«عن أبيه» is not a name: it resolves to the previous narrator's father from his nasab, so the
    verdict grades the man (هشام بن عروة عن أبيه → عروة), not a «غير معروف» «أبيه»."""
    from app.rijal import RijalIndex
    rijal = RijalIndex([
        {"name": "عروة بن الزبير الأسدي", "grade": "ثقة"},
        {"name": "عائشة أم المؤمنين", "grade": "صحابي"},
    ])
    a = analyze_isnad("حدثنا مالك عن هشام بن عروة عن أبيه عن عائشة", rijal=rijal)
    abih = next(n for n in a.narrators if "أبيه" in n["name"])
    assert abih.get("resolved") == "عروة"            # «أبيه» → عروة (the father in هشام's nasab)
    assert abih.get("rijal") is not None             # and it's graded, not «غير معروف»


def test_collective_adverb_dropped_from_co_narrators():
    """«… جميعاً / كلاهما» closes a co-narrator group and must not glue onto the last name."""
    names = [n["name"] for n in analyze_isnad("حدثنا أبو بكر بن أبي شيبة جميعا عن وكيع").narrators]
    assert "أبو بكر بن أبي شيبة" in names
    assert not any("جميع" in nm for nm in names)


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


def test_ruling_network_gap_is_a_caution_not_a_downgrade():
    # rijal all ثقات but a link is unseen in our graph: that is weak coverage evidence
    # (often just a name-form difference), so it must NOT flip the sound verdict — only caution.
    r = overall_ruling(_analysis(9), {"total": 5, "seen": 3})
    assert r["tone"] == "sahih" and "يُراجَع" in r["reason"]


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


def test_terminal_link_prefers_sahabi_over_later_homonym():
    """تمييز بالطبقة: a name at the Companion position (last link) that matches a صحابي IS that
    Companion — not a same-kunya homonym of a later طبقة (أبو ذر الغفاري, not the ثقة الكوفي)."""
    from app.rijal.index import RijalIndex
    rijal = RijalIndex([
        {"name": "جندب بن جنادة الغفاري", "kunya": "أبو ذر", "grade": "صحابي"},
        {"name": "عمر بن ذر الهمداني الكوفي", "kunya": "أبو ذر", "grade": "ثقة"},
    ])
    last = analyze_isnad("حدثنا فلان عن الأعمش عن أبي ذر", rijal=rijal).narrators[-1]["rijal"]
    assert last["name"] == "جندب بن جنادة الغفاري"
    assert last["grade"] == "صحابي"


def test_midchain_sahabi_prefers_non_sahabi():
    """Symmetric to the terminal rule: a صحابي match at a NON-terminal position is suspect — prefer
    a non-صحابي homonym («جرير» mid-chain → ابن عبد الحميد الثقة, not جرير البجلي الصحابي)."""
    from app.rijal.index import RijalIndex
    rijal = RijalIndex([
        {"name": "جرير بن عبد الله البجلي", "grade": "صحابي"},
        {"name": "جرير بن عبد الحميد الضبي", "grade": "ثقة"},
    ])
    a = analyze_isnad("حدثنا قتيبة عن جرير عن منصور عن إبراهيم", rijal=rijal)
    jarir = next(n for n in a.narrators if n["name"] == "جرير")
    assert jarir["rijal"]["grade"] == "ثقة"


def test_penultimate_companion_from_companion_kept():
    """صحابي عن صحابي: a younger Companion narrating from an older one (penultimate position) stays
    صحابي — the mid-chain «prefer non-صحابي» rule applies only DEEPER (≤ terminal−2). «أنس عن أبي
    بكر» keeps أنس بن مالك, not the tabi'i homonym أنس بن سيرين."""
    from app.rijal.index import RijalIndex
    rijal = RijalIndex([
        {"name": "أنس بن مالك", "grade": "صحابي"},
        {"name": "أنس بن سيرين", "grade": "ثقة"},
        {"name": "أبو بكر الصديق", "kunya": "أبو بكر", "grade": "صحابي"},
    ])
    anas = next(n for n in analyze_isnad("حدثنا قتيبة عن أنس عن أبي بكر", rijal=rijal).narrators
                if n["name"] == "أنس")
    assert anas["rijal"]["grade"] == "صحابي"


def test_companion_dictionary_sahabi_is_inert_mid_chain():
    """An obscure-Companion-dictionary (الإصابة) صحابي must not place a Companion DEEP in the chain:
    his bare ism+father over-matches a later same-named تابعي → a false «صحابي mid-chain» that also
    masks the real man. He is dropped to unknown mid-chain — but STILL identified at the terminal link
    (the whole point of الإصابة). A تقريب صحابي (a real famous Companion) is NOT affected by this guard."""
    from app.rijal.index import RijalIndex
    _ISABA = "الإصابة في تمييز الصحابة (رقم 9767)"
    rijal = RijalIndex([
        {"name": "سفيان بن عيينة", "grade": "ثقة", "source": "تقريب التهذيب (رقم 8609)"},
        {"name": "محمد بن عبد الله", "grade": "صحابي", "source": _ISABA},
        {"name": "حماد بن زيد", "grade": "ثقة", "source": "تقريب التهذيب (رقم 8609)"},
        {"name": "سعد بن مالك الساعدي", "grade": "صحابي", "source": _ISABA},
    ])
    # DEEP (≤ terminal−2): the الإصابة «محمد بن عبد الله» is honestly unknown, NOT graded صحابي
    deep = analyze_isnad("حدثنا أحمد عن سفيان بن عيينة عن محمد بن عبد الله عن حماد بن زيد "
                         "عن سعد بن مالك الساعدي عن النبي صلى الله عليه وسلم قال كذا", rijal=rijal)
    assert next(n for n in deep.narrators if n["name"] == "محمد بن عبد الله")["rijal"] is None
    # TERMINAL: an obscure الإصابة Companion at the chain's END is still identified صحابي
    term = analyze_isnad("حدثنا حماد بن زيد عن سعد بن مالك الساعدي عن النبي صلى الله عليه وسلم قال كذا",
                         rijal=rijal).narrators
    assert term[-2]["name"] == "سعد بن مالك الساعدي" and term[-2]["rijal"]["grade"] == "صحابي"


def test_object_pronoun_verb_closes_the_shaykh_not_glued():
    """«(أنّ) الزهري أخبره أنّ …» — an object-pronoun transmission verb «أخبره/حدثه/أنبأه» CLOSES the
    شيخ's name; it must not glue on, forging bogus nodes like «الزهري أخبره» (which aggregate his
    whole network in the narrator graph)."""
    names = [n["name"] for n in analyze_isnad(
        "حدثنا مالك عن الزهري أخبره أن رسول الله صلى الله عليه وسلم قال إنما الأعمال بالنيات").narrators]
    assert "الزهري" in names
    assert not any("اخبر" in n or "أخبر" in n for n in names)


@pytest.mark.parametrize("isnad, expect_node", [
    # «أنّهما/أنّهم» (dual/plural co-narrators) close the names instead of gluing «أنهما سمعا …» on (the
    # waw-split of the two men is a graph-build concern; in the verdict path the node stays as-is)
    ("حدثنا قتيبة عن ابن عباس وابن عمر أنهما سمعا النبي صلى الله عليه وسلم", "ابن عباس وابن عمر"),
    # قراءة + the «على» preposition skipped, so «قرأت على مالك» → مالك, not «قرأت على مالك»/«علي»
    ("أخبرنا قتيبة قرأت على مالك عن نافع عن ابن عمر", "مالك"),
    ("حدثنا فلان حدثتني عائشة عن النبي صلى الله عليه وسلم", "عائشة"),    # 1st-person transmission verb
    ("حدثنا فلان عن عائشة كان النبي صلى الله عليه وسلم يصلي", "عائشة"),  # «كان …» scene opener = matn
    ("حدثنا فلان عن أبي هريرة فذكره", "أبي هريرة"),                     # «فذكره» back-reference = matn
    ("حدثنا١ سفيان١ عن عمرو٢ عن جابر١", "سفيان"),                      # footnote-digit glue is stripped
    # al-Bukhārī's تعليق «… عن الزهري وقال الليث: حدّثني …» — «وقال الليث» must NOT glue onto الزهري
    ("حدثنا قتيبة عن مالك عن الزهري وقال الليث حدثني عقيل عن عروة", "الزهري"),
])
def test_segmentation_leaves_no_corrupt_nodes(isnad, expect_node):
    """The boundary rules found by scripts.audit_nodes: every finalised node is a clean name."""
    from scripts.audit_nodes import junk_in_node
    names = [n["name"] for n in analyze_isnad(isnad).narrators]
    assert expect_node in names
    assert all(not junk_in_node(n) for n in names)


# ── terminal-صحابي is gated on reaching the Prophet (C1: no مقطوع false-promotion) ─────────────
_ASWAD = [
    {"name": "الأسود بن يزيد النخعي", "grade": "ثقة"},      # تابعي — the real الأسود النخعي
    {"name": "الأسود بن سريع التميمي", "grade": "صحابي"},   # a صحابي homonym
]


def test_terminal_tabii_on_maqtu_not_forced_to_sahabi():
    """When the chain does NOT reach the Prophet (موقوف/مقطوع), the terminal need not be a Companion:
    a تابعي giving his own مقطوع (الأسود النخعي الثقة) must NOT be forced to a صحابي homonym
    (الأسود بن سريع). He is held as ambiguous — never confidently mis-identified."""
    from app.rijal.index import RijalIndex
    a = analyze_isnad("حدثنا فلان عن إبراهيم عن الأسود", rijal=RijalIndex(_ASWAD))
    assert not a.reaches_prophet
    last = a.narrators[-1]["rijal"]
    assert last["name"] != "الأسود بن سريع التميمي"   # not the forced صحابي
    assert last["ambiguous"]                           # honestly held, not a confident verdict


def test_terminal_forced_to_sahabi_only_when_reaches_prophet():
    """The mirror: narrating DIRECTLY from the Prophet ﷺ makes the man a Companion, so it IS resolved
    to the صحابي homonym (الأسود بن سريع), not the later تابعي الثقة."""
    from app.rijal.index import RijalIndex
    a = analyze_isnad("حدثنا فلان عن الأسود عن النبي صلى الله عليه وسلم", rijal=RijalIndex(_ASWAD))
    assert a.reaches_prophet
    penult = a.narrators[-2]["rijal"]
    assert penult["grade"] == "صحابي" and penult["name"] == "الأسود بن سريع التميمي"


# ── chain/matn boundaries: back-reference, hadith number, ramz, action verbs ───────────────────
def test_back_reference_isnad_ends_the_chain():
    """«… بهذا الإسناد» abbreviates a previously-given chain → the matn follows; «الإسناد» must not
    become a bogus narrator node."""
    names = [n["name"] for n in analyze_isnad("حدثنا قتيبة بهذا الإسناد قال إنما الأعمال").narrators]
    assert names == ["قتيبة"]
    assert not any("الإسناد" in n or "بهذا" in n for n in names)


def test_hadith_number_and_ramz_are_not_narrators():
    """A cross-reference marker («م - ٢٣٤٥») or a lone ramz letter is never a narrator name."""
    names = [n["name"] for n in analyze_isnad("حدثنا قتيبة م - ٢٣٤٥ عن مالك عن نافع").narrators]
    assert names == ["قتيبة", "مالك", "نافع"]


def test_action_verb_opens_matn_but_yuhaddith_keeps_the_chain():
    # «يخطب الناس» opens the narrated scene → the chain ends
    assert [n["name"] for n in analyze_isnad("عن ابن عمر يخطب الناس فقال").narrators] == ["ابن عمر"]
    # «يحدّث عن أبيه» is transmission, not matn → the chain continues
    names = [n["name"] for n in analyze_isnad("سمعت سالما يحدث عن أبيه عن جده").narrators]
    assert "أبيه" in names and "جده" in names


def test_tahwil_seam_is_not_a_link():
    """تحويل (ح) switches routes: the man before the seam and the one after are on different chains,
    so continuity must not read a تلميذ→شيخ link across it (شعبة→محمد is bogus)."""
    a = analyze_isnad("حدثنا أبو بكر عن شعبة ح وحدثنا محمد عن منصور")
    assert a.has_tahwil
    assert next(n for n in a.narrators if n["name"] == "محمد").get("route_start")

    class _G:
        def link_weight(self, student, teacher):
            return 0

    pairs = [(l["from"], l["to"]) for l in continuity(a.narrators, _G())["links"]]
    assert ("شعبة", "محمد") not in pairs        # the ح seam is not a link
    assert ("محمد", "منصور") in pairs           # the route-2 link is intact


def test_prominence_does_not_force_a_sahabi_mid_chain():
    """The prominence prior resolves a bare «جابر» to the prolific Companion — but mid-chain that would be a
    false «صحابي» (there it is usually the تابعي جابر الجعفي). The deep-صحابي demotion sees the FULL candidate
    set (apply_prominence=False) and picks the non-صحابي; the terminal link still gets the Companion."""
    from app.rijal.index import RijalIndex
    idx = RijalIndex([
        {"name": "جابر بن عبد الله الأنصاري", "grade": "صحابي", "source": "تقريب التهذيب (رقم 8609)"},
        {"name": "جابر بن يزيد الجعفي", "grade": "ضعيف", "source": "تقريب التهذيب (رقم 8609)"},
    ])
    idx.set_prominence({"جابر بن عبد الله الأنصاري": 5000, "جابر بن يزيد الجعفي": 500})
    deep = analyze_isnad("حدثنا قتيبة عن سفيان عن جابر عن الشعبي عن مسروق عن النبي صلى الله عليه وسلم قال كذا",
                         rijal=idx)
    assert next(n for n in deep.narrators if n["name"] == "جابر")["rijal"]["grade"] == "ضعيف"
    term = analyze_isnad("حدثنا قتيبة عن أبي الزبير عن جابر عن النبي صلى الله عليه وسلم قال كذا", rijal=idx)
    assert term.narrators[-2]["rijal"]["grade"] == "صحابي"


def test_demotion_sees_homonyms_even_for_a_very_common_ism():
    """The «عبد الله» regression: a bare ism with HUNDREDS of homonyms. Prominence collapses the lookup
    to its prolific bearers — which for «عبد الله» are the all-صحابي ابادلة — so it resolves to صحابي. The
    deep-صحابي demotion must still see the later تابعي «عبد الله» to undo it; that means candidates() must
    NOT be capped to [] for a >40-homonym name here, else the commonest isms regress to a false S."""
    from app.rijal.index import RijalIndex
    _T = "تقريب التهذيب (رقم 8609)"
    entries = [{"name": f"عبد الله بن صحابي{i}", "grade": "صحابي", "source": _T} for i in range(45)]
    entries.append({"name": "عبد الله بن وهب التابعي", "grade": "ثقة", "source": _T})
    idx = RijalIndex(entries)
    idx.set_prominence({**{f"عبد الله بن صحابي{i}": 5000 for i in range(45)},
                        "عبد الله بن وهب التابعي": 100})
    deep = analyze_isnad("حدثنا قتيبة عن سفيان عن عبد الله عن الشعبي عن مسروق "
                         "عن النبي صلى الله عليه وسلم قال كذا", rijal=idx)
    abd = next(n for n in deep.narrators if n["name"] == "عبد الله")
    assert (abd["rijal"] or {}).get("grade") != "صحابي"   # NOT graded صحابي mid-chain


def test_joint_resolver_identifies_a_held_name_from_the_documented_shaykh():
    """End-to-end: a bare mid-chain «سفيان» (الثوري vs عيينة) that the name+company leave ambiguous is
    resolved by the documented network — only الثوري is a تلميذ of الأعمش (the anchored, unique-named
    شيخ below him). Without a network the same chain stays held (the lever is inert when absent)."""
    from app.rijal.index import RijalIndex
    from app.rijal.resolve import DocumentedNetwork, network_key as _k
    _T = "تقريب التهذيب (رقم 8609)"
    idx = RijalIndex([
        {"name": "سفيان بن سعيد الثوري", "grade": "ثقة", "source": _T},
        {"name": "سفيان بن عيينة", "grade": "ثقة", "source": _T},
        {"name": "سليمان بن مهران الأعمش", "grade": "ثقة", "source": _T},
        {"name": "وكيع بن الجراح", "grade": "ثقة", "source": _T},
        {"name": "إبراهيم النخعي", "grade": "ثقة", "source": _T},
    ])
    chain = "حدثنا وكيع عن سفيان عن الأعمش عن إبراهيم النخعي"
    held = next(n for n in analyze_isnad(chain, rijal=idx).narrators if n["name"] == "سفيان")
    assert held["rijal"]["ambiguous"]                        # no network → honestly held «مشترك»
    net = DocumentedNetwork(students={_k("سليمان بن مهران الأعمش"): {_k("سفيان بن سعيد الثوري")}})
    res = next(n for n in analyze_isnad(chain, rijal=idx, network=net).narrators if n["name"] == "سفيان")
    assert res.get("resolved") == "سفيان بن سعيد الثوري"     # identified by the documented شيخ
    assert res["rijal"]["name"] == "سفيان بن سعيد الثوري" and not res["rijal"]["ambiguous"]


@pytest.mark.parametrize("isnad, expect_names, expect_absent", [
    # the screenshot bug: «الزهري وهشام بن عروة عن عروة» fused two men → split into two clean nodes
    ("حدثنا قتيبة عن الزهري وهشام بن عروة عن عروة بن الزبير عن عائشة",
     ["الزهري", "هشام بن عروة", "عروة بن الزبير"], "الزهري وهشام"),
    ("حدثنا حماد عن أيوب وعبيد الله عن نافع", ["أيوب", "عبيد الله", "نافع"], "أيوب وعبيد"),
    ("حدثنا غندر عن سفيان وشعبة عن قتادة", ["سفيان", "شعبة", "قتادة"], "سفيان وشعبة"),
])
def test_waw_splits_co_narrators_into_clean_nodes(isnad, expect_names, expect_absent):
    # split_conarrators=True is the graph-build path (build_graph); the verdict path leaves them fused
    names = [n["name"] for n in analyze_isnad(isnad, split_conarrators=True).narrators]
    for nm in expect_names:
        assert nm in names
    assert expect_absent not in " | ".join(names)   # the fused «A وB» node is gone
    # …and in the DEFAULT (verdict) path the node is left fused (no A/S regression in the audit)
    assert expect_absent in " | ".join(n["name"] for n in analyze_isnad(isnad).narrators)


@pytest.mark.parametrize("isnad, keep", [
    ("حدثنا الأعمش عن أبي وائل عن عبد الله", "أبي وائل"),        # waw INSIDE a kunya — not a split
    ("حدثنا أحمد عن عبد الله بن وهب عن مالك", "عبد الله بن وهب"),  # waw in a nasab (بن وهب)
    ("حدثنا وكيع عن سفيان عن منصور", "وكيع"),                    # a name that simply starts with waw
    ("حدثنا وهيب عن أيوب عن نافع", "وهيب"),
])
def test_waw_does_not_split_real_names_or_kunyas(isnad, keep):
    assert keep in [n["name"] for n in analyze_isnad(isnad, split_conarrators=True).narrators]


def test_waw_split_marks_a_route_seam_no_false_link():
    """The second co-narrator begins a new route, so continuity must not read a تلميذ→شيخ link from the
    first to the second (الزهري↛هشام)."""
    a = analyze_isnad("حدثنا قتيبة عن الزهري وهشام بن عروة عن عروة بن الزبير", split_conarrators=True)
    assert next(n for n in a.narrators if n["name"] == "هشام بن عروة").get("route_start")


def test_verify_isnad_splits_co_narrators(client):
    """The user-facing verdict must SPLIT a fused dual — «قتيبة بن سعيد وعبد الله بن مسلمة» and «عروة
    وعمرة» are two men each — else a sound chain (أبو داود 2468) is held «يُتوقَّف» on a «غير معروف»
    fused node. The router passes split_conarrators=True (the aggregate audit keeps it off)."""
    chain = ("حدثنا قتيبة بن سعيد وعبد الله بن مسلمة قالا حدثنا الليث عن ابن شهاب "
             "عن عروة وعمرة عن عائشة عن النبي صلى الله عليه وسلم")
    names = [n["name"] for n in client.get("/verify-isnad", params={"isnad": chain}).json()["analysis"]["narrators"]]
    assert "عبد الله بن مسلمة" in names and "عمرة" in names
    assert not any("وعبد الله" in n or "وعمرة" in n for n in names)   # no fused dual node

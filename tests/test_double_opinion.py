"""Double-opinion rijal: keep both critics' verdicts and expose divergence (P1.2)."""

from __future__ import annotations

from app.qa.isnad import analyze_isnad
from app.rijal.grades import RANKS
from app.rijal.index import RijalIndex
from scripts.build_rijal import _add_opinion, merge_source


def test_both_opinions_kept_when_critics_differ():
    primary = [{"name": "فلان بن علان الكوفي", "grade": "ثقة", "source": "تقريب التهذيب (رقم 1)"}]
    for r in primary:                                  # the authority's own opinion
        _add_opinion(r, r["source"], r["grade"])
    secondary = [{"name": "فلان بن علان الكوفي", "grade": "صدوق", "source": "الكاشف (رقم 2)"}]

    merged, added, upgraded = merge_source(primary, secondary)
    ops = merged[0]["opinions"]
    assert {o["source"]: o["grade"] for o in ops} == {"تقريب التهذيب": "ثقة", "الكاشف": "صدوق"}
    # the verdict driver stays the authority's grade; it round-trips through the index
    d = RijalIndex(merged).lookup("فلان بن علان الكوفي").to_dict()
    assert d["grade"] == "ثقة" and len(d["opinions"]) == 2


def test_no_divergence_when_critics_agree():
    primary = [{"name": "ثقة بن ثقة الثقفي", "grade": "ثقة", "source": "تقريب التهذيب (رقم 9)"}]
    for r in primary:
        _add_opinion(r, r["source"], r["grade"])
    merged, *_ = merge_source(primary, [
        {"name": "ثقة بن ثقة الثقفي", "grade": "ثقة حافظ", "source": "الكاشف (رقم 9)"}])
    # both classify to ثقة → a single distinct opinion (UI shows nothing to flag)
    assert {o["grade"] for o in merged[0]["opinions"]} == {"ثقة"}


def test_isnad_verdict_takes_the_weakest_opinion_for_a_disputed_narrator():
    # «الرأي الثاني» ADJUDICATED: a man called ثقة by تقريب but ضعيف by الكاشف drags the chain down to
    # his WEAKEST opinion (أنزل القولين), is listed as مختلف فيه, and is flagged on his card — while an
    # agreeing narrator is untouched.
    rij = RijalIndex([
        {"name": "محمد بن بشار البصري", "grade": "ثقة",
         "opinions": [{"source": "تقريب التهذيب", "grade": "ثقة"},
                      {"source": "الكاشف", "grade": "ضعيف"}]},
        {"name": "يحيى بن سعيد القطان", "grade": "ثقة",
         "opinions": [{"source": "تقريب التهذيب", "grade": "ثقة"}]},
    ])
    a = analyze_isnad("حدثنا محمد بن بشار البصري، عن يحيى بن سعيد القطان", rijal=rij).to_dict()
    asm = a["rijal_assessment"]
    assert any(d["name"].startswith("محمد بن بشار") for d in asm["disputed"])     # listed مختلف فيه
    assert asm["weakest_rank"] == RANKS["ضعيف"]                                   # graded by أنزل القولين
    assert any("اختُلف فيه" in n for n in a["notes"])                             # a note explains it
    disputed = [r["rijal"] for r in a["narrators"] if r.get("rijal") and r["rijal"].get("disputed")]
    assert disputed and all(d["disputed"] for d in disputed)                       # card flags him
    # the agreeing narrator is NOT disputed
    agree = [r["rijal"] for r in a["narrators"]
             if r.get("rijal") and r["rijal"]["name"].startswith("يحيى")]
    assert agree and not agree[0]["disputed"]

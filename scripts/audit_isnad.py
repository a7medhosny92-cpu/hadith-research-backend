"""Audit the isnad analysis for likely rijal-matching errors across the whole corpus.

A *heuristic* finder, not a verdict — every hit is for a human to verify. It surfaces
the patterns that betray a wrong narrator match (the kind that flips a sound chain to
«ضعيف جدًا»):

  P  the Prophet ﷺ graded as a narrator                     (should never happen)
  S  «صحابي» on a non-terminal narrator                      (a Companion belongs at the
                                                              chain's end, next to the Prophet)
  W  a fully-named narrator (≥3 tokens) graded متروك/متّهم/كذاب  (usually a homonym mismatch,
                                                              e.g. عثمان بن أبي شيبة ↦ متروك)
  A  an ambiguous match (مشترك)                              (two equally-good namesakes)

It uses the SAME context disambiguation as the verdict (تمييز المهمل), so it reports what
a reader actually sees. It writes a report to ``{DATA_DIR}/audit.json`` for the in-app
«التدقيق» tab, and prints a summary.

Run after building the index + rijal (+ graph, for the context tier):

    python -m scripts.audit_isnad                # scan all, write the report, print a summary
    python -m scripts.audit_isnad --limit 2000   # scan only the first N hadith (faster)
    python -m scripts.audit_isnad --cap 800      # keep up to N cases per category in the report
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from collections import Counter

from app.config import get_settings
from app.qa.isnad import analyze_isnad
from app.rijal.muhmal import load_map as load_muhmal_map
from app.rijal.resolve import load_network
from app.rijal import RijalIndex, load_entries
from app.rijal.canon import Canonicalizer
from app.rijal.graph import NarratorGraph
from app.rijal.index import _clean_tokens

_WEAK = {"متروك", "متهم", "كذاب", "وضاع"}          # ranks 0-1: a strong name here is suspect
_TWO_LAST = 2                                       # a صحابي should sit in the last 2 links
_LABEL = {
    "P": "الحكم على النبيّ ﷺ كراوٍ",
    "W": "اسمٌ كاملٌ حُكم له بالترك/الكذب (خلطٌ محتمل)",
    "S": "«صحابي» في غير آخر السند",
    "A": "مطابقةٌ مشتركة (مُلتبسة)",
}


def _build_canon(settings, rijal: RijalIndex) -> Canonicalizer:
    path = settings.narrator_graph_path
    if not path.exists():
        return Canonicalizer(rijal)
    graph = NarratorGraph(path)
    if not graph.count():
        return Canonicalizer(rijal)
    rijal.set_prominence(graph.frequencies())   # the prominence prior (corpus narration frequency)
    profiles = {
        name: set().union(*(_clean_tokens(nb) for nb in neigh)) if neigh else set()
        for name, neigh in graph.adjacency().items()
    }
    return Canonicalizer(rijal, associations=profiles)


def _name_compatible(cited: str, matched: str) -> bool:
    """True if the cited surface is CONSISTENT with the man the grade was read from — every
    content token of the citation appears in his full name.

    A late «الحسن بن علي بن زياد» (an obscure شيخ absent from the rijal) carries «زياد», absent
    from the Companion «الحسن بن علي بن أبي طالب» onto whose bare leading run «الحسن بن علي» it
    collapsed: a different, more-specific man, so the «صحابي» (or «متروك») grade is not his —
    don't flag it. A deeper-ancestor citation «عبد الله بن عمر بن الخطاب» stays compatible (الخطاب
    IS in his name), as does a kunya citation of the same man."""
    cited_toks = _clean_tokens(cited)
    return not cited_toks or cited_toks <= _clean_tokens(matched)


def _flag_chain(narrators: list[dict]) -> list[tuple[str, str]]:
    """Return (code, detail) anomalies for one analysed chain."""
    out: list[tuple[str, str]] = []
    n = len(narrators)
    for i, nar in enumerate(narrators):
        rij = nar.get("rijal")
        name = nar.get("name", "")
        if nar.get("is_prophet"):
            if rij:
                out.append(("P", f"الحكم على «{name}» (وهو مصدر الحديث) بـ {rij.get('grade')}"))
            continue
        if not rij:
            continue
        grade = rij.get("grade") or ""
        verdict = rij.get("verdict") or ""
        # A confident grade = either a single match, or tied candidates that agree. An ambiguous
        # match with disagreeing candidates (أبو إسحاق ↦ سعد الصحابي vs السبيعي الثقة; عثمان بن
        # أبي شيبة ↦ ثقة vs متروك) is undecided — it belongs in «مشترك», not a «صحابي»/«متروك» flag.
        certain = (not rij.get("ambiguous")) or rij.get("grade_agreed")
        # …and the cited name must be CONSISTENT with the matched man — else a more-specific
        # namesake (الحسن بن علي بن زياد) wrongly wears a short Companion's/متروك's grade.
        compatible = _name_compatible(name, rij.get("name") or "")
        # صحابيٌّ عن صحابيّ is legitimate at ANY depth — a younger Companion narrating from an older
        # one («ابن عباس عن عمر»، «أنس عن أبي بكر») is sound, not a misplaced صحابي. So extend the
        # last-two-links exception: a صحابي whose own شيخ (the NEXT link) is also a صحابي isn't flagged.
        nxt = narrators[i + 1] if i + 1 < n else None
        shaykh_sahabi = bool(nxt and (nxt.get("rijal") or {}).get("grade") == "صحابي")
        if grade == "صحابي" and i < n - _TWO_LAST and certain and compatible and not shaykh_sahabi:
            out.append(("S", f"«{name}» (الحلقة {i+1}/{n}) حُكم له «صحابي» وموضعه ليس آخر السند"))
        if any(w in verdict for w in _WEAK) and len(name.split()) >= 3 and certain and compatible:
            out.append(("W", f"«{name}» (اسمٌ كامل) حُكم له «{verdict}» — يُحتمل خلطٌ باسمٍ مشابه"))
        if rij.get("ambiguous"):
            alts = "، ".join(rij.get("alternatives") or [])
            out.append(("A", f"«{name}» مشترك بين: {rij.get('name')} / {alts}"))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit isnad rijal matching for likely errors.")
    ap.add_argument("--limit", type=int, default=None, help="scan only the first N hadith")
    ap.add_argument("--cap", type=int, default=500, help="cases to keep per category in the report")
    args = ap.parse_args()

    settings = get_settings()
    rijal = RijalIndex(load_entries(settings.rijal_file))
    canon = _build_canon(settings, rijal)
    muhmal = load_muhmal_map(settings.data_dir / "muhmal.json")   # تمييز المهمل (from build_graph)
    network = load_network(settings.documented_network_path)      # the documented شيخ/تلميذ resolver
    print(f"rijal entries: {rijal.count()}   index: {settings.index_path}   "
          f"مهمل: {len(muhmal)}   شبكة موثّقة: {'yes' if network else 'no'}")
    con = sqlite3.connect(str(settings.index_path))
    sql = "SELECT rowid, collection, number, isnad FROM hadith WHERE trim(isnad) <> ''"
    if args.limit:
        sql += f" LIMIT {args.limit}"

    rows = con.execute(sql).fetchall()
    total = len(rows)
    print(f"scanning {total} chains (this can take a few minutes on a full rijal)…", flush=True)

    counts: Counter[str] = Counter()
    cases: dict[str, list[dict]] = {"P": [], "S": [], "W": [], "A": []}
    a_names: Counter[str] = Counter()          # «مشترك» ranked view: cited name → how often it's ambiguous
    a_cands: dict[str, str] = {}               # …and its candidate list (the «مشترك بين: …» tail), once
    _NAME = re.compile(r"«([^»]+)»")
    scanned = 0
    for rid, coll, num, isnad in rows:
        scanned += 1
        if scanned % 500 == 0:
            print(f"  … {scanned}/{total}", end="\r", flush=True)
        a = analyze_isnad(isnad, rijal=rijal, canon=canon, muhmal=muhmal, network=network)
        for code, detail in _flag_chain(a.narrators):
            counts[code] += 1
            if code == "A":
                m = _NAME.search(detail)
                if m:
                    a_names[m.group(1)] += 1
                    a_cands.setdefault(m.group(1), detail.split("مشترك بين:", 1)[-1].strip())
            if len(cases[code]) < args.cap:
                cases[code].append({"id": rid, "collection": coll, "number": num, "detail": detail})
    con.close()

    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "rijal_entries": rijal.count(),
        "scanned": scanned,
        "counts": {c: counts[c] for c in ("P", "W", "S", "A")},
        "labels": _LABEL,
        "cases": cases,
        # the «مشترك» names ranked by how often they are ambiguous — the review/«قارن» list (a high
        # count on a SPECIFIC name betrays an over-match bug; a famous one held among many = genuine).
        "a_ranked": [{"name": nm, "count": ct, "candidates": a_cands.get(nm, "")}
                     for nm, ct in a_names.most_common(400)],
    }
    out_path = settings.data_dir / "audit.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    print(f"\nscanned {scanned} chains → {out_path}")
    for code in ("P", "W", "S", "A"):
        print(f"  [{code}] {_LABEL[code]}: {counts[code]}")


if __name__ == "__main__":
    main()

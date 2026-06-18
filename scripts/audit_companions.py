"""Audit how many COMPANIONS (صحابة) actually appear as narrators in the chains — read-only, fast.

The رجال base holds thousands of صحابي because الإصابة is a Companions-ONLY dictionary (+5.5k men), but
only a FRACTION of those Companions ever transmitted a hadith that survives in the corpus. This answers the
real question — «how many Companions are actually IN the chains?» — by reading the narrator network
(``narrators.db``: every man cited in an isnād + his corpus ``freq``) and the base, and reporting:

  • DISTINCT chain narrators that resolve to a صحابي grade            (how many Companions appear at all)
      split by source: in تقريب/الكاشف (the active transmitters) vs only-الإصابة (obscure coverage)
  • the same weighted by CHAIN POSITION (freq) — what share of all narration is by Companions
  • TERMINAL Companions — those who narrate DIRECTLY from the Prophet ﷺ («الصحابي عن النبي ﷺ»), i.e. the
      students of the single Prophet node; the classical «الصحابة الرواة»
  • the top transmitters (المكثرون) by frequency — أبو هريرة, ابن عمر, أنس …

«Companion» here means the base resolves the name to category «صحابي» — confidently, or (when homonyms tie)
only if every tied candidate is a صحابي (grade agreed). An uncovered or non-صحابي node is not counted.

    python -m scripts.audit_companions          # summary + write data/companions.json
    python -m scripts.audit_companions --cap 60 # more examples kept
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time

from app.config import get_settings
from app.rijal import RijalIndex, load_entries
from app.rijal.graph import is_prophet
from app.rijal.grades import classify
from app.rijal.index import from_companion_dictionary, from_coverage_source


def _companion(rijal: RijalIndex, name: str):
    """The base entry if ``name`` resolves UNIVOCALLY to a Companion, else ``None``.

    A node counts as a Companion only when EVERY real homonym is a صحابي — read from
    ``candidates(apply_prominence=False)``, the true homonym set, NOT from ``lookup`` (which the
    prominence prior would resolve to a صحابي bearer even for a bare, ambiguous «عبد الله» with
    hundreds of mixed namesakes, or «محمد بن جعفر» = 7 non-صحابي + غندر). So a bare/ambiguous node is
    NOT miscounted as a Companion; only a name whose homonyms agree on صحابي (or a unique صحابي) is.

    Coverage-only namesakes (الإصابة/الثقات) are dropped first when a real (non-coverage) man is present
    — mirroring the matcher's ``_prefer_non_coverage`` — so the famous «أبو هريرة» (الدوسي, in تقريب) is
    not excluded just because obscure الثقات men share his kunya. (When ALL are coverage — an obscure
    الإصابة-only Companion — they are kept, so the terminal Companions still count.)"""
    cands = rijal.candidates(name, apply_prominence=False, max_results=None)
    if not cands:
        return None
    real = [c for c in cands if not from_coverage_source(c)]
    pool = real or cands
    return pool[0] if all(c.category == "صحابي" for c in pool) else None


def audit(rijal: RijalIndex, nodes: list[tuple[int, str, int]],
          prophet_ids: set[int], terminal_ids: set[int]) -> dict:
    """Classify every chain narrator node ``(id, name, freq)`` as a Companion or not, and tally the
    DISTINCT Companions, their chain POSITIONS (freq), how many are only-الإصابة coverage, and the
    subset that narrate DIRECTLY from the Prophet (``terminal_ids`` = students of the Prophet node)."""
    distinct = coverage_only = positions = term_distinct = term_positions = 0
    terminal_total = 0
    total_positions = sum(f for _, _, f in nodes)
    top: list[tuple[str, int, bool]] = []   # (canonical name, freq, only-coverage)
    unrecognized: list[tuple[str, int]] = []  # terminal nodes (narrate «عن النبي ﷺ») NOT graded صحابي
    for nid, name, freq in nodes:
        if nid in prophet_ids:
            continue
        is_term = nid in terminal_ids
        terminal_total += is_term
        entry = _companion(rijal, name)
        if entry is None:
            if is_term:                      # narrates from the Prophet but unidentified — a missed
                unrecognized.append((name, freq))   # Companion (bare/variant) or a تابعي mursal
            continue
        distinct += 1
        positions += freq
        cov = from_companion_dictionary(entry)
        coverage_only += cov
        top.append((entry.name, freq, bool(cov)))
        if is_term:
            term_distinct += 1
            term_positions += freq
    top.sort(key=lambda x: -x[1])
    unrecognized.sort(key=lambda x: -x[1])
    return {
        "distinct": distinct,
        "in_taqrib_kashif": distinct - coverage_only,
        "coverage_only": coverage_only,
        "positions": positions,
        "total_positions": total_positions,
        "terminal_total": terminal_total,
        "terminal_distinct": term_distinct,
        "terminal_positions": term_positions,
        "top": top,
        "unrecognized": unrecognized,
    }


def _pct(x: int, tot: int) -> str:
    return f"{100 * x / tot:.1f}%" if tot else "—"


def main() -> None:
    ap = argparse.ArgumentParser(description="Count the Companions that actually appear in the chains.")
    ap.add_argument("--cap", type=int, default=40, help="examples kept in the JSON report")
    args = ap.parse_args()
    settings = get_settings()

    graph_path = settings.narrator_graph_path
    if not graph_path.exists():
        raise SystemExit(f"no narrator graph at {graph_path} — run build_graph first")
    con = sqlite3.connect(str(graph_path))
    nodes = [(nid, name, freq) for nid, name, freq in
             con.execute("SELECT id, name, freq FROM narrator") if name]
    prophet_ids = {nid for nid, name, _ in nodes if is_prophet(name)}
    # the students of the Prophet node = the narrators who narrate directly «عن النبي ﷺ» (terminal Companions)
    terminal_ids: set[int] = set()
    if prophet_ids:
        terminal_ids = {s for (s,) in con.execute(
            "SELECT DISTINCT student FROM link WHERE teacher IN (%s)" %
            ",".join("?" * len(prophet_ids)), tuple(prophet_ids)
        )}
    con.close()

    records = load_entries(settings.rijal_file)
    rijal = RijalIndex(records)
    rijal.set_prominence({name: freq for _, name, freq in nodes})   # mirror verdict-time disambiguation
    # the base stores a verdict TEXT («grade»); the «صحابي» CATEGORY is what RijalIndex derives via
    # classify() — so count Companions the same way, not by a (absent) «category» key on the raw dict.
    base_sahaba = sum(1 for r in records if classify(r.get("grade") or "")[0] == "صحابي")
    print(f"chain nodes (narrators.db): {len(nodes)}   rijal entries: {len(records)}   "
          f"(of which صحابي in the base: {base_sahaba})")

    res = audit(rijal, nodes, prophet_ids, terminal_ids)
    tot = res["total_positions"]
    print(f"\n— Companions DISTINCT in the chains —")
    print(f"  resolve to صحابي          : {res['distinct']:>6}   "
          f"(of {base_sahaba} صحابي in the base = {_pct(res['distinct'], base_sahaba)} of them actually narrate)")
    print(f"    · in تقريب/الكاشف       : {res['in_taqrib_kashif']:>6}   (the active transmitters)")
    print(f"    · only-الإصابة coverage : {res['coverage_only']:>6}   (obscure Companions, terminal-only)")
    print(f"\n— Companions by CHAIN POSITION (freq-weighted) —")
    print(f"  صحابي positions           : {res['positions']:>7}   "
          f"({_pct(res['positions'], tot)} of all {tot} chain positions)")
    term_total, term_ok = res["terminal_total"], res["terminal_distinct"]
    print(f"\n— TERMINAL nodes (narrate directly «عن النبي ﷺ») —")
    print(f"  total                     : {term_total:>6}   (every node that narrates from the Prophet)")
    print(f"  recognized as صحابي       : {term_ok:>6}   ← the classical «الصحابة الرواة» ({_pct(term_ok, term_total)})")
    print(f"  NOT recognized            : {term_total - term_ok:>6}   ← missed Companions (bare/variant) or تابعون mursal")
    print(f"  positions (recognized)    : {res['terminal_positions']:>7}   ({_pct(res['terminal_positions'], tot)})")
    print(f"\n— top transmitters (المكثرون, by frequency) —")
    for name, freq, _cov in res["top"][:20]:
        print(f"   {freq:>6}×  {name}")
    print(f"\n— top UNRECOGNIZED terminals (a missed Companion, or a تابعي narrating mursal) —")
    for name, freq in res["unrecognized"][:20]:
        print(f"   {freq:>6}×  {name}")

    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "chain_nodes": len(nodes),
        "rijal_entries": len(records),
        "base_sahaba": base_sahaba,
        **{k: v for k, v in res.items() if k not in ("top", "unrecognized")},
        "top": [{"name": nm, "freq": f, "coverage_only": c} for nm, f, c in res["top"][: args.cap]],
        "unrecognized": [{"name": nm, "freq": f} for nm, f in res["unrecognized"][: args.cap]],
    }
    out = settings.data_dir / "companions.json"
    out.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()

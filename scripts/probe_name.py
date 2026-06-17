"""Probe how the رجال matcher resolves a cited NAME — read-only, no rebuild.

For each name it prints what ``RijalIndex.lookup`` resolves to (entry · grade · محسوم/مشترك ·
alternatives) and the FULL ``candidates`` homonym set (each with its grade, death-year and whether
it is an add-only coverage entry الإصابة/الثقات). Two uses:

* **confirm a shuhra** before adding it to ``index._SHUHRA`` — «ابن أبي ذئب» → which exact canonical
  name does the base carry, and does it resolve uniquely?
* **diagnose a mis-resolution** — why does a bare «الشعبي» (a تابعي ثقة) grade «صحابي» mid-chain? The
  candidate dump shows the صحابي homonym that wins and whether a coverage entry is shadowing him.

    python -m scripts.probe_name "ابن جريج" "الشعبي" "قيس بن أبي حازم"
    python -m scripts.probe_name            # the curated shuhra + S-class shortlist

Reads only ``data/rijal.jsonl`` (+ the graph for the prominence prior, if built) — the SAME live
matcher the audit/verify use, so what it prints is what a chain sees. Touches nothing.
"""

from __future__ import annotations

import argparse

from app.config import get_settings
from app.rijal import RijalIndex, load_entries
from app.rijal.index import from_coverage_source
from app.rijal.graph import NarratorGraph

# Default shortlist: the shuhra-by-ancestor candidates to confirm, then the S-class تابعون the audit
# flags «صحابي» mid-chain (to diagnose). Override by passing names on the command line.
_DEFAULTS = [
    "ابن جريج", "ابن أبي ذئب", "ابن أبي مليكة", "ابن جدعان", "ابن أبي ليلى", "ابن المسيب",
    "الشعبي", "قيس بن أبي حازم", "عبيد الله بن عبد الله بن عتبة", "نافع بن أبي نافع",
]


def describe(rijal: RijalIndex, name: str, *, top: int = 25) -> list[str]:
    """The resolution report for one cited name — a list of printable lines."""
    out = [f"=== {name} ==="]
    m = rijal.lookup(name)
    if m is None:
        out.append("  lookup → (لا مطابقة)")
    else:
        verdict = "مشترك" if m.ambiguous else "محسوم"
        agreed = " · grade_agreed" if m.ambiguous and m.grade_agreed else ""
        out.append(f"  lookup → {m.entry.name}  ·  {m.entry.category or '—'}  ·  {verdict}{agreed}")
        if m.alternatives:
            out.append(f"    alternatives: {'، '.join(m.alternatives)}")
    cands = rijal.candidates(name, max_results=None, apply_prominence=False)
    out.append(f"  candidates ({len(cands)}):")
    for e in cands[:top]:
        dy = f" · ت{e.death_year}" if e.death_year else ""
        cov = " · [coverage]" if from_coverage_source(e) else ""
        out.append(f"    · {e.name}  —  {e.category or '—'}{dy}{cov}")
    if len(cands) > top:
        out.append(f"    … (+{len(cands) - top} أخرى)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Probe how the رجال matcher resolves a name (read-only)")
    ap.add_argument("names", nargs="*", help="cited names to probe (default: the curated shortlist)")
    ap.add_argument("--top", type=int, default=25, help="max candidates to list per name")
    args = ap.parse_args()

    settings = get_settings()
    entries = load_entries(settings.rijal_file)
    rijal = RijalIndex(entries)
    graph_path = settings.narrator_graph_path
    if graph_path.exists():
        graph = NarratorGraph(graph_path)
        if graph.count():
            rijal.set_prominence(graph.frequencies())   # the prominence prior, like the audit
            print(f"(prominence prior from {graph.count()} graph nodes)")
    print(f"rijal entries: {len(entries)}")

    for name in (args.names or _DEFAULTS):
        print()
        print("\n".join(describe(rijal, name, top=args.top)))


if __name__ == "__main__":
    main()

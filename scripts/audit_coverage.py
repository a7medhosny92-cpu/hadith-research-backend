"""Audit COVERAGE — does the رجال base grade every narrator who actually appears in the chains?

Read-only. Reads the narrator NETWORK (``narrators.db`` — every man cited in an isnād, with his corpus
narration ``freq``) and matches each node against the رجال base, classifying:

  identified   the base resolves him to ONE graded man          (covered & resolved)
  ambiguous    the base has the name but ≥2 homonyms tie         (covered, «مشترك»)
  uncovered    no match — the base does not grade this man       (the coverage GAP)

Reported both per DISTINCT narrator and weighted by FREQUENCY (chain positions), plus the top uncovered
nodes by frequency — the gaps that matter most. «Coverage» = identified + ambiguous (the man IS in the
base, possibly among homonyms); uncovered is the honest gap (obscure men, name-variant forms, or a dirty
chain node). The base is solid only as far as it covers the chains.

    python -m scripts.audit_coverage            # summary + write data/coverage.json
    python -m scripts.audit_coverage --cap 120  # more examples kept
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter

from app.config import get_settings
from app.rijal import RijalIndex, load_entries


def audit(rijal: RijalIndex, nodes: list[tuple[str, int]]) -> dict:
    """Classify every chain narrator node (name, freq) against the base."""
    by_node: Counter = Counter()
    by_pos: Counter = Counter()
    uncovered: list[tuple[str, int]] = []
    ambiguous: list[tuple[str, int]] = []
    for name, freq in nodes:
        match = rijal.lookup(name)
        if match is None:
            cls = "uncovered"
            uncovered.append((name, freq))
        elif match.ambiguous:
            cls = "ambiguous"
            ambiguous.append((name, freq))
        else:
            cls = "identified"
        by_node[cls] += 1
        by_pos[cls] += freq
    uncovered.sort(key=lambda x: -x[1])
    ambiguous.sort(key=lambda x: -x[1])
    return {
        "nodes": len(nodes),
        "positions": sum(f for _, f in nodes),
        "by_node": dict(by_node),
        "by_pos": dict(by_pos),
        "uncovered_top": uncovered,
        "ambiguous_top": ambiguous,
    }


def _pct(x: int, tot: int) -> str:
    return f"{100 * x / tot:.1f}%" if tot else "—"


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit how much of the chain narrators the رجال base covers.")
    ap.add_argument("--cap", type=int, default=80, help="examples kept per list")
    args = ap.parse_args()
    settings = get_settings()

    graph_path = settings.narrator_graph_path
    if not graph_path.exists():
        raise SystemExit(f"no narrator graph at {graph_path} — run build_graph first")
    con = sqlite3.connect(str(graph_path))
    nodes = [(name, freq) for name, freq in con.execute("SELECT name, freq FROM narrator") if name]
    con.close()

    records = load_entries(settings.rijal_file)
    rijal = RijalIndex(records)
    rijal.set_prominence({name: freq for name, freq in nodes})   # mirror verdict-time disambiguation
    print(f"chain narrators (graph nodes): {len(nodes)}   rijal entries: {len(records)}")

    res = audit(rijal, nodes)
    n, p = res["nodes"], res["positions"]
    print(f"\n— COVERAGE by DISTINCT narrator ({n}) —")
    for cls in ("identified", "ambiguous", "uncovered"):
        c = res["by_node"].get(cls, 0)
        print(f"  {cls:11} {c:>6}  ({_pct(c, n)})")
    print(f"\n— COVERAGE by CHAIN POSITION (freq-weighted, {p}) —")
    for cls in ("identified", "ambiguous", "uncovered"):
        c = res["by_pos"].get(cls, 0)
        print(f"  {cls:11} {c:>7}  ({_pct(c, p)})")

    cov_n = res["by_node"].get("identified", 0) + res["by_node"].get("ambiguous", 0)
    cov_p = res["by_pos"].get("identified", 0) + res["by_pos"].get("ambiguous", 0)
    print(f"\n→ the base COVERS {_pct(cov_n, n)} of distinct chain narrators "
          f"and {_pct(cov_p, p)} of chain positions; uncovered = {res['by_node'].get('uncovered', 0)} men.")
    print("\n— top UNCOVERED (by frequency — the gaps that matter most) —")
    for name, freq in res["uncovered_top"][:20]:
        print(f"   {freq:>5}×  {name}")

    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "nodes": n, "positions": p,
        "by_node": res["by_node"], "by_pos": res["by_pos"],
        "uncovered_top": [{"name": nm, "freq": f} for nm, f in res["uncovered_top"][: args.cap]],
        "ambiguous_top": [{"name": nm, "freq": f} for nm, f in res["ambiguous_top"][: args.cap]],
    }
    out = settings.data_dir / "coverage.json"
    out.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()

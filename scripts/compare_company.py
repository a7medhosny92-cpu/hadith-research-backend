"""Compare the شيوخ/تلاميذ company of two (or more) homonyms — read-only.

The disambiguation question for a «مشترك» pair (e.g. سفيان ↦ ابن عيينة / الثوري) is:
**does the chain company actually distinguish them?** If their تلاميذ/شيوخ are mostly
DISJOINT, then context (`canon._pick`) can split them — the ambiguity is ②a (resolvable,
a coverage/relaxation target). If they SHARE most of their company, no algorithm can split
them from the chain alone — that is ②b, the honest floor (held «مشترك» is correct).

This tool just READS `data/narrators.db` (built by ``scripts.build_graph``) and prints, for
each name, its top شيوخ + تلاميذ with counts, then the pairwise overlap (Jaccard + the
distinctive, non-shared company of each side) and a verdict. It never writes anything.

    python -m scripts.compare_company "سفيان بن سعيد الثوري" "سفيان بن عيينة"
    python -m scripts.compare_company "سفيان بن سعيد الثوري" "سفيان بن عيينة" --top 25
"""

from __future__ import annotations

import argparse

from app.config import get_settings
from app.rijal.graph import NarratorGraph


def _names(rows: list[dict]) -> set[str]:
    return {r["name"] for r in rows}


def _fmt(rows: list[dict], top: int) -> str:
    if not rows:
        return "      (none)"
    shown = rows[:top]
    body = "\n".join(f"      {r['count']:>4}× {r['name']}" for r in shown)
    if len(rows) > top:
        body += f"\n      … (+{len(rows) - top} more)"
    return body


def _overlap(a: set[str], b: set[str]) -> tuple[float, set[str], set[str], set[str]]:
    shared = a & b
    union = a | b
    jac = len(shared) / len(union) if union else 0.0
    return jac, shared, a - b, b - a


def main() -> None:
    ap = argparse.ArgumentParser(description="compare the chain company of homonyms (read-only)")
    ap.add_argument("names", nargs="+", help="two or more canonical narrator names to compare")
    ap.add_argument("--top", type=int, default=20, help="how many شيوخ/تلاميذ to print each (default 20)")
    args = ap.parse_args()

    settings = get_settings()
    path = settings.narrator_graph_path
    if not path.exists():
        raise SystemExit(f"narrator graph not found at {path} — run `python -m scripts.build_graph` first")
    graph = NarratorGraph(path)
    freq = graph.frequencies()

    profiles: list[dict] = []
    for name in args.names:
        node = graph.resolve(name)
        teachers = graph.teachers(name)        # all (no cap) — most frequent first
        students = graph.students(name)
        resolved = node.name if node else None
        profiles.append({"asked": name, "resolved": resolved,
                         "freq": freq.get(resolved, 0) if resolved else 0,
                         "teachers": teachers, "students": students})
        print("─" * 72)
        print(f"  {name}")
        if resolved is None:
            print("    ✗ not found in the graph")
            continue
        if resolved != name:
            print(f"    (resolved → {resolved})")
        print(f"    ناريشن (freq) = {freq.get(resolved, 0)}")
        print(f"    شيوخ ({len(teachers)}):")
        print(_fmt(teachers, args.top))
        print(f"    تلاميذ ({len(students)}):")
        print(_fmt(students, args.top))

    found = [p for p in profiles if p["resolved"] is not None]
    if len(found) < 2:
        print("\n  (need at least two resolvable names to compare)")
        return

    print("\n" + "═" * 72)
    print("  OVERLAP — does the company distinguish them?")
    for i in range(len(found)):
        for j in range(i + 1, len(found)):
            a, b = found[i], found[j]
            for label, key in (("تلاميذ", "students"), ("شيوخ", "teachers")):
                jac, shared, only_a, only_b = _overlap(_names(a[key]), _names(b[key]))
                print(f"\n  «{a['resolved']}»  vs  «{b['resolved']}»  — {label}")
                print(f"    Jaccard = {jac:.2f}   (shared {len(shared)} · "
                      f"only-A {len(only_a)} · only-B {len(only_b)})")
                if only_a:
                    print(f"    distinctive to A: {'، '.join(sorted(only_a)[:12])}")
                if only_b:
                    print(f"    distinctive to B: {'، '.join(sorted(only_b)[:12])}")
            # verdict on تلاميذ (the lever canon._pick reads when picking among تلاميذ→شيوخ)
            jac_t, *_ = _overlap(_names(a["students"]), _names(b["students"]))
            jac_s, *_ = _overlap(_names(a["teachers"]), _names(b["teachers"]))
            if max(jac_t, jac_s) < 0.20:
                verdict = "DISTINGUISHABLE — company is mostly disjoint → ②a (context CAN split them)"
            elif min(jac_t, jac_s) > 0.50:
                verdict = "SHARED — company largely overlaps → ②b (honest floor, held «مشترك» is right)"
            else:
                verdict = "MIXED — partially separable; the distinctive company above is the lever"
            print(f"    ⇒ {verdict}")


if __name__ == "__main__":
    main()

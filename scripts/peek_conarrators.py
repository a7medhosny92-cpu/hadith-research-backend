"""Verify the «two chains» class — read-only, no rebuild.

A waw co-narrator «شعبة عن عبد الله بن أبي السفر **وإسماعيل** عن الشعبي» (and a تحويل ح) is really TWO
parallel routes that share a شيخ: each co-narrator must be identified by ITS شيخ, not held «مجهول». This
scans every chain with ``split_conarrators=True`` (the /verify-isnad path — the AUDIT fuses co-narrators,
so it can't see this class) and reports each route-start narrator's resolution:

  * **resolved** — a قاعدة/شبكة/رفقة fixed it from its شيخ (the win),
  * **held** — still «مشترك»/«غير معروف» (a candidate for a new قاعدة or more coverage),
  * **graded** — resolved to a single man directly.

So we SEE all the «two chains» cases and how many the شيخ-link now resolves. The top HELD route-start names
are the review queue (add a قاعدة, or confirm honest homonymy). Reads only data/ — touches nothing.

    python -m scripts.peek_conarrators            # full corpus
    python -m scripts.peek_conarrators --limit 5000 --top 40
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter

from app.config import get_settings
from app.qa.isnad import analyze_isnad
from app.rijal import RijalIndex, load_entries
from app.rijal.muhmal import load_map as load_muhmal_map
from app.rijal.resolve import load_network
from scripts.audit_isnad import _build_canon


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit the «two chains» (waw co-narrator / ح) resolution — read-only.")
    ap.add_argument("--limit", type=int, default=None, help="scan only the first N chains")
    ap.add_argument("--top", type=int, default=30, help="how many top HELD route-start names to list")
    args = ap.parse_args()

    settings = get_settings()
    rijal = RijalIndex(load_entries(settings.rijal_file))
    canon = _build_canon(settings, rijal)
    muhmal = load_muhmal_map(settings.data_dir / "muhmal.json")
    network = load_network(settings.documented_network_path)
    print(f"rijal {rijal.count()} · مهمل {len(muhmal)} · شبكة {'yes' if network else 'no'}")

    if not settings.index_path.exists():
        print(f"⚠ no index at {settings.index_path} — run from the build dir (needs data/index.db).")
        return
    con = sqlite3.connect(str(settings.index_path))
    sql = "SELECT isnad FROM hadith WHERE trim(isnad) <> ''"
    if args.limit:
        sql += f" LIMIT {args.limit}"
    rows = con.execute(sql).fetchall()
    con.close()
    print(f"scanning {len(rows)} chains (split_conarrators=True)…", flush=True)

    counts: Counter[str] = Counter()
    held: Counter[str] = Counter()        # route-start names left «مشترك»/«غير معروف» (the review queue)
    won: Counter[str] = Counter()         # …and the ones a قاعدة/شبكة now resolves (the win)
    for n_done, (isnad,) in enumerate(rows, 1):
        if n_done % 1000 == 0:
            print(f"  … {n_done}/{len(rows)}", end="\r", flush=True)
        a = analyze_isnad(isnad, rijal=rijal, canon=canon, muhmal=muhmal, network=network,
                          split_conarrators=True)
        for nar in a.narrators:
            if not nar.get("route_start") or nar.get("is_prophet") or nar.get("mubham"):
                continue
            counts["route_start"] += 1
            rij = nar.get("rijal")
            if nar.get("resolved"):                       # fixed from its شيخ — the «two chains» win
                counts["resolved"] += 1
                won[nar["resolved"]] += 1
            elif rij is None:                             # غير معروف
                counts["unknown"] += 1
                held[nar["name"]] += 1
            elif rij.get("ambiguous"):                    # held «مشترك»
                counts["held"] += 1
                held[nar["name"]] += 1
            else:
                counts["graded"] += 1

    print(f"\nroute-start (co-narrator / ح) nodes: {counts['route_start']}")
    print(f"  ✅ resolved by شيخ (قاعدة/شبكة/رفقة): {counts['resolved']}")
    print(f"  ✅ graded directly (unique name):    {counts['graded']}")
    print(f"  ⚠️ held «مشترك»:                      {counts['held']}")
    print(f"  ⚠️ «غير معروف»:                       {counts['unknown']}")
    print(f"\nTOP {args.top} HELD route-start names (a قاعدة candidate, or honest homonymy):")
    for name, ct in held.most_common(args.top):
        print(f"  {ct:5}  {name}")
    print(f"\nTOP resolved-by-شيخ (the «two chains» win):")
    for name, ct in won.most_common(12):
        print(f"  {ct:5}  {name}")


if __name__ == "__main__":
    main()

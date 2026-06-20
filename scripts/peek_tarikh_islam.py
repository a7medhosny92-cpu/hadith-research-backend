"""Measure the تاريخ الإسلام (35100) extractor on the REAL downloaded book — read-only, before any build.

The سير lesson: a heading-based extractor can silently undercatch (the muqaddima skip, the طبقات), so
MEASURE before investing a build_graph. Reports: how many narrator tarjamas, how many carry a grade vs
«غير معروف», how many reach the LATE الأصم-class (death ≥ 300h), a death-decade spread, and a sample —
plus whether the الأصم himself (محمد بن يعقوب) is captured. Writes nothing.

    python -m scripts.peek_tarikh_islam
    python -m scripts.peek_tarikh_islam --show 25 --find "محمد بن يعقوب"
"""

from __future__ import annotations

import argparse
import collections
import json

from app.config import get_settings
from app.parsing.tarikh_islam_extract import TARIKH_ISLAM_BOOK_ID, iter_tarikh_islam
from app.rijal.grades import classify


def main() -> None:
    ap = argparse.ArgumentParser(description="Measure the تاريخ الإسلام extractor — read-only.")
    ap.add_argument("--show", type=int, default=20, help="how many sample records to print")
    ap.add_argument("--find", default=None, help="print records whose name contains this text")
    args = ap.parse_args()

    settings = get_settings()
    path = settings.raw_dir / "turath" / "books" / f"{TARIKH_ISLAM_BOOK_ID}.json"
    if not path.exists():
        print(f"⚠ {path} not found — download it first: python -m scripts.ingest --books {TARIKH_ISLAM_BOOK_ID}")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    recs = list(iter_tarikh_islam(data))
    print(f"تاريخ الإسلام (35100): {len(recs)} narrator tarjamas extracted")

    graded = sum(1 for r in recs if classify(r.get("grade", ""))[1] is not None)
    with_net = sum(1 for r in recs if r.get("shuyukh") or r.get("talamidh"))
    with_death = [r for r in recs if r.get("death_year")]
    late = [r for r in with_death if (r["death_year"] or 0) >= 300]
    print(f"  graded (a real جرح/تعديل): {graded}  ·  «غير معروف»: {len(recs) - graded}")
    print(f"  with شيوخ/تلاميذ network: {with_net}  ·  with a death year: {len(with_death)}")
    print(f"  ★ LATE (death ≥ 300h, the الأصم-class): {len(late)}")

    buckets: collections.Counter[int] = collections.Counter()
    for r in with_death:
        buckets[(r["death_year"] or 0) // 50 * 50] += 1
    print("  death-year spread (50y buckets):")
    for lo in sorted(buckets):
        print(f"    {lo:4d}–{lo+49}: {buckets[lo]}")

    grade_dist = collections.Counter(classify(r.get("grade", ""))[0] for r in recs)
    print("  grade distribution:")
    for g, n in grade_dist.most_common():
        print(f"    {g}: {n}")

    if args.find:
        hits = [r for r in recs if args.find in r.get("name", "")]
        print(f"\n=== {len(hits)} records matching «{args.find}» ===")
        for r in hits[:args.show]:
            print(f"  {r['name']}  ·  {r.get('grade','?')}  ·  ت{r.get('death_year','?')}  ·  "
                  f"شيوخ {len(r.get('shuyukh',[]))} · تلاميذ {len(r.get('talamidh',[]))}")
    else:
        print(f"\n=== sample (last {args.show}, the late men) ===")
        for r in recs[-args.show:]:
            print(f"  {r['name']}  ·  {r.get('grade','?')}  ·  ت{r.get('death_year','?')}")


if __name__ == "__main__":
    main()

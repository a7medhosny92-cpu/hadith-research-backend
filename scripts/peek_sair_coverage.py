"""Measure سير أعلام النبلاء (10906) extraction COVERAGE — read-only, fast, no rebuild.

The body «N -» boundary (rijal_extract._BOUNDARY) requires a line-start, but سير's tarjama
heads flow INLINE («… مات سنة ٢٠٠. ١٤٦ - فلان …»), so most are missed. This compares what the
CURRENT extractor catches against the reliable `indexes.headings`, and shows the طبقة spread
(by death-year) of what IS caught — so we know if the post-Six-Books الأصم-class (the A.3 target)
is captured or lost BEFORE committing to a 61-min build_graph.

    python -m scripts.peek_sair_coverage
"""

from __future__ import annotations

import json
from collections import Counter

from app.config import get_settings
from app.parsing.rijal_extract import _BOUNDARY
from app.parsing.sair_extract import SAIR_BOOK_ID, _tarjama_heads, book_main_text, iter_sair


def main() -> None:
    path = get_settings().raw_dir / "books" / f"{SAIR_BOOK_ID}.json"
    if not path.exists():
        print(f"{SAIR_BOOK_ID}.json not found under {path.parent}")
        return
    data = json.loads(path.read_text(encoding="utf-8"))

    # 1) headings index: how many are «N - Name» tarjama heads (the reliable structure the extractor walks)?
    headings = (data.get("indexes") or {}).get("headings") or []
    head_tarjamas = len(_tarjama_heads(data))

    # 2) body line-start «N -» boundaries (what the OLD body-boundary extractor keyed on — the 7% trap)
    full = book_main_text(data)
    body_bounds = sum(1 for m in _BOUNDARY.finditer(full) if m.group(1) is not None)

    # 3) what iter_sair actually yields, and its طبقة spread (by death-year)
    records = list(iter_sair(data))
    with_death = [r for r in records if r.get("death_year")]
    late = [r for r in records if (r.get("death_year") or 0) >= 250]   # post-Six-Books ≈ الأصم-class
    buckets = Counter()
    for r in with_death:
        y = r["death_year"]
        buckets["<150"] += y < 150
        buckets["150-249"] += 150 <= y < 250
        buckets["250-349"] += 250 <= y < 350
        buckets[">=350"] += y >= 350

    print(f"=== سير أعلام النبلاء {SAIR_BOOK_ID} coverage ===")
    print(f"indexes.headings total          : {len(headings)}")
    print(f"  «N - Name» tarjama heads      : {head_tarjamas}   ← the page-driven extractor walks these")
    print(f"OLD body line-start «N -» bounds: {body_bounds}   ← the 7% trap the rewrite replaced")
    print()
    print(f"iter_sair parsed records        : {len(records)}   ← should be ≈ the head count now")
    if head_tarjamas:
        print(f"  → emits {100*len(records)/head_tarjamas:.0f}% of heading tarjamas")
    print(f"  with a death-year             : {len(with_death)}")
    print(f"  LATE (وفاة ≥ 250, الأصم-class) : {len(late)}   ← the A.3 target")
    print(f"  death-year buckets            : {dict(buckets)}")
    print()
    print("sample LATE parsed names (وفاة ≥ 250):")
    for r in late[:12]:
        net = f" شيوخ:{len(r.get('shuyukh', []))} تلاميذ:{len(r.get('talamidh', []))}"
        print(f"  ت{r['death_year']:>4}  {r['name'][:45]:45s}  {r['grade']}{net}")


if __name__ == "__main__":
    main()

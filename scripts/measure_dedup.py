"""Measure how much of «مشترك» (ambiguous rijal matches) is really the SAME man written two
ways across تقريب/الكاشف — i.e. how far a *prudent* dedup (or one authoritative source such as
تهذيب الكمال) would deflate the ambiguity — versus how much is genuine homonymy that must stay.

It groups the رجال by «ism + first nasab» (the short form a chain actually cites, e.g. «الليث بن
سعد»), then, inside each colliding group, decides which entries are the same man under the
*prudent* rule the project chose: confirm a merge only when the death-years agree (±window) OR
the kunyas are identical; otherwise leave them apart. It reports three buckets:

  • removable   — duplicates a prudent dedup would safely collapse now (the مشترك we can deflate)
  • homonyms    — keys that stay ambiguous because the men are *confirmed different* (correctly مشترك)
  • unconfirmable— keys that stay ambiguous only because تقريب/الكاشف lack the death-year/kunya to
                   tell same-man from homonym — exactly what a richer source (تهذيب الكمال: full
                   name + death-year + شيوخ) would resolve.

    python -m scripts.measure_dedup                  # measure data/rijal.jsonl
    python -m scripts.measure_dedup --input file.jsonl --window 20 --examples 12
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from app.config import get_settings
from app.parsing.normalize import normalize_for_search

_BIN = {normalize_for_search(w) for w in ("بن", "ابن")}                 # patronymic links
_GEN = {normalize_for_search(w) for w in                                # «… الكبير» ≠ «… الحفيد»
        ("الكبير", "الأكبر", "الحفيد", "الأصغر", "الصغير")}


def _fold(text: str | None) -> str:
    return normalize_for_search(text or "")


def _ident_key(name: str) -> tuple[str, ...]:
    """«ism + first nasab»: folded tokens up to and including the first patronymic link —
    «الليث بن سعد بن عبد الرحمن الفهمي» and «الليث بن سعد أبو الحارث» both key on (الليث، سعد)."""
    toks = [t for t in (normalize_for_search(w) for w in name.split()) if t]
    for i, t in enumerate(toks):
        if t in _BIN:
            return tuple(x for x in toks[: i + 2] if x not in _BIN)
    return tuple(toks[:3])                                              # no nasab → first 3 tokens


def _tokens(name: str) -> set[str]:
    return {t for t in (normalize_for_search(w) for w in name.split()) if t and t not in _BIN}


def _nisbas(toks: set[str]) -> set[str]:
    """Nisba-like tokens: «الـ…ـي» (الموصلي، الكوفي، البغدادي) — a place/tribe discriminator."""
    return {t for t in toks if t.startswith("ال") and t.endswith("ي") and len(t) >= 4}


def _relation(a: dict, b: dict, window: int) -> str:
    """'same' | 'different' | 'unknown' under the prudent rule. A merge needs the names to
    *substantially overlap* (≥80% of the shorter), with no conflicting nisba or generation
    marker, AND confirmation by death-year (±window) or identical kunya — else it's left apart."""
    A, B = _tokens(a["name"]), _tokens(b["name"])
    if len(A & B) / (min(len(A), len(B)) or 1) < 0.8:
        return "different"                                            # names don't really overlap
    if (A & _GEN) != (B & _GEN):
        return "different"                                            # «الكبير» vs «الحفيد»
    na, nb = _nisbas(A), _nisbas(B)
    if na and nb and na.isdisjoint(nb):
        return "different"                                            # الموصلي vs الدورقي → not one man
    da, db = a.get("death_year"), b.get("death_year")
    if da and db:
        try:
            return "same" if abs(int(da) - int(db)) <= window else "different"
        except (TypeError, ValueError):
            pass
    ka, kb = _fold(a.get("kunya")), _fold(b.get("kunya"))
    if ka and kb:
        return "same" if ka == kb else "different"
    return "unknown"                                                  # names match; metadata can't confirm


def _cluster(group: list[dict], window: int) -> tuple[list[list[dict]], bool]:
    """Partition a same-key group into distinct men by transitive 'same'. Returns the clusters
    and whether any *residual* split between clusters is merely 'unknown' (i.e. unconfirmable)."""
    parent = list(range(len(group)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            if _relation(group[i], group[j], window) == "same":
                parent[find(i)] = find(j)
    buckets: dict[int, list[dict]] = defaultdict(list)
    for i, rec in enumerate(group):
        buckets[find(i)].append(rec)
    clusters = list(buckets.values())

    unknown_residual = False
    if len(clusters) > 1:
        reps = [c[0] for c in clusters]
        for i in range(len(reps)):
            for j in range(i + 1, len(reps)):
                if _relation(reps[i], reps[j], window) == "unknown":
                    unknown_residual = True
    return clusters, unknown_residual


def main() -> None:
    ap = argparse.ArgumentParser(description="Measure same-man duplication behind «مشترك».")
    ap.add_argument("--input", type=Path, default=None, help="rijal JSONL (default: settings.rijal_file)")
    ap.add_argument("--window", type=int, default=20, help="prudent death-year window in years")
    ap.add_argument("--examples", type=int, default=10, help="examples to print per bucket")
    args = ap.parse_args()

    path = args.input or get_settings().rijal_file
    records = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]

    groups: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for rec in records:
        groups[_ident_key(rec.get("name", ""))].append(rec)

    colliding = {k: g for k, g in groups.items() if len(g) > 1}
    removable = 0                       # entries a prudent dedup collapses (the مشترك we deflate)
    homonym_keys: list[tuple] = []      # stay ambiguous: men confirmed different (correct مشترك)
    unconfirmable_keys: list[tuple] = []  # stay ambiguous only for want of death-year/kunya
    ex_removable: list[str] = []

    for key, group in colliding.items():
        clusters, unknown_residual = _cluster(group, args.window)
        removed_here = len(group) - len(clusters)
        removable += removed_here
        if removed_here and len(ex_removable) < args.examples:
            collapsed = next(c for c in clusters if len(c) > 1)
            ex_removable.append(" ⟺ ".join(r["name"] for r in collapsed[:3]))
        if len(clusters) > 1:
            (unconfirmable_keys if unknown_residual else homonym_keys).append(key)

    def _names(keys: list[tuple], n: int) -> list[str]:
        out = []
        for k in keys[:n]:
            g = colliding[k]
            out.append(" / ".join(sorted({r["name"] for r in g})[:3]))
        return out

    print(f"input            : {path}")
    print(f"entries          : {len(records)}")
    print(f"colliding keys   : {len(colliding)}  (an «ism+nasab» shared by ≥2 entries)")
    print(f"  entries therein: {sum(len(g) for g in colliding.values())}")
    print(f"prudent window   : ±{args.window} years\n")
    print(f"► REMOVABLE now  : {removable} duplicate entries a prudent dedup safely collapses")
    print(f"  (these are the same man twice — the «مشترك» we can deflate today)")
    for e in ex_removable:
        print(f"     • {e}")
    print(f"\n► HOMONYMS kept  : {len(homonym_keys)} keys stay مشترك — men *confirmed different* (correct)")
    for e in _names(homonym_keys, args.examples):
        print(f"     • {e}")
    print(f"\n► UNCONFIRMABLE  : {len(unconfirmable_keys)} keys stay مشترك only for want of death-year/kunya")
    print(f"  (تقريب/الكاشف can't tell same-man from homonym here — تهذيب الكمال would)")
    for e in _names(unconfirmable_keys, args.examples):
        print(f"     • {e}")


if __name__ == "__main__":
    main()

"""Audit the رجال for SAME-MAN DUPLICATES the build leaves split — the doublings the «الرواة» index
shows (أبو بكر ×2، عبد الله بن عباس ×2…). Read-only: it reports the same-man clusters the current
canonicalization (build_rijal → collapse_duplicates) MISSES, classified by cause, so we size the
problem on the real ~20k رجال before strengthening the resolution.

    python -m scripts.audit_duplicates                 # summary + write data/duplicates.json
    python -m scripts.audit_duplicates --input f.jsonl  # measure a specific rijal.jsonl
    python -m scripts.audit_duplicates --cap 40         # example clusters kept per class

Classes (WHY the same man stayed two records):

  كنية       a كنية-led form («أبو بكر الصديق») whose tokens are a subset of a fuller ism-led name
             («عبد الله بن عثمان … أبو بكر الصديق»). They get a DIFFERENT ``ident_key``, so today's
             dedup never even compares them.
  ابن        an «ابن X» form («ابن عباس») shadowing the full «… بن X …» name — same cause.
  نقص قرينة   the SAME ``ident_key``, but ``same_man()`` can't confirm because the short form carries
             no nisba / death-year / كنية (the تقريب-vs-الإصابة Companion doubling).
  تلوث الاسم  a name carrying a biography tail («وقيل اسمه…», «أحد العشرة») — a name-QUALITY issue
             that breaks matching and dedup (reported separately, NOT counted as a removable cluster).

NOT a duplicate: a short form contained in SEVERAL distinct men (a genuinely shared كنية/«ابن») is
honest homonymy — counted as «ambiguous», never proposed as a merge. The tool only SURFACES candidate
clusters for review; it changes nothing.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict

from app.config import get_settings
from app.parsing.normalize import normalize_for_search
from app.rijal import RijalIndex, load_entries
from app.rijal.dedup import (
    _BIN, _GEN, _KUNYA_P, _strong_grade_conflict, ident_key, lineage_compatible, same_man, tokens,
)
from app.rijal.grades import classify

# A biography tail that leaked into the NAME (not the grade) — pollutes the token set so a man no
# longer matches his clean form. Companion bios are the usual culprit (الإصابة / تقريب-by-description).
_BIO = re.compile(
    r"وقيل|يقال|اسمه|أحد العشرة|العشرة المبشرين|ابن عم رسول|بنت رسول|خادم رسول|مولى رسول|"
    r"أمير المؤمنين|أم المؤمنين|زوج النبي|له صحبة|وله صحبة|شهد بدر|من السابقين"
)


def _clusters(pairs: list[tuple[int, int]]) -> list[list[int]]:
    """Union-find over the reported pairs → the connected same-man clusters (each ≥2 indices)."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        parent[find(a)] = find(b)
    groups: dict[int, list[int]] = defaultdict(list)
    for x in {i for pair in pairs for i in pair}:
        groups[find(x)].append(x)
    return [sorted(g) for g in groups.values() if len(g) >= 2]


def audit(records: list[dict]) -> dict:
    """Find the same-man clusters the build left split, by class. Returns counts + example clusters."""
    n = len(records)
    names = [r.get("name", "") for r in records]
    cats = [classify(r.get("grade") or "")[0] for r in records]
    toks = [tokens(nm) for nm in names]
    keys = [ident_key(nm) for nm in names]

    posting: dict[str, list[int]] = defaultdict(list)   # content token → entry indices
    for i, ts in enumerate(toks):
        for t in ts:
            posting[t].append(i)

    pairs: dict[str, list[tuple[int, int]]] = {"كنية": [], "ابن": [], "نقص قرينة": []}
    ambiguous: dict[str, int] = {"كنية": 0, "ابن": 0}

    # كنية / ابن shadows: a short form whose tokens ⊂ a fuller, DIFFERENT-key name.
    for i in range(n):
        head = normalize_for_search(names[i]).split()
        if not head:
            continue
        cls = "كنية" if head[0] in _KUNYA_P else ("ابن" if head[0] in _BIN else None)
        if cls is None or len(toks[i]) < 2:        # a bare كنية («أبو بكر») identifies no one
            continue
        probe = min(toks[i], key=lambda t: len(posting.get(t, ())))   # rarest token → small scan
        fulls = [j for j in posting.get(probe, ())
                 if j != i and toks[i] < toks[j] and keys[j] != keys[i]]
        if not fulls:
            continue
        if len({keys[j] for j in fulls}) > 1:      # the short form fits SEVERAL men → homonymy
            ambiguous[cls] += 1
            continue
        if _strong_grade_conflict(records[i], records[fulls[0]]):
            continue                               # a ثقة-vs-متروك clash → not blindly one man
        for j in fulls:
            pairs[cls].append((i, j))

    # نقص قرينة: same ident_key, but same_man() couldn't confirm — yet the lineage agrees, no
    # generation/grade conflict, and one name extends the other (or they share a category).
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i in range(n):
        groups[keys[i]].append(i)
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                if same_man(records[i], records[j]):
                    continue                       # the build already merged these
                if not lineage_compatible(records[i], records[j]):
                    continue
                if (toks[i] & _GEN) != (toks[j] & _GEN):
                    continue                       # الكبير ≠ الصغير
                if _strong_grade_conflict(records[i], records[j]):
                    continue
                if toks[i] < toks[j] or toks[j] < toks[i] or cats[i] == cats[j]:
                    pairs["نقص قرينة"].append((i, j))

    def render(cluster: list[int]) -> list[dict]:
        return [{"name": names[i], "grade": cats[i], "source": records[i].get("source")}
                for i in cluster]

    by_class: dict[str, dict] = {}
    removable = 0
    for cls, prs in pairs.items():
        cl = _clusters(prs)
        removable += sum(len(c) - 1 for c in cl)
        by_class[cls] = {"clusters": len(cl), "removable": sum(len(c) - 1 for c in cl),
                         "examples": [render(c) for c in cl]}

    bio = [i for i in range(n) if _BIO.search(names[i])]
    return {
        "entries": n,
        "removable": removable,
        "ambiguous": ambiguous,                    # shared forms — honest homonymy, not dups
        "by_class": by_class,
        "name_pollution": {"count": len(bio), "examples": [names[i] for i in bio[:60]]},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit the رجال for same-man duplicates left split.")
    ap.add_argument("--input", help="a rijal.jsonl to measure (default: settings.rijal_file)")
    ap.add_argument("--cap", type=int, default=30, help="example clusters to keep per class")
    args = ap.parse_args()

    settings = get_settings()
    if args.input:
        records = [json.loads(line) for line in open(args.input, encoding="utf-8") if line.strip()]
    else:
        idx = RijalIndex(load_entries(settings.rijal_file))   # seed + the full رجال base
        records = [{"name": e.name, "grade": e.grade_text, "kunya": e.kunya,
                    "death_year": e.death_year, "source": e.source} for e in idx._entries]
    print(f"rijal entries: {len(records)}")

    res = audit(records)
    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "entries": res["entries"],
        "removable": res["removable"],
        "ambiguous": res["ambiguous"],
        "counts": {cls: {"clusters": d["clusters"], "removable": d["removable"]}
                   for cls, d in res["by_class"].items()},
        "name_pollution": res["name_pollution"]["count"],
        "by_class": {cls: {**{k: d[k] for k in ("clusters", "removable")},
                           "examples": d["examples"][: args.cap]}
                     for cls, d in res["by_class"].items()},
        "name_pollution_examples": res["name_pollution"]["examples"],
    }
    out = settings.data_dir / "duplicates.json"
    out.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    print(f"same-man clusters the build left split → ~{res['removable']} removable duplicate records")
    for cls, d in res["by_class"].items():
        print(f"  {cls}: {d['clusters']} clusters · ~{d['removable']} removable")
    print(f"  (ambiguous shared forms, NOT dups: كنية {res['ambiguous']['كنية']} · ابن {res['ambiguous']['ابن']})")
    print(f"  تلوث الاسم (bio leaked into the name): {res['name_pollution']['count']} entries")
    for cls, d in res["by_class"].items():
        if not d["examples"]:
            continue
        print(f"\n— {cls} —")
        for cluster in d["examples"][:6]:
            print("   • " + "  ↔  ".join(f"{c['name']} [{c['grade']}]" for c in cluster))
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()

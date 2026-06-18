"""Dump the exact رجال base entries behind a cited NAME (read-only) — to see WHY it mis-resolves.

``probe_name`` shows what the matcher RETURNS; this shows the raw base records BEHIND it. For each name
it prints every entry whose (normalised) name EQUALS it — its grade/category, source, kunya, death,
aliases — so a bare/truncated «صحابي» shadow (an entry literally named «محمد بن جعفر» graded صحابي,
beside the real غندر «محمد بن جعفر الهذلي») is visible WITH the source that produced it. ``--contains``
widens to a substring match (every «محمد بن جعفر بن …») to see the whole homonym family.

    python -m scripts.peek_entry "محمد بن جعفر" "عبد الله بن عبد"
    python -m scripts.peek_entry --contains "بن جعفر"
"""

from __future__ import annotations

import argparse

from app.config import get_settings
from app.parsing.normalize import normalize_for_search
from app.rijal import load_entries
from app.rijal.grades import classify

# A name that ENDS on a dangling theophoric/relational particle is truncated — no real name ends on a
# bare «عبد» (the theophoric needs its second half: عبد + الله/الرحمن…), nor on «بن/أبو/ابن».
_DANGLING = {"عبد", "عبيد", "بن", "ابن", "أبو", "أبي", "أبا", "أم", "ذو", "ذي", "آل"}


_DANGLING_N = {normalize_for_search(w) for w in _DANGLING}


def _flags(name: str) -> str:
    """Flag only what is UNAMBIGUOUSLY wrong: a name ending on a dangling theophoric/particle is
    truncated. (Bare ism+father is NOT flagged — «سعد بن معاذ» is a real Companion of that shape.)"""
    toks = normalize_for_search(name).split()
    return "   ⚠ TRUNCATED (dangling tail)" if toks and toks[-1] in _DANGLING_N else ""


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump base رجال entries behind a name (read-only)")
    ap.add_argument("names", nargs="+", help="cited names to look up")
    ap.add_argument("--contains", action="store_true", help="substring match (the whole homonym family)")
    args = ap.parse_args()

    entries = load_entries(get_settings().rijal_file)
    print(f"rijal entries: {len(entries)}")
    for q in args.names:
        qn = normalize_for_search(q)
        hits = [
            e for e in entries
            if (qn in normalize_for_search(e.get("name", "")) if args.contains
                else normalize_for_search(e.get("name", "")) == qn)
        ]
        print(f"\n=== {q} === ({len(hits)} matching)")
        for e in hits:
            cat = classify(e.get("grade") or "")[0] or "—"
            f = [f"cat={cat}", f"grade={e.get('grade') or '—'}"]
            if e.get("kunya"):
                f.append(f"kunya={e['kunya']}")
            if e.get("death_year"):
                f.append(f"ت{e['death_year']}")
            if e.get("source"):
                f.append(f"src={e['source']}")
            if e.get("aliases"):
                f.append(f"aliases=[{'، '.join(e['aliases'])}]")
            print(f"  • «{e.get('name')}»  [{'  ·  '.join(f)}]{_flags(e.get('name', ''))}")


if __name__ == "__main__":
    main()

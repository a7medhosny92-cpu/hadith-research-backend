"""Derive candidate قواعد التمييز from the books — read-only, no rebuild, لا نختلق.

The hand-written ``app/rijal/qaida.py`` table (سفيان · حماد · هشام …) encodes what a محدّث knows:
a bare homonym is fixed by his **شيخ** (سفيان عن الأعمش = الثوري). But those rules ARE in the books:
تهذيب الكمال / الجرح / الثقات list every man's شيوخ/تلاميذ, and we already distil them into the
DIRECTIONAL ``documented_network.json``. So we can MINE the قواعد instead of hand-listing them:

  * for each ambiguous name (from the audit's ``a_ranked`` — the names actually cited «مشترك»),
    take its homonym set (``RijalIndex.candidates``);
  * read each homonym's شيوخ from the network (invert ``students`` → ``teachers``);
  * a شيخ DISTINCTIVE to one homonym (in his شيوخ, in NONE of his namesakes') is a قاعدة:
    «‹ism› عن ‹that شيخ› = ‹that homonym›». A شيخ shared by two namesakes is dropped (لا نختلق —
    exactly the curated table's discipline).
  * the marker is a DISTINCTIVE TOKEN of the شيخ's name (rare in the base — «دينار» for عمرو بن دينار,
    «الأعمش» — not the common ism «عمرو»/«سليمان»), so it matches the SHORT form a chain cites.

Output ``data/qaida.json`` (+ a printed summary): the proposed rules, each homonym with its distinctive
شيوخ and the marker tokens. **This is a PROPOSAL to REVIEW**, not auto-loaded — run it, eyeball the
rules (probe a sample), then we wire the trusted subset. A name whose homonyms share all their شيوخ is
the honest ②b floor (no قاعدة), reported separately.

    python -m scripts.derive_qaida                       # mine from data/audit.json a_ranked
    python -m scripts.derive_qaida --names سفيان حماد     # only these names
    python -m scripts.derive_qaida --min-count 20 --max-token-df 80

Reads ``data/rijal.jsonl`` + ``data/documented_network.json`` (+ ``data/audit.json`` for the name list).
Touches nothing the pipeline depends on; writes only ``data/qaida.json``.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from app.config import get_settings
from app.parsing.normalize import normalize_for_search
from app.rijal import RijalIndex, load_entries
from app.rijal.index import _clean_seq
from app.rijal.graph import NarratorGraph
from app.rijal.resolve import network_key


def _f(s: str) -> str:
    return normalize_for_search(s).strip()


def load_teachers(network_path: Path) -> dict[str, set[str]]:
    """Invert the documented ``students`` map → each man's شيوخ as ``network_key`` sets.
    ``students[T] ∋ S`` («T is a شيخ of S») ⟺ ``teachers[S] ∋ T``."""
    if not network_path.exists():
        return {}
    data = json.loads(network_path.read_text(encoding="utf-8"))
    teachers: dict[str, set[str]] = {}
    for shaykh_key, tilmidh_keys in data.get("students", {}).items():
        for tk in tilmidh_keys:
            teachers.setdefault(tk, set()).add(shaykh_key)
    return teachers


def token_df(entries) -> Counter:
    """Base-wide document frequency of each folded name token — a proxy for how DISTINCTIVE a token is
    (a marker must be rare: «دينار» identifies, the common «عمرو»/«محمد» does not). ``entries`` are the
    raw dicts ``load_entries`` returns."""
    df: Counter = Counter()
    for e in entries:
        for t in set(_clean_seq(e.get("name", ""))):
            df[t] += 1
    return df


def derive_rules(rijal: RijalIndex, teachers: dict[str, set[str]], df: Counter,
                 names, *, max_token_df: int = 50) -> tuple[dict, list[str]]:
    """The قواعد mined from the network. Returns ``(rules, floor)``:
    ``rules[folded ism] = [{name, markers, distinctive}]`` (homonyms with a distinctive شيخ + its marker
    tokens), and ``floor`` = the ambiguous names where NO homonym had a distinctive شيخ (the ②b floor)."""
    rules: dict[str, list[dict]] = {}
    floor: list[str] = []
    for raw in names:
        key = _f(raw)
        if not key or key in rules:
            continue
        cands = rijal.candidates(raw, max_results=None, apply_prominence=False)
        if len(cands) < 2:                               # not ambiguous → no قاعدة needed
            continue
        shuyukh = {e.name: teachers.get(network_key(e.name), frozenset()) for e in cands}
        homonyms: list[dict] = []
        for e in cands:
            mine = shuyukh[e.name]
            if not mine:
                continue
            others: set[str] = set()
            for n2, s in shuyukh.items():
                if n2 != e.name:
                    others |= s
            distinctive = mine - others                  # شيوخ unique to THIS homonym (لا نختلق)
            markers = sorted({t for sk in distinctive for t in sk.split()
                              if len(t) >= 3 and df.get(t, 0) <= max_token_df})
            if markers:
                homonyms.append({"name": e.name, "markers": markers,
                                 "distinctive": sorted(distinctive)})
        if homonyms:
            rules[key] = homonyms
        else:
            floor.append(raw)
    return rules, floor


def _audit_names(audit_path: Path, min_count: int) -> list[str]:
    """The «مشترك» names ranked by ambiguity frequency (audit.json a_ranked), count ≥ ``min_count``."""
    if not audit_path.exists():
        return []
    data = json.loads(audit_path.read_text(encoding="utf-8"))
    return [r["name"] for r in data.get("a_ranked", []) if r.get("count", 0) >= min_count]


def main() -> None:
    ap = argparse.ArgumentParser(description="Derive candidate قواعد التمييز from the documented network (read-only).")
    ap.add_argument("--names", nargs="*", help="ambiguous names to mine (default: audit.json a_ranked)")
    ap.add_argument("--min-count", type=int, default=5, help="only a_ranked names cited ambiguously ≥ N times")
    ap.add_argument("--max-token-df", type=int, default=50, help="a marker token must appear in ≤ N base entries")
    args = ap.parse_args()

    settings = get_settings()
    entries = load_entries(settings.rijal_file)
    rijal = RijalIndex(entries)
    gp = settings.narrator_graph_path
    if gp.exists():
        g = NarratorGraph(gp)
        if g.count():
            rijal.set_prominence(g.frequencies())
    teachers = load_teachers(settings.documented_network_path)
    df = token_df(entries)
    key2name = {network_key(e["name"]): e["name"]                 # folded شيخ key → a readable name
                for e in entries if e.get("name")}

    names = args.names or _audit_names(settings.data_dir / "audit.json", args.min_count)
    if not names:
        print("no names to mine — pass --names, or build data/audit.json (scripts.audit_isnad) for a_ranked.")
        return
    if not teachers:
        print("⚠ no documented_network.json — قواعد cannot be mined without the شيوخ/تلاميذ network.")
        return

    print(f"rijal {len(entries)} · network شيوخ-of {len(teachers)} · mining {len(names)} ambiguous names "
          f"(df≤{args.max_token_df})…")
    rules, floor = derive_rules(rijal, teachers, df, names, max_token_df=args.max_token_df)

    out = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "source": "documented_network.json + rijal.jsonl",
        "params": {"min_count": args.min_count, "max_token_df": args.max_token_df},
        "summary": {"names_processed": len(names), "names_with_qaida": len(rules),
                    "names_floor_shared_or_uncovered": len(floor)},
        "rules": rules,
    }
    out_path = settings.data_dir / "qaida.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    # a readable digest: the names that gained a قاعدة, homonym ← his distinctive شيوخ (real names)
    shown = 0
    for key, homs in sorted(rules.items(), key=lambda kv: -len(kv[1])):
        if shown >= 40:
            print(f"  … (+{len(rules) - shown} more in {out_path.name})")
            break
        print(f"\n=== {key}  ({len(homs)} مُميَّز) ===")
        for h in homs:
            who = "، ".join(key2name.get(k, k) for k in h["distinctive"][:6])
            print(f"  {h['name']}  ← عن: {who}   [markers: {' '.join(h['markers'][:8])}]")
        shown += 1
    print(f"\n{len(rules)} names gained a قاعدة · {len(floor)} stayed the ②b floor (shared/uncovered شيوخ) "
          f"→ {out_path}")


if __name__ == "__main__":
    main()

"""Hunt for isnad-PARSING bugs across the whole corpus: narrator nodes that came out corrupted.

A read-only diagnostic — the متن/رجال counterpart for the SEGMENTATION itself. It re-segments
every isnad with the SAME ``analyze_isnad`` the app uses, then flags any finalised narrator node
whose tokens still carry a non-name fragment that a transmission term should have stripped:

  verb     a transmission/قراءة verb glued onto the name — «الزهري أخبره»، «قرأت على مالك»
           (a verb form `_VIA`/the matn split missed; the dominant «bogus node» class)
  say      «قال/يقول/فقال …» left inside a node
  action   a narrated-scene verb «كان/يخطب/يصلّي/سأل …» glued on
  anna     «أنّ/أنّه …» (the report opener) glued onto the previous narrator
  backref  «مثله/نحوه/بهذا الإسناد/مرفوعًا …» — a back-reference, not a name
  number   a digit / hadith-number fragment inside the node

It groups the hits by class, ranks the offending tokens, and keeps sample node names + hadith ids
so each leak is traceable to a rule. Writes ``{DATA_DIR}/node_audit.json`` and prints a summary::

    python -m scripts.audit_nodes                 # scan all chains, write the report
    python -m scripts.audit_nodes --limit 5000    # scan only the first N (faster)

Every hit is for a human to verify; a class with a high count points at a missing rule to add
(the object-pronoun verbs «أخبره/حدثه/أنبأه» were found exactly this way).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from collections import Counter, defaultdict

from app.config import get_settings
from app.parsing.normalize import normalize_for_search
from app.qa.isnad import analyze_isnad
from app.rijal.graph import is_prophet

# A finalised node should be a NAME. These folded forms never belong in one — each is a transmission
# term, a report opener, or a back-reference the segmentation ought to have consumed.
_VERB_RE = re.compile(
    r"^(?:حدث|اخبر|انبا|نبا|سمع|قرا|اقرا|عرض|اجاز|ناول)(?:نا|ني|ه|ها|هم|هما|كم|ت|تنا|تني|تها|تم|وا)?$"
)
_SAY = {"قال", "قالا", "قالوا", "قالت", "يقول", "تقول", "فقال", "فقالت", "فقالوا", "يقولون"}
_ACTION = {"كان", "يخطب", "يصلي", "يدعو", "يقرا", "يكبر", "يامر", "يحدث", "يذكر", "يصنع", "يفعل",
           "سال", "سالت", "سالنا", "راى", "رايت", "اتى", "جاء", "دخل", "خرج"}
_ANNA = {"ان", "انه", "انها", "انهم", "انهما"}
_BACKREF = {"مثله", "نحوه", "بمثله", "بنحوه", "مرفوعا", "رفعه", "يرفعه", "فذكره", "فذكر",
            "الاسناد", "اسناده", "باسناده", "بسنده", "باسناد", "بهذا", "بهذه", "بمعناه", "بمعنى"}
_DIGIT = re.compile(r"[0-9٠-٩۰-۹]")


def _classify_token(folded: str) -> str | None:
    """The bug-class a stray node token betrays, or ``None`` if it is a legitimate name token.
    «بن/ابن» and kunya particles (أبو/أم) and the Prophet's eulogy are NOT flagged — they are real
    parts of finalised node names."""
    if not folded:
        return None
    if _DIGIT.search(folded):
        return "number"
    if folded in _ANNA:
        return "anna"
    if folded in _SAY:
        return "say"
    if folded in _ACTION:
        return "action"
    if folded in _BACKREF:
        return "backref"
    if _VERB_RE.match(folded):
        return "verb"
    return None


def junk_in_node(name: str) -> list[tuple[str, str]]:
    """(token, class) for every non-name fragment glued into a finalised node — empty when clean.
    The Prophet's terminal node (his name + eulogy) is exempt: «صلّى/عليه/وسلّم» are not narrator
    tokens but belong there legitimately."""
    if is_prophet(name):
        return []
    hits: list[tuple[str, str]] = []
    for tok in name.split():
        folded = normalize_for_search(tok)
        cls = _classify_token(folded)
        if cls:
            hits.append((folded, cls))
    return hits


def main() -> None:
    ap = argparse.ArgumentParser(description="Find isnad-parsing bugs (corrupted narrator nodes).")
    ap.add_argument("--limit", type=int, default=None, help="scan only the first N hadith")
    ap.add_argument("--cap", type=int, default=400, help="sample nodes to keep per class")
    args = ap.parse_args()

    settings = get_settings()
    con = sqlite3.connect(str(settings.index_path))
    sql = "SELECT rowid, collection, number, isnad FROM hadith WHERE trim(isnad) <> ''"
    if args.limit:
        sql += f" LIMIT {args.limit}"
    rows = con.execute(sql).fetchall()
    total = len(rows)
    print(f"scanning {total} chains for parsing bugs (re-segmenting each isnad)…", flush=True)

    counts: Counter[str] = Counter()          # class → number of corrupted nodes
    tokens: dict[str, Counter] = defaultdict(Counter)   # class → offending token → count
    samples: dict[str, list[dict]] = defaultdict(list)  # class → sample corrupted nodes
    seen_nodes: set[str] = set()
    scanned = flagged = 0
    for rid, coll, num, isnad in rows:
        scanned += 1
        if scanned % 500 == 0:
            print(f"  … {scanned}/{total}", end="\r", flush=True)
        for nar in analyze_isnad(isnad).narrators:
            name = nar.get("name", "")
            hits = junk_in_node(name)
            if not hits:
                continue
            flagged += 1
            classes = {c for _t, c in hits}
            for tok, cls in hits:
                tokens[cls][tok] += 1
            for cls in classes:
                counts[cls] += 1
                if name not in seen_nodes and len(samples[cls]) < args.cap:
                    samples[cls].append({"id": rid, "collection": coll, "number": num, "node": name})
            seen_nodes.add(name)
    con.close()

    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "scanned": scanned,
        "flagged_nodes": flagged,
        "distinct_nodes": len(seen_nodes),
        "counts": dict(counts.most_common()),
        "top_tokens": {cls: tokens[cls].most_common(25) for cls in counts},
        "samples": samples,
    }
    out_path = settings.data_dir / "node_audit.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    print(f"\nscanned {scanned} chains → {out_path}")
    print(f"corrupted narrator nodes: {flagged}  (distinct: {len(seen_nodes)})")
    for cls, ct in counts.most_common():
        top = "، ".join(f"{t}×{c}" for t, c in tokens[cls].most_common(6))
        print(f"  [{cls:8}] {ct:>6}   {top}")


if __name__ == "__main__":
    main()

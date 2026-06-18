"""Why is a باب still missing from the «الكتب» tab? Categorise every heading absent from index.db.

Read-only. For one book it replays the parser's heading→chapter map (the «كتاب ← باب» hierarchy) and,
for each heading whose chapter has NO row in index.db (no hadith AND no recovered تعليق), reports WHY:

  * multi-head-page — other أبواب share its page, so the page-granularity two-pointer gave all the
    page's hadith to the LAST باب on the page (this باب lost them). The real lever (in-page ordering).
  * has-marker     — its page range holds a hadith marker, but it is a single heading (a shared page).
  * empty/short    — no real body (a verse/تعليق inside the heading itself, or a bare structural باب).
  * ancestor       — a كتاب above أبواب that DO have hadith (correctly not a leaf; expected).

    python -m scripts.peek_missing_chapters 1284            # صحيح البخاري
    python -m scripts.peek_missing_chapters 1284 --limit 80

Needs the raw book (data/raw/books/{id}.json) AND a built index.db. Run after a re-parse.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter

from app.config import get_settings
from app.parsing.hadith_extract import _detect_marker, _first_text_page
from app.parsing.html_clean import clean_block, remove_footnote_refs, split_footnotes


def _head_chapters(headings: list) -> list[tuple[int, int, str]]:
    """(page, level, title) sorted by page — the parser's heading list."""
    heads = []
    for h in headings or []:
        p, t = h.get("page"), (h.get("title") or "").strip()
        if p is not None and t:
            heads.append((int(p), int(h.get("level") or 99), t))
    heads.sort(key=lambda x: x[0])
    return heads


def _chapter_strings(heads: list[tuple[int, int, str]]) -> list[str]:
    out, active = [], {}
    for _p, lvl, title in heads:
        for d in [l for l in list(active) if l > lvl]:
            del active[d]
        active[lvl] = title
        out.append(" ← ".join(active[l] for l in sorted(active)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Categorise the أبواب still missing from the library.")
    ap.add_argument("book_id", type=int)
    ap.add_argument("--limit", type=int, default=60, help="missing chapters to print")
    args = ap.parse_args()

    settings = get_settings()
    raw = settings.raw_dir / "books" / f"{args.book_id}.json"
    if not raw.exists():
        raise SystemExit(f"{raw} not found — the raw turath book isn't downloaded")
    data = json.loads(raw.read_text(encoding="utf-8"))
    heads = _head_chapters((data.get("indexes") or {}).get("headings"))
    chapters = _chapter_strings(heads)

    # present chapters (have a hadith OR a recovered تعليق) from index.db
    con = sqlite3.connect(str(settings.index_path))
    present = {r[0] for r in con.execute(
        "SELECT DISTINCT chapter FROM hadith WHERE book_id = ? AND chapter IS NOT NULL", (args.book_id,))}
    con.close()

    # page text (for the body/marker check) + heading-per-page counts
    start = _first_text_page(data)
    marker = _detect_marker(data.get("pages", []), start)
    pg_text: dict[int, str] = {}
    pgs: list[int] = []
    for page in sorted(data.get("pages", []), key=lambda p: p.get("pg", 0)):
        pg = page.get("pg", 0)
        if start is not None and pg < start:
            continue
        body, _ = split_footnotes(page.get("text") or "")
        pg_text[pg] = clean_block(body)
        pgs.append(pg)
    pgs.sort()
    heads_on_page = Counter(p for p, _l, _t in heads)

    # ancestors of present chapters (a كتاب above ones that have hadith)
    ancestors = set()
    for sc in present:
        parts = sc.split(" ← ")
        for k in range(1, len(parts)):
            ancestors.add(" ← ".join(parts[:k]))

    import bisect
    cats: Counter = Counter()
    rows = []
    for i, (p_i, _lvl, title) in enumerate(heads):
        cs = chapters[i]
        if cs in present:
            continue
        if cs in ancestors:
            cats["ancestor"] += 1
            continue
        p_next = next((heads[j][0] for j in range(i + 1, len(heads)) if heads[j][0] > p_i), None)
        lo = bisect.bisect_left(pgs, p_i)
        hi_ = bisect.bisect_left(pgs, p_next) if p_next is not None else len(pgs)
        block = " ".join(pg_text.get(pp, "") for pp in pgs[lo:hi_])
        body = remove_footnote_refs(block).replace(title, " ", 1).strip()
        words = len([w for w in body.split() if any("ء" <= c <= "ي" for c in w)])
        if heads_on_page[p_i] > 1:
            cat = "multi-head-page"
        elif marker.search(block):
            cat = "has-marker"
        else:
            cat = "empty/short"
        cats[cat] += 1
        rows.append((cat, p_i, heads_on_page[p_i], words, cs))

    print(f"book {args.book_id}: {len(heads)} headings · {len(present)} present chapters · "
          f"{sum(cats.values())} absent")
    print(f"  by reason: {dict(cats)}")
    print("  (multi-head-page + has-marker = recoverable by in-page ordering · "
          "empty/short = no body to show · ancestor = a كتاب above its أبواب, expected)\n")
    print(f"{'reason':>16}  {'page':>6}  {'#heads':>6}  {'words':>5}   chapter")
    for cat, pg, nh, words, cs in rows[: args.limit]:
        print(f"{cat:>16}  {pg:>6}  {nh:>6}  {words:>5}   «{cs}»")
    if len(rows) > args.limit:
        print(f"… (+{len(rows) - args.limit} more)")


if __name__ == "__main__":
    main()

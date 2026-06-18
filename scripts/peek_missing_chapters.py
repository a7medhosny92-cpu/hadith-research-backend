"""Why is a باب still missing from the «الكتب» tab? Categorise every heading absent from index.db.

Read-only. Replays the parser's heading→chapter map (the «كتاب ← باب» hierarchy) and, for each heading
whose chapter has NO row in index.db (no hadith AND no recovered تعليق), reports WHY:

  * mh:align-fail — several أبواب share the page AND their title spans don't match the indexed headings →
    the in-page fix fell back to the page-level باب, so an earlier باب-with-hadith is mis-filed (FIXABLE).
  * mh:aligned    — aligned yet absent = a تعليق-only باب on a page shared with a hadith باب.
  * has-marker    — a single heading whose page range holds a marker (a shared page).
  * empty/short   — no real body (a verse/تعليق inside the heading itself, or a bare structural باب).
  * ancestor      — a كتاب above أبواب that DO have hadith (correctly not a leaf; expected).

    python -m scripts.peek_missing_chapters            # SUMMARY of every book (one line each)
    python -m scripts.peek_missing_chapters 1284       # one book, detailed
    python -m scripts.peek_missing_chapters 1284 --limit 80

Needs the raw book(s) (data/raw/books/{id}.json) AND a built index.db. Run after a re-parse.
"""

from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
from collections import Counter

from app.config import get_settings
from app.parsing.hadith_extract import _aligned, _detect_marker, _eff_level, _first_text_page, _HEAD_SENTINEL
from app.parsing.html_clean import clean_block, clean_block_marked, extract_titles, remove_footnote_refs, split_footnotes


def _head_chapters(headings: list) -> list[tuple[int, float, str]]:
    """(page, effective-level, title) sorted by page — the parser's heading list."""
    heads = []
    for h in headings or []:
        p, t = h.get("page"), (h.get("title") or "").strip()
        if p is not None and t:
            heads.append((int(p), _eff_level(int(h.get("level") or 99), t), t))
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


def _analyze(data: dict, present: set[str]) -> tuple[int, int, int, Counter, list, int | None]:
    """(n_headings, n_present, n_skipped_muqaddima, cats, detail_rows, start_page) for one book."""
    heads = _head_chapters((data.get("indexes") or {}).get("headings"))
    chapters = _chapter_strings(heads)
    start = _first_text_page(data)
    marker = _detect_marker(data.get("pages", []), start)
    pg_text: dict[int, str] = {}
    pgs: list[int] = []
    for page in sorted(data.get("pages", []), key=lambda p: p.get("pg", 0)):
        pg = page.get("pg", 0)
        if start is not None and pg < start:
            continue
        pg_text[pg] = clean_block(split_footnotes(page.get("text") or "")[0])
        pgs.append(pg)
    pgs.sort()
    heads_on_page = Counter(p for p, _l, _t in heads)
    raw_by_pg = {p.get("pg", 0): p for p in data.get("pages", [])}
    titles_at: dict[int, list[str]] = {p: [t for q, _l, t in heads if q == p] for p in heads_on_page}

    def _aligned_at(pg: int) -> bool | None:
        page = raw_by_pg.get(pg)
        if page is None or len(titles_at.get(pg, [])) < 2:
            return None
        _, spans = clean_block_marked(split_footnotes(page.get("text") or "")[0], _HEAD_SENTINEL)
        return _aligned(spans, titles_at[pg])

    ancestors = set()
    for sc in present:
        parts = sc.split(" ← ")
        for k in range(1, len(parts)):
            ancestors.add(" ← ".join(parts[:k]))

    cats: Counter = Counter()
    rows = []
    skipped = 0
    for i, (p_i, _lvl, title) in enumerate(heads):
        if start is not None and p_i < start:        # the محقق's introduction — not a باب
            skipped += 1
            continue
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
        if heads_on_page[p_i] > 1:
            cat = "mh:align-fail" if _aligned_at(p_i) is False else "mh:aligned"
        elif marker.search(block):
            cat = "has-marker"
        else:
            cat = "empty/short"
        cats[cat] += 1
        body = remove_footnote_refs(block).replace(title, " ", 1).strip()
        words = len([w for w in body.split() if any("ء" <= c <= "ي" for c in w)])
        rows.append((cat, p_i, f"{heads_on_page[p_i]}h/{len(titles_at.get(p_i, []))}s", words, cs))
    return len(heads), len(present), skipped, cats, rows, start


def _present(con: sqlite3.Connection, book_id: int) -> set[str]:
    return {r[0] for r in con.execute(
        "SELECT DISTINCT chapter FROM hadith WHERE book_id = ? AND chapter IS NOT NULL", (book_id,))}


def main() -> None:
    ap = argparse.ArgumentParser(description="Categorise the أبواب still missing from the library.")
    ap.add_argument("book_id", type=int, nargs="?", help="one book (detailed); omit to summarise ALL books")
    ap.add_argument("--limit", type=int, default=60, help="missing chapters to print (single-book mode)")
    args = ap.parse_args()

    settings = get_settings()
    if not settings.index_path.exists():
        raise SystemExit(f"no index at {settings.index_path} — run scripts.index first")
    con = sqlite3.connect(str(settings.index_path))

    if args.book_id is None:                          # ── summary of every book ──
        books = con.execute(
            "SELECT book_id, collection FROM hadith GROUP BY book_id ORDER BY MIN(rowid)").fetchall()
        print(f"{'book':>7}  {'present':>7}  {'absent':>6}  {'align-fail':>10}  {'aligned':>7}  "
              f"{'marker':>6}  {'empty':>6}   collection")
        for book_id, coll in books:
            raw = settings.raw_dir / "books" / f"{book_id}.json"
            if not raw.exists():
                continue
            data = json.loads(raw.read_text(encoding="utf-8"))
            _, n_present, _, cats, _, _ = _analyze(data, _present(con, book_id))
            print(f"{book_id:>7}  {n_present:>7}  {sum(cats.values()):>6}  {cats.get('mh:align-fail', 0):>10}  "
                  f"{cats.get('mh:aligned', 0):>7}  {cats.get('has-marker', 0):>6}  "
                  f"{cats.get('empty/short', 0):>6}   {coll}")
        print("\nalign-fail = FIXABLE (in-page ordering) · aligned/marker = تعليق-only on a shared page · "
              "empty = no body (verse/structural). Run «peek_missing_chapters <book_id>» for a book's detail.")
        con.close()
        return

    raw = settings.raw_dir / "books" / f"{args.book_id}.json"
    if not raw.exists():
        raise SystemExit(f"{raw} not found — the raw turath book isn't downloaded")
    data = json.loads(raw.read_text(encoding="utf-8"))
    n_heads, n_present, skipped, cats, rows, start = _analyze(data, _present(con, args.book_id))
    con.close()

    print(f"book {args.book_id}: {n_heads} headings · {n_present} present chapters · {sum(cats.values())} "
          f"absent (after skipping {skipped} muqaddima headings below the first hadith, page {start})")
    print(f"  by reason: {dict(cats)}")
    print("  (mh:align-fail = title spans don't match the indexed headings on the page → the in-page fix "
          "fell back, a باب-with-hadith is mis-filed (FIXABLE) · mh:aligned = aligned yet absent = تعليق-only "
          "on a shared page · has-marker/empty-short/ancestor as before. «Nh/Ms» = N headings, M title spans)\n")
    print(f"{'reason':>16}  {'page':>6}  {'h/s':>7}  {'words':>5}   chapter")
    for cat, pg, nh, words, cs in rows[: args.limit]:
        print(f"{cat:>16}  {pg:>6}  {nh:>7}  {words:>5}   «{cs}»")
    if len(rows) > args.limit:
        print(f"… (+{len(rows) - args.limit} more)")


if __name__ == "__main__":
    main()

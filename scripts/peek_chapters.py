"""Dump a collection's chapters AS THE LIBRARY TAB GROUPS THEM — to see why some أبواب go missing.

Read-only, fast. For one book it prints each distinct ``chapter`` string with its hadith COUNT and the
hadith-NUMBER range it spans, in book order, plus how many hadiths carry NO chapter (excluded from the
tab). A chapter with a huge count over a WIDE number range = many untitled «باب» collapsed into one
(the GROUP BY fuses same-text headings); a big NULL count = headings the parser didn't attach.

    python -m scripts.peek_chapters 1284          # صحيح البخاري
    python -m scripts.peek_chapters 1198 --limit 100
"""

from __future__ import annotations

import argparse
import sqlite3

from app.config import get_settings


def _fused(rows: list) -> list:
    """Chapters that look fused: ≥15 hadiths spanning a wide (≥50) number range."""
    return [(ch, n, mn, mx) for ch, n, mn, mx in rows
            if n >= 15 and mn and mx and (mx - mn) >= 50]


def _chapter_rows(con: sqlite3.Connection, book_id: int) -> list:
    return con.execute(
        "SELECT chapter, COUNT(*), MIN(CAST(number AS INTEGER)), MAX(CAST(number AS INTEGER)) "
        "FROM hadith WHERE book_id = ? AND chapter IS NOT NULL AND chapter <> '' "
        "GROUP BY chapter ORDER BY MIN(CAST(number AS INTEGER)), MIN(rowid)",
        (book_id,),
    ).fetchall()


def _null_count(con: sqlite3.Connection, book_id: int) -> int:
    return con.execute(
        "SELECT COUNT(*) FROM hadith WHERE book_id = ? AND (chapter IS NULL OR chapter = '')",
        (book_id,),
    ).fetchone()[0]


def _summarise_all(con: sqlite3.Connection) -> None:
    """One line per book: hadiths · distinct chapters · FUSED chapters (+their hadiths) · NO-chapter."""
    books = con.execute(
        "SELECT book_id, collection, COUNT(*) FROM hadith GROUP BY book_id ORDER BY MIN(rowid)"
    ).fetchall()
    print(f"{'book':>7}  {'ح':>6}  {'فصول':>5}  {'FUSED':>5} {'(ح)':>7}  {'بلا فصل':>7}   collection")
    for book_id, coll, total in books:
        rows = _chapter_rows(con, book_id)
        fused = _fused(rows)
        fused_h = sum(n for _, n, _, _ in fused)
        nulls = _null_count(con, book_id)
        flag = " ⚠" if (fused or nulls > total * 0.05) else ""
        print(f"{book_id:>7}  {total:>6}  {len(rows):>5}  {len(fused):>5} {fused_h:>7}  {nulls:>7}{flag}   {coll}")
    print("\n⚠ = some «بَابٌ» fused (FUSED>0) or >5% hadiths with no chapter. "
          "Run «peek_chapters <book_id>» for that book's detail.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump a book's chapters as the library tab groups them.")
    ap.add_argument("book_id", type=int, nargs="?", help="one book; omit to summarise ALL books")
    ap.add_argument("--limit", type=int, default=60, help="chapters to print")
    args = ap.parse_args()

    db = get_settings().index_path
    if not db.exists():
        raise SystemExit(f"no index at {db} — run scripts.index first")
    con = sqlite3.connect(str(db))

    if args.book_id is None:                       # ── summary of every book ──
        _summarise_all(con)
        con.close()
        return

    total = con.execute("SELECT COUNT(*) FROM hadith WHERE book_id = ?", (args.book_id,)).fetchone()[0]
    rows = _chapter_rows(con, args.book_id)
    null_n = _null_count(con, args.book_id)
    con.close()

    print(f"book {args.book_id}: {total} hadiths · {len(rows)} distinct chapters · {null_n} with NO chapter")
    print(f"\n{'ح':>5}  {'#range':>13}   chapter")
    for ch, n, mn, mx in rows[: args.limit]:
        span = f"{mn}-{mx}" if mn != mx else f"{mn}"
        flag = "  ⚠ FUSED?" if n >= 15 and mx and mn and (mx - mn) >= 15 else ""
        print(f"{n:>5}  {span:>13}   «{ch}»{flag}")
    if len(rows) > args.limit:
        print(f"… (+{len(rows) - args.limit} more)")
    print(f"\nNote: a chapter with a big count over a WIDE #range (⚠) = untitled «باب» fused by GROUP BY;\n"
          f"a large «NO chapter» = headings the parser didn't attach to their hadiths.")


if __name__ == "__main__":
    main()

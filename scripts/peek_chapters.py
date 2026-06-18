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


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump a book's chapters as the library tab groups them.")
    ap.add_argument("book_id", type=int)
    ap.add_argument("--limit", type=int, default=60, help="chapters to print")
    args = ap.parse_args()

    db = get_settings().index_path
    if not db.exists():
        raise SystemExit(f"no index at {db} — run scripts.index first")
    con = sqlite3.connect(str(db))

    total = con.execute("SELECT COUNT(*) FROM hadith WHERE book_id = ?", (args.book_id,)).fetchone()[0]
    rows = con.execute(
        "SELECT chapter, COUNT(*), MIN(CAST(number AS INTEGER)), MAX(CAST(number AS INTEGER)) "
        "FROM hadith WHERE book_id = ? AND chapter IS NOT NULL AND chapter <> '' "
        "GROUP BY chapter ORDER BY MIN(CAST(number AS INTEGER)), MIN(rowid)",
        (args.book_id,),
    ).fetchall()
    null_n = con.execute(
        "SELECT COUNT(*) FROM hadith WHERE book_id = ? AND (chapter IS NULL OR chapter = '')",
        (args.book_id,),
    ).fetchone()[0]
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

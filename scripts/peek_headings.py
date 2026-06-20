"""Dump a raw turath book's ``indexes.headings`` hierarchy (level · page · title) — read-only.

The hadith parser takes the chapter from the page TEXT (``extract_titles``), so untitled «بَابٌ»
headings collide and whole أبواب fuse in the «الكتب» tab. turath already ships a structured
``indexes.headings`` (each with a ``level`` — كتاب vs باب — and a ``page``); this prints it so we can
build a UNIQUE, hierarchical chapter id (كتاب → باب) from it instead. One book at a time.

    python -m scripts.peek_headings 1284            # صحيح البخاري (باب-based)
    python -m scripts.peek_headings 25794 --limit 80   # مسند أحمد (musnad-based)
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

from app.config import get_settings


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump a turath book's indexes.headings hierarchy (read-only).")
    ap.add_argument("book_id", type=int)
    ap.add_argument("--limit", type=int, default=60, help="headings to print")
    ap.add_argument("--level", type=int, default=None, help="show only headings at this level")
    ap.add_argument("--from", dest="from_page", type=int, default=None, help="start at this page")
    ap.add_argument("--grep", default=None, help="show only titles containing this text")
    args = ap.parse_args()

    path = get_settings().raw_dir / "books" / f"{args.book_id}.json"
    if not path.exists():
        raise SystemExit(f"{path} not found — the raw turath book isn't downloaded")
    data = json.loads(path.read_text(encoding="utf-8"))
    idx = data.get("indexes") or {}
    headings = idx.get("headings") or []
    numbers = idx.get("numbers") or {}

    levels = Counter(h.get("level") for h in headings)
    print(f"book {args.book_id}: {len(headings)} headings · levels {dict(levels)} · "
          f"indexes.numbers: {len(numbers)}")
    sel = [
        h for h in headings
        if (args.level is None or h.get("level") == args.level)
        and (args.from_page is None or (h.get("page") or 0) >= args.from_page)
        and (args.grep is None or args.grep in (h.get("title") or ""))
    ]
    print(f"\n{'level':>5}  {'page':>6}   title   ({len(sel)} match the filters)")
    for h in sel[: args.limit]:
        print(f"{str(h.get('level')):>5}  {str(h.get('page')):>6}   {h.get('title')}")
    if len(sel) > args.limit:
        print(f"… (+{len(sel) - args.limit} more)")
    print("\nWhat to look for: is there a كتاب-level (e.g. level 1/2) ABOVE the باب-level (a deeper "
          "level)? If yes, the parser can build «كتاب → باب» unique ids from this, page-aligned to "
          "each hadith — no more fused «بَابٌ».")


if __name__ == "__main__":
    main()

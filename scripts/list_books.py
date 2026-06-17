"""List the turath books currently DOWNLOADED (``data/raw/turath/books/``) with id · size · cat · title
— read-only. To see what's on disk before picking a new رجال/biographical source to ingest, so we
REUSE an already-downloaded book instead of re-fetching a 30-MB file. Titles come from the cached
catalog (``raw_dir/catalog.json``); without it, only ids + sizes are shown.

    python -m scripts.list_books            # everything on disk
    python -m scripts.list_books رجال سير     # only titles matching a substring
"""

from __future__ import annotations

import glob
import json
import os
import sys

from app.config import get_settings


def main() -> None:
    queries = sys.argv[1:]
    raw = get_settings().raw_dir
    cf = next((p for p in (raw / "catalog.json", raw / "data-v3.json") if p.exists()), None)
    cat: dict[int, tuple[str, object]] = {}
    if cf:
        books = json.loads(cf.read_text(encoding="utf-8")).get("books", {})
        cat = {b.get("id"): (b.get("name", ""), b.get("cat_id")) for b in books.values()}

    rows = sorted(
        (int(os.path.basename(p)[:-5]), os.path.getsize(p))
        for p in glob.glob(str(raw / "books" / "*.json"))
        if os.path.basename(p)[:-5].isdigit()
    )
    note = "" if cf else "  (no catalog cached → titles unknown)"
    print(f"{len(rows)} books under {raw / 'books'}{note}")
    total = shown = 0
    for bid, size in rows:
        total += size
        name, c = cat.get(bid, ("?", "?"))
        if queries and not any(q in name for q in queries):
            continue
        shown += 1
        print(f"  {bid:<7} {size / 1048576:6.1f}MB  cat {str(c):<3} {name}")
    if queries:
        print(f"  ({shown} shown of {len(rows)})")
    print(f"  total ≈ {total / 1048576:.0f} MB")


if __name__ == "__main__":
    main()

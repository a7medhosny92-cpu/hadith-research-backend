"""Pull readable sample tarājim from a رجال source book — to *study a prose source* (تهذيب
الكمال، تهذيب التهذيب) before writing an extractor for it.

It downloads the book if it isn't on disk yet (resumable, polite — exactly like
``build_rijal``), but it **never touches ``data/rijal.jsonl``**: it only reads pages and
prints them. Use it to see how a tarjama lays out name / شيوخ («روى عن») / تلاميذ («روى عنه»)
/ each critic's verdict («قال فلان…») / death, so the extractor can be designed against real
text instead of guesswork.

    python -m scripts.sample_source 3722 --entries 5           # first 5 full tarājim of تهذيب الكمال
    python -m scripts.sample_source 3722 --find "الليث بن سعد"  # the tarjama of a specific narrator
    python -m scripts.sample_source 3722 --pages 40-44          # raw cleaned text of a page range
    python -m scripts.sample_source 3722 --entries 8 --out sample.txt   # write it out to upload

The book ids: تهذيب الكمال = 3722، تهذيب التهذيب = 1293 (ط الرسالة) / 1278 (ط دبي)،
تقريب = 8609، الكاشف = 2171.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.config import get_settings
from app.ingestion.catalog import Catalog
from app.ingestion.downloader import CorpusDownloader
from app.ingestion.turath_client import TurathClient
from app.parsing.html_clean import clean_block
from app.parsing.rijal_extract import _BOUNDARY, _first_entry_page


async def _ensure(book_id: int) -> Path:
    """Return the on-disk book path, downloading it first if absent (rijal.jsonl untouched)."""
    settings = get_settings()
    path = settings.raw_dir / "books" / f"{book_id}.json"
    if path.exists():
        return path
    async with TurathClient(
        settings.turath_api_base, settings.turath_files_base,
        rate_per_sec=settings.turath_rate_per_sec, max_retries=settings.turath_max_retries,
        timeout=settings.turath_timeout, user_agent=settings.turath_user_agent,
    ) as client:
        downloader = CorpusDownloader(client, settings.raw_dir, on_progress=print)
        print(f"Downloading book {book_id} (one-off, won't modify rijal.jsonl)…")
        catalog = Catalog.from_raw(await downloader.download_catalog())
        if book_id not in catalog.books:
            raise SystemExit(f"book {book_id} is not in the turath catalog")
        await downloader.download_books([catalog.books[book_id]])
    return path


def _full_text(data: dict) -> str:
    """Cleaned text of all pages, in order, from the first numbered tarjama (skip muqaddima)."""
    start = _first_entry_page(data)
    pages = [p for p in data.get("pages", []) if start is None or p.get("pg", 0) >= start]
    return "\n".join(clean_block(p.get("text") or "") for p in sorted(pages, key=lambda p: p.get("pg", 0)))


def _entries(full: str, limit: int) -> list[str]:
    bounds = [m for m in _BOUNDARY.finditer(full) if m.group(1) is not None]
    out: list[str] = []
    for i, m in enumerate(bounds[:limit]):
        end = bounds[i + 1].start() if i + 1 < len(bounds) else len(full)
        out.append(full[m.start():end].strip())
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Print sample tarājim from a رجال source book.")
    ap.add_argument("book_id", type=int)
    ap.add_argument("--entries", type=int, default=5, help="dump the first N full tarājim")
    ap.add_argument("--find", type=str, default=None, help="dump the tarjama containing this text")
    ap.add_argument("--pages", type=str, default=None, help="dump cleaned text of a page range A-B")
    ap.add_argument("--window", type=int, default=1600, help="chars around a --find hit")
    ap.add_argument("--out", type=Path, default=None, help="write the dump here (to upload) instead of stdout")
    args = ap.parse_args()

    path = asyncio.run(_ensure(args.book_id))
    data = json.loads(path.read_text(encoding="utf-8"))
    chunks: list[str] = [f"# {data.get('name', args.book_id)}  (id {args.book_id}, {len(data.get('pages', []))} pages)\n"]

    if args.pages:
        lo, _, hi = args.pages.partition("-")
        lo, hi = int(lo), int(hi or lo)
        for p in sorted(data.get("pages", []), key=lambda p: p.get("pg", 0)):
            if lo <= p.get("pg", 0) <= hi:
                chunks.append(f"── page {p.get('pg')} ──\n{clean_block(p.get('text') or '')}")
    elif args.find:
        full = _full_text(data)
        idx = full.find(args.find)
        if idx < 0:
            chunks.append(f"«{args.find}» not found in the body text.")
        else:
            lo = full.rfind("\n", 0, max(0, idx - 200)) + 1
            chunks.append(full[lo: idx + args.window])
    else:
        for n, tarjama in enumerate(_entries(_full_text(data), args.entries), 1):
            chunks.append(f"── tarjama {n} ──\n{tarjama}")

    text = "\n\n".join(chunks)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {len(text)} chars → {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()

"""CLI to download the hadith corpus from turath.io (resumable, rate-limited).

Examples
--------
    # See what's in the hadith categories (no download):
    python -m scripts.ingest --list-categories

    # Seed the canonical collections (Bukhari, Muslim, the Sunan, ...):
    python -m scripts.ingest --priority

    # Smoke test: 3 pages of Sahih al-Bukhari:
    python -m scripts.ingest --books 1284 --limit-pages 3

    # Full hadith-sciences crawl (long — ~2.9M pages; resumable):
    python -m scripts.ingest --categories 6 7 8 9 10 26
"""

from __future__ import annotations

import argparse
import asyncio

from app.config import get_settings
from app.ingestion.catalog import Catalog
from app.ingestion.downloader import CorpusDownloader
from app.ingestion.turath_client import TurathClient


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Download hadith books from turath.io")
    parser.add_argument("--books", type=int, nargs="*", help="explicit book ids to fetch")
    parser.add_argument(
        "--categories", type=int, nargs="*",
        help=f"category ids (default hadith set: {list(settings.hadith_category_ids)})",
    )
    parser.add_argument(
        "--priority", action="store_true",
        help="seed the curated core collections first",
    )
    parser.add_argument(
        "--with-commentaries", action="store_true",
        help="also fetch the curated شروح (scholarly explanations) of the collections",
    )
    parser.add_argument(
        "--limit-pages", type=int, default=None,
        help="cap pages per book (smoke testing)",
    )
    parser.add_argument("--rate", type=float, default=settings.turath_rate_per_sec)
    parser.add_argument(
        "--list-categories", action="store_true",
        help="print hadith categories with book/page counts and exit",
    )
    return parser


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    async with TurathClient(
        settings.turath_api_base,
        settings.turath_files_base,
        rate_per_sec=args.rate,
        max_retries=settings.turath_max_retries,
        timeout=settings.turath_timeout,
        user_agent=settings.turath_user_agent,
    ) as client:
        downloader = CorpusDownloader(client, settings.raw_dir, on_progress=print)
        print("Fetching catalog (data-v3.json)…")
        catalog = Catalog.from_raw(await downloader.download_catalog())
        print(f"Catalog: {len(catalog.books)} books, {len(catalog.cats)} categories.")

        if args.list_categories:
            for cid in settings.hadith_category_ids:
                cat = catalog.cats.get(cid)
                if not cat:
                    continue
                books = catalog.books_in_categories([cid])
                pages = catalog.total_pages(books)
                print(f"  {cid:>3} | books={len(books):>5} pages={pages:>9} | {cat.name}")
            return

        # Resolve the download selection.
        cat_ids = args.categories
        if not args.books and not args.priority and cat_ids is None:
            cat_ids = list(settings.hadith_category_ids)  # sensible default
        books = catalog.select(
            book_ids=args.books,
            cat_ids=cat_ids,
            priority=args.priority,
            with_commentaries=args.with_commentaries,
        )

        if not books:
            print("Nothing selected.")
            return
        total_pages = catalog.total_pages(books)
        capped = min(total_pages, len(books) * args.limit_pages) if args.limit_pages else total_pages
        est_seconds = capped / args.rate if args.rate else 0
        print(
            f"Selected {len(books)} books (~{total_pages:,} pages; "
            f"~{capped:,} to fetch, est ~{est_seconds / 3600:.1f}h at {args.rate}/s)."
        )
        await downloader.download_books(books, max_pages_per_book=args.limit_pages)
        print("Done. Progress saved to manifest.json — rerun to resume/extend.")


def main() -> None:
    asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    main()

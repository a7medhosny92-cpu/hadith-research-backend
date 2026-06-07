"""Build the full رجال (narrator) gradings for /verify-isnad.

Downloads the terse رجال source books (تقريب التهذيب — the men of the Six Books, one
graded entry each), extracts a narrator record per tarjama, drops the ones the curated
seed already covers, and writes the result to ``data/rijal.jsonl``::

    python -m scripts.build_rijal                    # download + extract + write
    python -m scripts.build_rijal --books 8609 2171  # choose source book ids
    python -m scripts.build_rijal --input extra.jsonl  # also merge a hand-made JSONL

``/verify-isnad`` auto-loads ``data/rijal.jsonl`` (on top of the bundled seed) the next
time the app starts — no env var needed. With it in place, isnad verdicts become
decisive instead of «يُتوقَّف فيه», since nearly every narrator is now known.

Each record: ``{"name", "kunya", "grade", "death_year", "source"}``; ``grade`` is the
critic's verdict text, which app.rijal.grades classifies into a category/rank.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from pathlib import Path

from app.config import get_settings
from app.ingestion.catalog import RIJAL_SOURCES, Catalog
from app.ingestion.downloader import CorpusDownloader
from app.ingestion.turath_client import TurathClient
from app.parsing.rijal_extract import parse_rijal_file
from app.rijal.grades import classify
from app.rijal.index import RijalIndex, _clean_tokens, load_seed


async def _ensure_downloaded(book_ids: list[int]) -> None:
    """Download any rijal source books not already present (resumable, polite)."""
    settings = get_settings()
    have = {int(p.stem) for p in (settings.raw_dir / "books").glob("*.json")}
    missing = [b for b in book_ids if b not in have]
    if not missing:
        return
    async with TurathClient(
        settings.turath_api_base, settings.turath_files_base,
        rate_per_sec=settings.turath_rate_per_sec, max_retries=settings.turath_max_retries,
        timeout=settings.turath_timeout, user_agent=settings.turath_user_agent,
    ) as client:
        downloader = CorpusDownloader(client, settings.raw_dir, on_progress=print)
        print("Fetching catalog…")
        catalog = Catalog.from_raw(await downloader.download_catalog())
        records = [catalog.books[b] for b in missing if b in catalog.books]
        if records:
            await downloader.download_books(records)


def dedupe_against_seed(records: list[dict]) -> list[dict]:
    """Drop only narrators whose name is *textually identical* to a seed name/alias —
    a true duplicate, which could otherwise tie with the seed and look مشترك. We compare
    folded token *sets*, so namesakes that add a nisba (a weak grandson sharing a
    Companion's name) keep their own — distinct — gradings."""
    seed_sets = {
        frozenset(toks)
        for entry in load_seed()
        for form in (entry.get("name", ""), *(entry.get("aliases") or []))
        if (toks := _clean_tokens(form))
    }
    kept, dropped = [], 0
    for record in records:
        if frozenset(_clean_tokens(record.get("name", ""))) in seed_sets:
            dropped += 1
            continue
        kept.append(record)
    if dropped:
        print(f"(deduped {dropped} narrators already in the curated seed)")
    return kept


def _graded(grade: str | None) -> bool:
    return classify(grade or "")[1] is not None


def _covered(index: RijalIndex, name: str) -> bool:
    match = index.lookup(name)
    return bool(match and match.score >= 1.0 and not match.ambiguous)


def _short(source: str) -> str:
    """The bare book name without the «(رقم …)» suffix — e.g. «تقريب التهذيب»."""
    return re.sub(r"\s*\(رقم.*", "", source or "").strip() or "غير معروف"


def _opinion(source: str, grade_raw: str) -> dict:
    return {"source": _short(source), "grade": classify(grade_raw)[0]}


def _add_opinion(record: dict, source: str, grade_raw: str) -> None:
    """Record a critic's verdict on a narrator (one per source) — the «double opinion»."""
    op = _opinion(source, grade_raw)
    ops = record.setdefault("opinions", [])
    if not any(o["source"] == op["source"] for o in ops):
        ops.append(op)


def merge_source(primary: list[dict], secondary: list[dict]) -> tuple[list[dict], int, int]:
    """Fold a *secondary* رجال source (e.g. الكاشف) into ``primary`` (تقريب, the
    authority) without ever creating a duplicate — which would make a shared name look
    مشترك. A secondary record is used only to:

      * **grade** a primary narrator that primary left ungraded (al-Dhahabi fills a gap), or
      * **add** a narrator that primary doesn't have at all.

    Records the secondary book itself leaves ungraded are skipped (no value). Returns
    ``(records, added, upgraded)``."""
    seed_index = RijalIndex(load_seed())
    index = RijalIndex(primary)
    by_name = {r["name"]: r for r in primary}
    added = upgraded = 0
    for record in secondary:
        if not _graded(record.get("grade")):
            continue
        if _covered(seed_index, record["name"]):
            continue
        match = index.lookup(record["name"])
        if match and match.score >= 1.0 and not match.ambiguous:
            existing = by_name.get(match.entry.name)
            if existing is None:
                continue
            _add_opinion(existing, record.get("source", ""), record["grade"])  # keep both views
            if not _graded(existing.get("grade")):
                existing["grade"] = record["grade"]      # fill the gap with al-Dhahabi
                existing["source"] = f"{existing.get('source', '')} + {record.get('source', '')}".strip(" +")
                upgraded += 1
            # otherwise primary already grades him — primary is the standard for the verdict
        else:
            record["opinions"] = [_opinion(record.get("source", ""), record["grade"])]
            primary.append(record)                       # a narrator primary didn't have
            index.add([record])
            by_name[record["name"]] = record
            added += 1
    return primary, added, upgraded


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Build the full رجال JSONL for /verify-isnad")
    parser.add_argument("--books", type=int, nargs="*", default=list(RIJAL_SOURCES),
                        help=f"source book ids (default: {list(RIJAL_SOURCES)})")
    parser.add_argument("--input", type=Path, help="also merge a hand-made narrator JSONL")
    parser.add_argument("--output", type=Path, default=settings.data_dir / "rijal.jsonl")
    parser.add_argument("--no-download", action="store_true",
                        help="don't fetch missing source books, use what's on disk")
    args = parser.parse_args()

    if not args.no_download:
        asyncio.run(_ensure_downloaded(args.books))

    books_dir = settings.raw_dir / "books"
    extracted: list[list[dict]] = []   # one list per source, in order (first = authority)
    for book_id in args.books:
        path = books_dir / f"{book_id}.json"
        if not path.exists():
            print(f"skip {book_id}: not downloaded")
            continue
        records = parse_rijal_file(path)
        extracted.append(records)
        print(f"book {book_id}: {len(records)} narrators ({RIJAL_SOURCES.get(book_id, '')})")

    if not extracted:
        print("No رجال source books found. Run with network access to download تقريب التهذيب.")
        return

    # تقريب (the first source) is the authority; fold in the rest as gap-fillers.
    result = dedupe_against_seed(extracted[0])
    for r in result:                       # record each narrator's own (authority) opinion
        _add_opinion(r, r.get("source", ""), r["grade"])
    for records in extracted[1:]:
        result, added, upgraded = merge_source(result, records)
        print(f"  merged a secondary source: +{added} new narrators, {upgraded} gaps graded")

    if args.input and args.input.exists():
        extra = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
        result, added, upgraded = merge_source(result, extra)
        print(f"  merged --input: +{added} new, {upgraded} gaps graded")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        for record in result:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    distribution = Counter(classify(r.get("grade") or "")[0] for r in result)
    seed_n = len(load_seed())
    print(f"\nwrote {len(result)} narrators → {args.output}")
    print(f"(+ {seed_n} from the bundled seed = {len(result) + seed_n} graded narrators total)")
    for category, count in distribution.most_common():
        print(f"  {category}: {count}")
    print("\n/verify-isnad will use this automatically on the next app start.")


if __name__ == "__main__":
    main()

"""Parse downloaded turath books into structured hadith records (JSONL).

    python -m scripts.parse                 # parse every downloaded book
    python -m scripts.parse --books 1284    # parse specific books

Output: ``{DATA_DIR}/processed/{book_id}.jsonl`` (one hadith per line). This is the
intermediate the indexing/DB-load phase consumes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.ingestion.catalog import RIJAL_PROSE_BOOKS, RIJAL_SOURCES
from app.parsing.hadith_extract import parse_book_file
from app.parsing.sharh_extract import SHARH_TO_BASE, parse_sharh_file

# Collections that are ṣaḥīḥ by scholarly convention — applied when no inline grade
# is found in the text. (Extend as more collections are seeded.)
SAHIH_BY_DEFAULT: dict[int, str] = {1284: "صحيح", 1727: "صحيح"}


def _is_sharh(path: Path, book_id: int) -> bool:
    """A commentary book — cat 7 (شروح الحديث) or one of the curated شروح."""
    if book_id in SHARH_TO_BASE:
        return True
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("cat_id") == 7
    except (json.JSONDecodeError, OSError):
        return False


def _dump(records: list, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse downloaded books into JSONL")
    parser.add_argument("--books", type=int, nargs="*", help="book ids (default: all downloaded)")
    args = parser.parse_args()

    settings = get_settings()
    books_dir = settings.raw_dir / "books"
    out_dir = settings.processed_dir
    sharh_dir = out_dir / "sharh"  # kept separate so the hadith index ignores it

    book_ids = args.books or sorted(int(p.stem) for p in books_dir.glob("*.json"))
    if not book_ids:
        print("No downloaded books found. Run `python -m scripts.ingest` first.")
        return

    # optional: a faithful LLM re-segmentation for the chains the regex mis-split (matn leaked into
    # the terminal narrator). Gated — without scripts.build_rijal_llm the parse is unchanged.
    llm_chains = None
    llm_chains_path = settings.data_dir / "chains_llm.jsonl"
    if llm_chains_path.exists():
        from app.rijal.llm_source import load_llm_chains
        llm_chains = load_llm_chains(llm_chains_path)
        print(f"LLM chains: {len(llm_chains)} faithful re-segmentations will override the regex split")

    for book_id in book_ids:
        path = books_dir / f"{book_id}.json"
        if not path.exists():
            print(f"skip {book_id}: not downloaded")
            continue
        if book_id in RIJAL_SOURCES:
            # A terse رجال biography book, not hadith — handled by scripts.build_rijal so it
            # doesn't pollute the hadith index. Skip it here.
            print(f"skip {book_id}: رجال source ({RIJAL_SOURCES[book_id]}) → scripts.build_rijal")
            continue
        if book_id in RIJAL_PROSE_BOOKS:
            # A verbose رجال biography (تهذيب الكمال / التهذيب) — also not hadith. No terse
            # extractor for it yet, so just keep it out of the hadith index.
            print(f"skip {book_id}: رجال (prose) ({RIJAL_PROSE_BOOKS[book_id]}) — not hadith")
            continue
        if _is_sharh(path, book_id):
            passages = parse_sharh_file(path)
            _dump(passages, sharh_dir / f"{book_id}.jsonl")
            linked = sum(1 for p in passages if p.hadith_number is not None)
            print(f"sharh {book_id}: {len(passages)} passages ({linked} hadith-linked) → sharh/")
        else:
            hadiths = parse_book_file(path, default_grade=SAHIH_BY_DEFAULT.get(book_id),
                                      llm_chains=llm_chains)
            _dump(hadiths, out_dir / f"{book_id}.jsonl")
            with_matn = sum(1 for h in hadiths if h.matn)
            print(f"book {book_id}: {len(hadiths)} hadith ({with_matn} with matn)")


if __name__ == "__main__":
    main()

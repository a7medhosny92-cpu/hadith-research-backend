"""Build the lexical search index from parsed JSONL.

    python -m scripts.index     # (re)build {DATA_DIR}/index.db from {DATA_DIR}/processed

The API serves search from this file when present; otherwise it builds an in-memory
index from the JSONL on first request (handy in dev).
"""

from __future__ import annotations

import time

from app.config import get_settings
from app.search import HadithIndex


def main() -> None:
    settings = get_settings()
    processed = settings.processed_dir
    if not processed.exists() or not any(processed.glob("*.jsonl")):
        print("No parsed JSONL found. Run `python -m scripts.parse` first.")
        return

    db = settings.index_path
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()  # rebuild from scratch for a clean index

    started = time.time()
    index = HadithIndex.build_from_processed(processed, db)
    print(f"Indexed {index.count()} hadith → {db} in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()

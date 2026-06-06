"""Build the semantic (vector) index for hybrid search.

    python -m scripts.embed            # embed every hadith in the lexical index
    python -m scripts.embed --batch 128

Reads hadith straight from the prebuilt lexical index ({DATA_DIR}/index.db) so the
vector store shares its row ids, then writes dense vectors to {DATA_DIR}/vectors.db.
Uses the configured Arabic model when the ``embeddings`` extra (sentence-transformers
+ torch) is installed; otherwise a stdlib hashing baseline keeps the pipeline live.

Run after `scripts.index`. Re-run anytime to rebuild (idempotent). On a CPU-only
laptop the first run takes a while (one-off); search then embeds only the query.
"""

from __future__ import annotations

import argparse
import time

from app.config import get_settings
from app.search import HadithIndex
from app.search.embeddings import load_embedder
from app.search.vectors import VectorIndex
from scripts._atomic import rebuild


def main() -> None:
    ap = argparse.ArgumentParser(description="Embed the hadith corpus for semantic search.")
    ap.add_argument("--batch", type=int, default=128, help="texts encoded per batch")
    args = ap.parse_args()

    settings = get_settings()
    if not settings.index_path.exists():
        print("No lexical index found. Run `python -m scripts.index` first.")
        return

    lexical = HadithIndex(settings.index_path)
    total = lexical.count()
    if not total:
        print("Lexical index is empty — nothing to embed.")
        return

    embedder = load_embedder(settings)
    print(f"Embedder: {type(embedder).__name__} (dim={embedder.dim}); {total} hadith to embed.")
    started = time.time()

    def build(tmp):
        vectors = VectorIndex(tmp, dim=embedder.dim)
        ids: list[int] = []
        texts: list[str] = []
        done = 0

        def flush() -> None:
            nonlocal done
            if not texts:
                return
            vectors.add(ids, embedder.embed(texts))
            done += len(texts)
            print(f"  embedded {done}/{total} ({done * 100 // total}%)", end="\r")
            ids.clear()
            texts.clear()

        for rowid, text in lexical.iter_for_embedding():
            ids.append(rowid)
            texts.append(text)
            if len(texts) >= args.batch:
                flush()
        flush()
        return vectors

    n = rebuild(settings.vector_index_path, build)
    print(f"\nIndexed {n} vectors → {settings.vector_index_path} in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()

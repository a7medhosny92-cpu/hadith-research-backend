"""Build the semantic (vector) index for hybrid search — incrementally.

    python -m scripts.embed              # embed new/changed matns, reuse the rest
    python -m scripts.embed --batch 128
    python -m scripts.embed --seed-cache # seed the cache from an existing vectors.db
    python -m scripts.embed --no-cache   # force a full re-embed (ignore the cache)

Reads hadith from the prebuilt lexical index ({DATA_DIR}/index.db) so the vector store
shares its row ids, then writes dense vectors to {DATA_DIR}/vectors.db.

Embedding the whole corpus is the slow step (hours on CPU). Because re-indexing assigns
fresh row ids, we key a persistent cache ({DATA_DIR}/embed_cache.db) by a hash of the
*embedding text* (and the model), so a re-run only embeds matns whose text actually
changed and reuses every vector for unchanged text. Run `--seed-cache` once on an
existing vectors.db to populate the cache without re-embedding, so the next update is fast.

Run after `scripts.index`. Uses the configured Arabic model when the ``embeddings`` extra
is installed; otherwise a stdlib hashing baseline keeps the pipeline live.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import time
from array import array
from pathlib import Path

from app.config import Settings, get_settings
from app.search import HadithIndex
from app.search.embeddings import load_embedder
from app.search.vectors import VectorIndex
from scripts._atomic import rebuild


def _digester(model: str, dim: int):
    """A hash of (model, dim, text) — keys the cache so a different model/text misses."""
    tag = f"{model}:{dim}".encode("utf-8")
    return lambda text: hashlib.sha1(tag + b"\0" + text.encode("utf-8")).hexdigest()


def _open_cache(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE IF NOT EXISTS vec (h TEXT PRIMARY KEY, v BLOB NOT NULL)")
    return con


def _cache_lookup(con: sqlite3.Connection, hashes: list[str]) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for i in range(0, len(hashes), 900):                       # sqlite parameter cap
        chunk = hashes[i:i + 900]
        q = "SELECT h, v FROM vec WHERE h IN (%s)" % ",".join("?" * len(chunk))
        out.update(con.execute(q, chunk).fetchall())
    return out


def seed_cache(settings: Settings) -> int:
    """Populate the embed cache from an existing (consistent) vectors.db — no embedding."""
    if not settings.index_path.exists() or not settings.vector_index_path.exists():
        print("Need both index.db and vectors.db to seed the cache.")
        return 0
    vcon = sqlite3.connect(str(settings.vector_index_path))
    sample = vcon.execute("SELECT v FROM vec LIMIT 1").fetchone()
    if not sample:
        print("vectors.db is empty — nothing to seed.")
        return 0
    dim = len(sample[0]) // 4
    digest = _digester(settings.embedding_model, dim)
    by_id = dict(vcon.execute("SELECT id, v FROM vec"))
    cache = _open_cache(settings.embed_cache_path)
    seeded = 0
    for rowid, text in HadithIndex(settings.index_path).iter_for_embedding():
        blob = by_id.get(rowid)
        if blob is not None:
            cache.execute("INSERT OR REPLACE INTO vec (h, v) VALUES (?, ?)", (digest(text), blob))
            seeded += 1
    cache.commit()
    cache.close()
    print(f"Seeded {seeded} vectors into {settings.embed_cache_path} — the next embed will "
          "reuse every unchanged matn.")
    return seeded


def embed_corpus(settings: Settings, *, batch: int = 128, use_cache: bool = True) -> tuple[int, int, int]:
    """(Re)build vectors.db, embedding only new/changed texts. Returns (total, new, reused)."""
    lexical = HadithIndex(settings.index_path)
    total = lexical.count()
    embedder = load_embedder(settings)
    digest = _digester(settings.embedding_model, embedder.dim)
    cache = _open_cache(settings.embed_cache_path) if use_cache else None
    counts = {"new": 0, "reused": 0, "done": 0}

    def build(tmp):
        vectors = VectorIndex(tmp, dim=embedder.dim)
        buf: list[tuple[int, str, str]] = []

        def process() -> None:
            if not buf:
                return
            have = _cache_lookup(cache, [h for _, _, h in buf]) if cache else {}
            ids: list[int] = []
            vecs: list[array] = []
            for rid, _, h in buf:
                if h in have:
                    a = array("f"); a.frombytes(have[h]); ids.append(rid); vecs.append(a)
                    counts["reused"] += 1
            miss = [(rid, text, h) for rid, text, h in buf if h not in have]
            if miss:
                for (rid, _, h), v in zip(miss, embedder.embed([t for _, t, _ in miss])):
                    blob = array("f", v).tobytes()
                    if cache is not None:
                        cache.execute("INSERT OR REPLACE INTO vec (h, v) VALUES (?, ?)", (h, blob))
                    a = array("f"); a.frombytes(blob); ids.append(rid); vecs.append(a)
                    counts["new"] += 1
                if cache is not None:
                    cache.commit()
            vectors.add(ids, vecs)
            counts["done"] += len(buf)
            print(f"  {counts['done']}/{total} ({counts['done'] * 100 // total}%) "
                  f"— embedded {counts['new']}, reused {counts['reused']}", end="\r")
            buf.clear()

        for rowid, text in lexical.iter_for_embedding():
            buf.append((rowid, text, digest(text)))
            if len(buf) >= batch:
                process()
        process()
        return vectors

    rebuild(settings.vector_index_path, build)
    if cache is not None:
        cache.close()
    return total, counts["new"], counts["reused"]


def main() -> None:
    ap = argparse.ArgumentParser(description="Embed the hadith corpus for semantic search.")
    ap.add_argument("--batch", type=int, default=128, help="texts encoded per batch")
    ap.add_argument("--seed-cache", action="store_true",
                    help="populate the cache from an existing vectors.db, then exit (no embedding)")
    ap.add_argument("--no-cache", action="store_true", help="ignore the cache and embed everything")
    args = ap.parse_args()

    settings = get_settings()
    if not settings.index_path.exists():
        print("No lexical index found. Run `python -m scripts.index` first.")
        return
    if args.seed_cache:
        seed_cache(settings)
        return

    embedder = load_embedder(settings)
    total = HadithIndex(settings.index_path).count()
    if not total:
        print("Lexical index is empty — nothing to embed.")
        return
    print(f"Embedder: {type(embedder).__name__} (dim={embedder.dim}); {total} hadith "
          f"({'incremental' if not args.no_cache else 'full re-embed'}).")
    started = time.time()
    n, new, reused = embed_corpus(settings, batch=args.batch, use_cache=not args.no_cache)
    print(f"\nIndexed {n} vectors → {settings.vector_index_path} "
          f"(embedded {new}, reused {reused}) in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()

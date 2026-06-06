"""Dense-vector index for semantic hadith search (dev backend).

Pairs with the lexical :class:`~app.search.index.HadithIndex`: both assign the same
sequential row ids (built from the same JSONL in the same order), so a vector hit's
id looks up the full record in the lexical store. Vectors are **L2-normalised**, so
cosine similarity is a plain dot product.

Storage is sqlite (float32 blobs); for search the vectors are loaded into memory
once and scored brute-force — with numpy when it's installed (fast), else a pure
stdlib path so the pipeline runs anywhere. In production this role is played by
PostgreSQL + pgvector; the interface here mirrors what that backend will expose.
"""

from __future__ import annotations

import heapq
import sqlite3
from array import array
from pathlib import Path
from typing import Sequence

from app.search.embeddings import cosine

_SCHEMA = "CREATE TABLE IF NOT EXISTS vec (id INTEGER PRIMARY KEY, v BLOB NOT NULL);"


class VectorIndex:
    """An id→vector store with top-k cosine search over L2-normalised vectors."""

    def __init__(self, db_path: str | Path = ":memory:", *, dim: int | None = None) -> None:
        self._con = sqlite3.connect(str(db_path), check_same_thread=False)
        self._con.executescript(_SCHEMA)
        self.dim = dim
        self._ids: list[int] | None = None      # row ids, aligned to…
        self._rows: list[array] | None = None    # …their float32 vectors
        self._np = None                          # numpy matrix cache, if available

    # ── building ────────────────────────────────────────────────────────────────
    def add(self, ids: Sequence[int], vectors: Sequence[Sequence[float]]) -> int:
        rows = [(int(i), array("f", v).tobytes()) for i, v in zip(ids, vectors)]
        if rows and self.dim is None:
            self.dim = len(vectors[0])
        self._con.executemany("INSERT OR REPLACE INTO vec (id, v) VALUES (?, ?)", rows)
        self._con.commit()
        self._ids = self._rows = self._np = None  # invalidate the in-memory cache
        return len(rows)

    # ── querying ────────────────────────────────────────────────────────────────
    def _ensure_loaded(self) -> None:
        if self._ids is not None:
            return
        ids: list[int] = []
        rows: list[array] = []
        for rid, blob in self._con.execute("SELECT id, v FROM vec ORDER BY id"):
            ids.append(rid)
            vec = array("f")
            vec.frombytes(blob)
            rows.append(vec)
        self._ids, self._rows = ids, rows
        if rows and self.dim is None:
            self.dim = len(rows[0])
        try:
            import numpy as np  # optional: only to speed up scoring

            self._np = np.array(rows, dtype="float32") if rows else None
        except Exception:  # noqa: BLE001 — pure-Python path below
            self._np = None

    def search(self, query_vec: Sequence[float], k: int = 20) -> list[tuple[int, float]]:
        """Return up to ``k`` ``(id, score)`` pairs, most similar first."""
        self._ensure_loaded()
        if not self._ids:
            return []
        if self._np is not None:
            import numpy as np

            q = np.asarray(query_vec, dtype="float32")
            scores = self._np @ q
            k = min(k, scores.shape[0])
            top = np.argpartition(-scores, k - 1)[:k]
            top = top[np.argsort(-scores[top])]
            return [(self._ids[i], float(scores[i])) for i in top]
        scored = ((cosine(query_vec, vec), rid) for rid, vec in zip(self._ids, self._rows))
        return [(rid, score) for score, rid in heapq.nlargest(k, scored)]

    def count(self) -> int:
        return self._con.execute("SELECT count(*) FROM vec").fetchone()[0]

    def vectors_for(self, ids: Sequence[int]) -> dict[int, list[float]]:
        """Return ``{id: vector}`` for the given ids — for pairwise similarity (clustering)."""
        ids = list(ids)
        if not ids:
            return {}
        out: dict[int, list[float]] = {}
        placeholders = ",".join("?" * len(ids))
        for rid, blob in self._con.execute(
            f"SELECT id, v FROM vec WHERE id IN ({placeholders})", ids
        ):
            vec = array("f")
            vec.frombytes(blob)
            out[rid] = vec.tolist()
        return out

    def close(self) -> None:
        self._con.close()

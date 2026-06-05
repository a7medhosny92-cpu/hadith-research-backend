"""Lexical hadith search over the parsed corpus.

The :class:`HadithIndex` interface is storage-agnostic. The dev/default backend is
**sqlite FTS5** — zero extra dependencies and Arabic-aware because we feed it
text already folded by :func:`app.parsing.normalize.normalize_for_search` (drop
tashkeel, unify alef/hamza/ya/ta-marbuta). In production the same interface is
meant to be backed by PostgreSQL + pgvector for hybrid lexical + semantic search.

Why pre-normalise instead of leaning on the tokenizer: FTS5's ``remove_diacritics``
does not handle Classical-Arabic letter folding (إ/أ/آ→ا, ى→ي, ة→ه), so queries
would miss obvious matches. We store a folded ``*_norm`` column for matching and
keep the original (diacritised) text for display and citation.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from app.ingestion.catalog import CORE_COLLECTIONS
from app.parsing.normalize import normalize_for_search

#: book id → display name for citations (the canonical collections).
COLLECTION_NAMES: dict[int, str] = dict(CORE_COLLECTIONS)

# FTS5 query operator characters we must neutralise in user input.
_FTS_SPECIAL = str.maketrans({c: " " for c in '"*()^:-'})

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS hadith USING fts5(
    matn_norm, isnad_norm,
    book_id     UNINDEXED,
    collection  UNINDEXED,
    number      UNINDEXED,
    matn        UNINDEXED,
    isnad       UNINDEXED,
    grade       UNINDEXED,
    chapter     UNINDEXED,
    page        UNINDEXED,
    volume      UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


@dataclass(slots=True)
class SearchHit:
    id: int                # index rowid (stable within a built index)
    book_id: int
    collection: str
    number: int | None
    matn: str
    isnad: str
    grade: str | None
    chapter: str | None
    page: int | None
    volume: str | None
    score: float           # higher = better (negated bm25)
    snippet: str           # matched matn fragment, match wrapped in «…»

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "book_id": self.book_id,
            "collection": self.collection,
            "number": self.number,
            "matn": self.matn,
            "isnad": self.isnad,
            "grade": self.grade,
            "chapter": self.chapter,
            "page": self.page,
            "volume": self.volume,
            "score": round(self.score, 4),
            "snippet": self.snippet,
        }


def _tokens(query: str) -> list[str]:
    return [t for t in normalize_for_search(query.translate(_FTS_SPECIAL)).split() if t]


class HadithIndex:
    """An FTS5-backed hadith index. Use :meth:`build_from_processed` to load the
    parsed JSONL corpus, or :meth:`add` to insert records directly (tests)."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        # check_same_thread=False: read-only FTS queries are served from FastAPI's
        # threadpool. (Production uses PostgreSQL, where this is a non-issue.)
        self._con = sqlite3.connect(str(db_path), check_same_thread=False)
        self._con.executescript(_SCHEMA)

    # ── building ──────────────────────────────────────────────────────────────
    def add(self, records: Iterable[dict]) -> int:
        rows = []
        for r in records:
            matn = r.get("matn") or ""
            isnad = r.get("isnad") or ""
            book_id = r.get("book_id")
            rows.append(
                (
                    normalize_for_search(matn),
                    normalize_for_search(isnad),
                    book_id,
                    COLLECTION_NAMES.get(book_id, str(book_id)),
                    r.get("number"),
                    matn,
                    isnad,
                    r.get("grade"),
                    r.get("chapter"),
                    r.get("page"),
                    r.get("volume"),
                )
            )
        self._con.executemany(
            "INSERT INTO hadith (matn_norm, isnad_norm, book_id, collection, number, "
            "matn, isnad, grade, chapter, page, volume) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        self._con.commit()
        return len(rows)

    @classmethod
    def build_from_processed(
        cls, processed_dir: str | Path, db_path: str | Path = ":memory:"
    ) -> "HadithIndex":
        index = cls(db_path)
        for jsonl in sorted(Path(processed_dir).glob("*.jsonl")):
            index.add(_read_jsonl(jsonl))
        return index

    # ── querying ──────────────────────────────────────────────────────────────
    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        collection_id: int | None = None,
        grade: str | None = None,
        field: str = "matn",
    ) -> list[SearchHit]:
        """Rank hadith by relevance to ``query``.

        Tries an all-terms (AND) match first for precision, then falls back to
        any-term (OR) for recall. ``field`` selects what to search: ``matn`` (the
        text), ``isnad`` (the chain), or ``both``.
        """
        terms = _tokens(query)
        if not terms:
            return []
        col = {"matn": "matn_norm", "isnad": "isnad_norm"}.get(field)
        prefix = f"{col}:" if col else ""  # column filter, or whole-row for "both"

        filters, params = ["hadith MATCH ?"], [""]
        if collection_id is not None:
            filters.append("book_id = ?")
            params.append(collection_id)
        if grade is not None:
            filters.append("grade = ?")
            params.append(grade)
        sql = (
            "SELECT rowid, book_id, collection, number, matn, isnad, grade, chapter, "
            "page, volume, -bm25(hadith) AS score, "
            "snippet(hadith, 0, '«', '»', '…', 12) AS snip "
            f"FROM hadith WHERE {' AND '.join(filters)} ORDER BY score DESC LIMIT ?"
        )
        for joiner in (" AND ", " OR "):
            params[0] = prefix + (joiner.join(f'"{t}"' for t in terms))
            rows = self._con.execute(sql, [*params, limit]).fetchall()
            if rows or joiner == " OR ":
                return [_hit(row) for row in rows]
        return []

    def get(self, hadith_id: int) -> SearchHit | None:
        row = self._con.execute(
            "SELECT rowid, book_id, collection, number, matn, isnad, grade, chapter, "
            "page, volume, 0.0 AS score, '' AS snip FROM hadith WHERE rowid = ?",
            (hadith_id,),
        ).fetchone()
        return _hit(row) if row else None

    def count(self) -> int:
        return self._con.execute("SELECT count(*) FROM hadith").fetchone()[0]

    def close(self) -> None:
        self._con.close()


def _read_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _hit(row: tuple) -> SearchHit:
    return SearchHit(
        id=row[0], book_id=row[1], collection=row[2], number=row[3], matn=row[4],
        isnad=row[5], grade=row[6], chapter=row[7], page=row[8], volume=row[9],
        score=row[10], snippet=row[11],
    )

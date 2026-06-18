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
    matn_norm, chapter_norm, isnad_norm,
    book_id     UNINDEXED,
    collection  UNINDEXED,
    number      UNINDEXED,
    matn        UNINDEXED,
    isnad       UNINDEXED,
    grade       UNINDEXED,
    chapter     UNINDEXED,
    page        UNINDEXED,
    volume      UNINDEXED,
    kind        UNINDEXED,
    sort        UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

#: bm25 column weights (matn_norm, chapter_norm, isnad_norm): the matn matters most,
#: the chapter heading helps topical queries, the chain least.
_HADITH_WEIGHTS = "10.0, 4.0, 1.0"

_SHARH_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS sharh USING fts5(
    text_norm,
    book_id       UNINDEXED,
    sharh_name    UNINDEXED,
    base_id       UNINDEXED,
    base_name     UNINDEXED,
    hadith_number UNINDEXED,
    chapter       UNINDEXED,
    page          UNINDEXED,
    page_id       UNINDEXED,
    text          UNINDEXED,
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
    kind: str = "hadith"   # "hadith" | "taliq" (a باب with only a تعليق/أثر — no isnad, no number)

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
            "kind": self.kind,
        }


def _tokens(query: str) -> list[str]:
    return [t for t in normalize_for_search(query.translate(_FTS_SPECIAL)).split() if t]


def _chunks(text: str, size: int = 1400) -> list[str]:
    """Split long commentary into ~``size``-char pieces at sentence/space boundaries,
    so retrieval returns a focused passage (one hadith's شرح can run to tens of KB)."""
    text = " ".join(text.split())
    if len(text) <= size:
        return [text] if text else []
    out, i, n = [], 0, len(text)
    while i < n:
        end = min(i + size, n)
        if end < n:
            cut = max(
                text.rfind("۔", i, end), text.rfind(". ", i, end),
                text.rfind("؟", i, end), text.rfind(" ", i, end),
            )
            if cut > i:
                end = cut + 1
        out.append(text[i:end].strip())
        i = end
    return [c for c in out if c]


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
                    normalize_for_search(r.get("chapter") or ""),
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
                    r.get("kind") or "hadith",
                    r.get("sort"),
                )
            )
        self._con.executemany(
            "INSERT INTO hadith (matn_norm, chapter_norm, isnad_norm, book_id, collection, "
            "number, matn, isnad, grade, chapter, page, volume, kind, sort) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
        limit: int | None = 20,
        collection_id: int | None = None,
        grade: str | None = None,
        field: str = "all",
        match: str = "auto",
    ) -> list[SearchHit]:
        """Rank hadith by relevance to ``query``.

        ``match`` controls term combination: ``auto`` tries all-terms (AND) first for
        precision, then falls back to any-term (OR) for recall; ``and`` / ``or`` force
        one. (Takhrij uses ``or`` to surface differently-worded narrations even when a
        verbatim parallel exists.) ``field`` selects what to search: ``all`` (matn +
        chapter + chain, matn weighted highest), ``matn``, or ``isnad``.
        ``limit=None`` returns *every* match (no cap).
        """
        terms = _tokens(query)
        if not terms:
            return []
        col = {"matn": "matn_norm", "isnad": "isnad_norm"}.get(field)
        prefix = f"{col}:" if col else ""  # column filter, or whole-row for "all"

        filters, params = ["hadith MATCH ?", "kind = 'hadith'"], [""]  # «taliq» معلّقات are library-only
        if collection_id is not None:
            filters.append("book_id = ?")
            params.append(collection_id)
        if grade is not None:
            filters.append("grade = ?")
            params.append(grade)
        limit_sql = "" if limit is None else " LIMIT ?"
        sql = (
            "SELECT rowid, book_id, collection, number, matn, isnad, grade, chapter, "
            f"page, volume, -bm25(hadith, {_HADITH_WEIGHTS}) AS score, "
            "snippet(hadith, 0, '«', '»', '…', 12) AS snip, kind "
            f"FROM hadith WHERE {' AND '.join(filters)} ORDER BY score DESC{limit_sql}"
        )
        joiners = {"and": (" AND ",), "or": (" OR ",), "auto": (" AND ", " OR ")}[match]
        for joiner in joiners:
            params[0] = prefix + (joiner.join(f'"{t}"' for t in terms))
            args = [*params] if limit is None else [*params, limit]
            rows = self._con.execute(sql, args).fetchall()
            if rows or joiner == joiners[-1]:
                return [_hit(row, tuple(terms)) for row in rows]
        return []

    def get(self, hadith_id: int) -> SearchHit | None:
        row = self._con.execute(
            "SELECT rowid, book_id, collection, number, matn, isnad, grade, chapter, "
            "page, volume, 0.0 AS score, '' AS snip, kind FROM hadith WHERE rowid = ?",
            (hadith_id,),
        ).fetchone()
        return _hit(row) if row else None

    def count(self) -> int:
        return self._con.execute("SELECT count(*) FROM hadith").fetchone()[0]

    # ── library navigator (collections → chapters → hadiths), for the «الكتب» browse tab ──────────
    def collections(self) -> list[dict]:
        """Every collection present, with its hadith count, in corpus (parse) order."""
        rows = self._con.execute(
            "SELECT book_id, collection, COUNT(*) FROM hadith GROUP BY book_id ORDER BY MIN(rowid)"
        ).fetchall()
        return [{"book_id": b, "collection": c, "count": n} for b, c, n in rows]

    def chapters(self, book_id: int) -> list[dict]:
        """The chapters (كتاب/باب headings) of one collection, in book order, each with its count.

        A chapter recurs on every hadith under it, so we group and order by the FIRST hadith NUMBER in
        it — the hadith number is monotonic in book order (and global across volumes), unlike ``rowid``
        (insertion order, which interleaved the كتب) or ``page`` (which restarts each volume). A «taliq»
        باب (تعليق/أثر, no number) has no number, so it orders by its ``sort`` key (the preceding hadith
        number); ``rowid`` is the final tie-break."""
        rows = self._con.execute(
            "SELECT chapter, COUNT(*) FROM hadith "
            "WHERE book_id = ? AND chapter IS NOT NULL AND chapter <> '' "
            "GROUP BY chapter ORDER BY MIN(COALESCE(CAST(number AS INTEGER), sort)), MIN(rowid)",
            (book_id,),
        ).fetchall()
        return [{"chapter": ch, "count": n} for ch, n in rows]

    def chapter_hadiths(
        self, book_id: int, chapter: str | None = None, *, offset: int = 0, limit: int = 50
    ) -> list[SearchHit]:
        """The hadiths of one collection under ``chapter`` (or the whole book when ``None``), in
        book order, paged — the leaf of the «الكتب» navigator."""
        where, args = "book_id = ?", [book_id]
        if chapter is not None:
            where, args = "book_id = ? AND chapter = ?", [book_id, chapter]
        rows = self._con.execute(
            "SELECT rowid, book_id, collection, number, matn, isnad, grade, chapter, "
            f"page, volume, 0.0 AS score, '' AS snip, kind FROM hadith WHERE {where} "
            "ORDER BY COALESCE(CAST(number AS INTEGER), sort), rowid LIMIT ? OFFSET ?",
            (*args, limit, offset),
        ).fetchall()
        return [_hit(row) for row in rows]

    def iter_for_embedding(self) -> Iterator[tuple[int, str]]:
        """Yield ``(rowid, text)`` for every hadith, in row order, for the vector index.

        Reading ids straight from this index guarantees the vector store shares them,
        so a semantic hit's id resolves back to the full record here. The embedded text
        is the matn plus its chapter heading (light topical context)."""
        for rowid, matn, chapter in self._con.execute(
            "SELECT rowid, matn, chapter FROM hadith ORDER BY rowid"
        ):
            text = " ".join(p for p in (matn, chapter) if p)
            yield rowid, text

    def close(self) -> None:
        self._con.close()


def _read_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _excerpt(matn: str, terms: tuple[str, ...] = (), window: int = 14) -> str:
    """A readable, *original-spelling* excerpt with the match wrapped in «…».

    FTS5's snippet() can only highlight the indexed (folded) column, which would show
    diacritic-stripped Arabic. So we highlight the original matn ourselves: find the
    first word whose folded form carries a query term and frame a window around it."""
    words = (matn or "").split()
    if not words:
        return ""
    hit = next(
        (i for i, w in enumerate(words) if any(t in normalize_for_search(w) for t in terms)),
        None,
    )
    if hit is None:
        return " ".join(words[:window]) + ("…" if len(words) > window else "")
    lo, hi = max(0, hit - window // 2), min(len(words), hit + window // 2 + 1)
    frag = words[lo:hi]
    frag[hit - lo] = f"«{frag[hit - lo]}»"
    return f"{'…' if lo else ''}{' '.join(frag)}{'…' if hi < len(words) else ''}"


def _hit(row: tuple, terms: tuple[str, ...] = ()) -> SearchHit:
    return SearchHit(
        id=row[0], book_id=row[1], collection=row[2], number=row[3], matn=row[4],
        isnad=row[5], grade=row[6], chapter=row[7], page=row[8], volume=row[9],
        score=row[10], snippet=_excerpt(row[4], terms),
        kind=(row[12] if len(row) > 12 else "hadith") or "hadith",
    )


@dataclass(slots=True)
class SharhHit:
    book_id: int
    sharh: str               # commentary title (identifies the commentator)
    base_id: int | None
    base_name: str | None
    hadith_number: int | None
    chapter: str | None
    page: int | None
    page_id: int | None      # anchor page id — identifies the passage (joins its chunks)
    score: float
    excerpt: str             # matched fragment, the hit wrapped in «…» (shows context)
    text: str                # the full passage text (the complete stored chunk)

    def to_dict(self) -> dict:
        return {
            "book_id": self.book_id,
            "sharh": self.sharh,
            "base_id": self.base_id,
            "base_name": self.base_name,
            "hadith_number": self.hadith_number,
            "chapter": self.chapter,
            "page": self.page,
            "page_id": self.page_id,
            "score": round(self.score, 4),
            "excerpt": self.excerpt,
            "text": self.text,
        }


class SharhIndex:
    """FTS5 index over commentary passages, linked to the base collection/hadith.

    Powers /ask's "what the scholars said": search the شرح by question terms,
    optionally constrained to a specific hadith (``base_id`` + ``hadith_number``)."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._con = sqlite3.connect(str(db_path), check_same_thread=False)
        self._con.executescript(_SHARH_SCHEMA)

    def add(self, passages: Iterable[dict]) -> int:
        rows = []
        for p in passages:
            meta = (
                p.get("book_id"), p.get("sharh"), p.get("base_id"), p.get("base_name"),
                p.get("hadith_number"), p.get("chapter"), p.get("page"), p.get("page_id"),
            )
            for chunk in _chunks(p.get("text") or ""):
                rows.append((normalize_for_search(chunk), *meta, chunk))
        self._con.executemany(
            "INSERT INTO sharh (text_norm, book_id, sharh_name, base_id, base_name, "
            "hadith_number, chapter, page, page_id, text) VALUES (?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        self._con.commit()
        return len(rows)

    @classmethod
    def build_from_processed(
        cls, sharh_dir: str | Path, db_path: str | Path = ":memory:", on_progress=None
    ) -> "SharhIndex":
        """Build the شرح index. ``on_progress(name, total_chunks)`` is called after each
        commentary file — this is the long step, so callers can show progress."""
        index = cls(db_path)
        directory = Path(sharh_dir)
        if directory.exists():
            for jsonl in sorted(directory.glob("*.jsonl")):
                index.add(_read_jsonl(jsonl))
                if on_progress is not None:
                    on_progress(jsonl.stem, index.count())
        return index

    def search(
        self,
        query: str,
        *,
        base_id: int | None = None,
        hadith_number: int | None = None,
        limit: int = 5,
    ) -> list[SharhHit]:
        terms = _tokens(query)
        if not terms:
            return []
        filters, params = ["sharh MATCH ?"], [""]
        if base_id is not None:
            filters.append("base_id = ?")
            params.append(base_id)
        if hadith_number is not None:
            filters.append("hadith_number = ?")
            params.append(hadith_number)
        sql = (
            "SELECT book_id, sharh_name, base_id, base_name, hadith_number, chapter, page, "
            "page_id, -bm25(sharh) AS score, snippet(sharh, 0, '«', '»', '…', 24) AS snip, text "
            f"FROM sharh WHERE {' AND '.join(filters)} ORDER BY score DESC LIMIT ?"
        )
        for joiner in (" AND ", " OR "):
            params[0] = joiner.join(f'"{t}"' for t in terms)
            rows = self._con.execute(sql, [*params, limit]).fetchall()
            if rows or joiner == " OR ":
                return [_sharh_hit(row) for row in rows]
        return []

    def by_hadith(self, base_id: int, hadith_number: int, *, limit: int = 3) -> list[SharhHit]:
        """All commentary linked to a hadith, regardless of query (full passage text)."""
        rows = self._con.execute(
            "SELECT book_id, sharh_name, base_id, base_name, hadith_number, chapter, page, "
            "page_id, 0.0 AS score, substr(text, 1, 240) AS snip, text FROM sharh "
            "WHERE base_id = ? AND hadith_number = ? LIMIT ?",
            (base_id, hadith_number, limit),
        ).fetchall()
        return [_sharh_hit(row) for row in rows]

    # ── library navigator (شروح → chapters → passages), for the «الكتب» browse tab ───────────────
    def collections(self) -> list[dict]:
        """Every شرح present, with its base collection and DISTINCT-passage count, in build order."""
        rows = self._con.execute(
            "SELECT book_id, sharh_name, base_id, base_name, COUNT(DISTINCT page_id) "
            "FROM sharh GROUP BY book_id ORDER BY MIN(rowid)"
        ).fetchall()
        return [{"book_id": b, "sharh": s, "base_id": bi, "base_name": bn, "count": n}
                for b, s, bi, bn, n in rows]

    def chapters(self, book_id: int) -> list[dict]:
        """The chapters (كتب/أبواب) of one شرح, in book order, each with its passage count. A شرح
        follows its base collection, so order by the linked hadith NUMBER where present, else rowid."""
        rows = self._con.execute(
            "SELECT chapter, COUNT(DISTINCT page_id) FROM sharh "
            "WHERE book_id = ? AND chapter IS NOT NULL AND chapter <> '' "
            "GROUP BY chapter ORDER BY MIN(CAST(hadith_number AS INTEGER)), MIN(rowid)",
            (book_id,),
        ).fetchall()
        return [{"chapter": ch, "count": n} for ch, n in rows]

    def chapter_passages(
        self, book_id: int, chapter: str | None = None, *, offset: int = 0, limit: int = 20
    ) -> list[dict]:
        """The passages of one شرح under ``chapter`` (or the whole book), in book order, paged — the
        leaf of the «الكتب» navigator. One entry per passage (its chunks rejoined to the full text)."""
        where, args = "book_id = ?", [book_id]
        if chapter is not None:
            where, args = "book_id = ? AND chapter = ?", [book_id, chapter]
        rows = self._con.execute(
            "SELECT page_id, MIN(rowid) AS r, sharh_name, base_id, base_name, hadith_number, chapter, page "
            f"FROM sharh WHERE {where} GROUP BY page_id "
            "ORDER BY MIN(CAST(hadith_number AS INTEGER)), r LIMIT ? OFFSET ?",
            (*args, limit, offset),
        ).fetchall()
        return [
            {"book_id": book_id, "sharh": s, "base_id": bi, "base_name": bn, "hadith_number": hn,
             "chapter": ch, "page": pg, "page_id": pid, "text": self.full_passage(book_id, pid)}
            for pid, _r, s, bi, bn, hn, ch, pg in rows
        ]

    def full_passage(self, book_id: int, page_id: int) -> str:
        """Re-join every chunk of one شرح *passage* — a whole hadith's commentary, or a
        whole chapter's — identified by its anchor ``page_id``.

        A passage is split into ~1400-char chunks at index time for focused retrieval;
        joining them back by their shared anchor returns the complete discourse (and it
        works for by-number editions *and* by-chapter ones, where ``hadith_number`` is
        null), so /ask shows the scholar's full explanation, never a truncated fragment.
        """
        rows = self._con.execute(
            "SELECT text FROM sharh WHERE book_id = ? AND page_id = ? ORDER BY rowid",
            (book_id, page_id),
        ).fetchall()
        return " ".join(r[0] for r in rows if r[0]).strip()

    def count(self) -> int:
        return self._con.execute("SELECT count(*) FROM sharh").fetchone()[0]

    def close(self) -> None:
        self._con.close()


def _sharh_hit(row: tuple) -> SharhHit:
    return SharhHit(
        book_id=row[0], sharh=row[1], base_id=row[2], base_name=row[3],
        hadith_number=row[4], chapter=row[5], page=row[6], page_id=row[7],
        score=row[8], excerpt=row[9], text=row[10],
    )

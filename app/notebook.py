"""The study notebook (دفتر): a small local store of saved items + personal notes.

Lets the app keep the user's work between sessions — save a hadith, a narrator, or an
answer, attach a note and tags, search it later. It's deliberately separate from the
search indexes (which are rebuilt by scripts) so it **survives updates**: it lives in
its own sqlite file under data/ and is never recreated by the indexing pipeline.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS note (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT,          -- hadith | narrator | answer | …
    title TEXT,         -- citation / name / question
    body TEXT,          -- matn / profile / answer text
    meta TEXT,          -- JSON: grade, isnad, rulings, model… (free-form)
    note TEXT,          -- the user's own note
    tags TEXT,          -- comma-separated
    created_at REAL
);
"""


class Notebook:
    """A user's saved items with notes — sqlite-backed, persistent across updates."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._con = sqlite3.connect(str(db_path), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._con.executescript(_SCHEMA)

    def add(self, kind: str, title: str, body: str = "", *, meta: dict | None = None,
            note: str = "", tags: str = "") -> dict:
        cur = self._con.execute(
            "INSERT INTO note (kind, title, body, meta, note, tags, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (kind, title, body, json.dumps(meta or {}, ensure_ascii=False), note, tags, time.time()),
        )
        self._con.commit()
        return self.get(cur.lastrowid)  # type: ignore[arg-type]

    def get(self, note_id: int) -> dict | None:
        row = self._con.execute("SELECT * FROM note WHERE id = ?", (note_id,)).fetchone()
        return _to_dict(row) if row else None

    def list(self, q: str | None = None, *, kind: str | None = None) -> list[dict]:
        """All saved items, newest first; ``q`` filters across title/body/note/tags."""
        sql, params = "SELECT * FROM note", []
        where = []
        if kind:
            where.append("kind = ?")
            params.append(kind)
        if q:
            like = f"%{q}%"
            where.append("(title LIKE ? OR body LIKE ? OR note LIKE ? OR tags LIKE ?)")
            params += [like, like, like, like]
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC"
        return [_to_dict(r) for r in self._con.execute(sql, params)]

    def update(self, note_id: int, *, note: str | None = None, tags: str | None = None) -> dict | None:
        sets, params = [], []
        if note is not None:
            sets.append("note = ?")
            params.append(note)
        if tags is not None:
            sets.append("tags = ?")
            params.append(tags)
        if sets:
            params.append(note_id)
            self._con.execute(f"UPDATE note SET {', '.join(sets)} WHERE id = ?", params)
            self._con.commit()
        return self.get(note_id)

    def delete(self, note_id: int) -> bool:
        cur = self._con.execute("DELETE FROM note WHERE id = ?", (note_id,))
        self._con.commit()
        return cur.rowcount > 0

    def count(self) -> int:
        return self._con.execute("SELECT count(*) FROM note").fetchone()[0]

    def close(self) -> None:
        self._con.close()


def _to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    try:
        d["meta"] = json.loads(d.get("meta") or "{}")
    except (json.JSONDecodeError, TypeError):
        d["meta"] = {}
    return d

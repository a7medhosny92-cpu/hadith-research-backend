"""The narrator network (شبكة الرواة): who narrates from whom, built from the chains.

Every isnad is a sequence «A عن B عن C …»: each adjacent pair is a link — A (التلميذ)
heard from B (الشيخ). Aggregating *all* chains in the corpus gives, for every narrator,
their شيوخ (teachers they narrate from) and تلاميذ (students who narrate from them),
weighted by how often the link occurs. This covers every narrator that appears, with
no external dataset, and the links themselves help disambiguate shared names (مهمل):
which «سفيان» it is follows from who he narrates from.

Names are matched by their folded token set (kunya cases أبو/أبا/أبي unified), so the
same man written slightly differently collapses to one node. This is a *structural*
network from the texts, not a substitute for the رجال critics' documented سماع.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.parsing.normalize import normalize_for_search

_SCHEMA = """
CREATE TABLE IF NOT EXISTS narrator (
    id INTEGER PRIMARY KEY, norm TEXT UNIQUE, name TEXT, freq INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS link (
    teacher INTEGER, student INTEGER, weight INTEGER DEFAULT 0,
    PRIMARY KEY (teacher, student)
);
CREATE INDEX IF NOT EXISTS link_student ON link(student);
CREATE INDEX IF NOT EXISTS link_teacher ON link(teacher);
"""

# Tokens that mark the end of a chain (the Prophet ﷺ), not a gradable narrator.
_PROPHET = {"النبي", "رسول", "الله", "نبي"}


def name_tokens(text: str) -> frozenset[str]:
    """Folded tokens for narrator-name matching (kunya cases أبو/أبا/أبي unified)."""
    out = set()
    for t in normalize_for_search(text or "").split():
        out.add("ابو" if t in ("ابو", "ابا", "ابي") else t)
    return frozenset(out)


def is_prophet(name: str) -> bool:
    toks = name_tokens(name)
    return bool(toks) and toks <= _PROPHET | {"صلي", "عليه", "وسلم", "عن"}


@dataclass(slots=True)
class _Node:
    id: int
    name: str
    tokens: frozenset[str]
    freq: int


class NarratorGraph:
    """A teacher↔student graph over narrators, keyed by folded name tokens."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._con = sqlite3.connect(str(db_path), check_same_thread=False)
        self._con.executescript(_SCHEMA)
        self._nodes_cache: list[_Node] | None = None

    # ── building ──────────────────────────────────────────────────────────────
    def _node_id(self, name: str) -> int | None:
        norm = " ".join(sorted(name_tokens(name)))
        if not norm:
            return None
        row = self._con.execute("SELECT id FROM narrator WHERE norm = ?", (norm,)).fetchone()
        if row:
            self._con.execute("UPDATE narrator SET freq = freq + 1 WHERE id = ?", (row[0],))
            return row[0]
        cur = self._con.execute(
            "INSERT INTO narrator (norm, name, freq) VALUES (?, ?, 1)", (norm, name.strip())
        )
        return cur.lastrowid

    def add_chain(self, names: Iterable[str]) -> None:
        """Record a chain: each name narrates *from* the next one (تلميذ → شيخ)."""
        ids = [nid for n in names if (nid := self._node_id(n)) is not None]
        for student, teacher in zip(ids, ids[1:]):
            if student == teacher:
                continue
            self._con.execute(
                "INSERT INTO link (teacher, student, weight) VALUES (?, ?, 1) "
                "ON CONFLICT(teacher, student) DO UPDATE SET weight = weight + 1",
                (teacher, student),
            )
        self._nodes_cache = None

    def commit(self) -> None:
        self._con.commit()

    # ── querying ──────────────────────────────────────────────────────────────
    def _nodes(self) -> list[_Node]:
        if self._nodes_cache is None:
            self._nodes_cache = [
                _Node(id=r[0], name=r[2], tokens=frozenset(r[1].split()), freq=r[3])
                for r in self._con.execute("SELECT id, norm, name, freq FROM narrator")
            ]
        return self._nodes_cache

    def resolve(self, name: str) -> _Node | None:
        """Find the node for ``name``: exact token match, else the most-narrated node
        whose tokens contain the query (so «أبو هريرة» finds «أبو هريرة الدوسي»)."""
        q = name_tokens(name)
        if not q:
            return None
        exact = self._con.execute(
            "SELECT id, norm, name, freq FROM narrator WHERE norm = ?",
            (" ".join(sorted(q)),),
        ).fetchone()
        if exact:
            return _Node(id=exact[0], name=exact[2], tokens=frozenset(exact[1].split()), freq=exact[3])
        best: _Node | None = None
        for node in self._nodes():
            if q <= node.tokens and (best is None or node.freq > best.freq):
                best = node
        return best

    def _neighbours(self, node_id: int, *, as_teacher: bool, limit: int) -> list[dict]:
        col, other = ("teacher", "student") if as_teacher else ("student", "teacher")
        rows = self._con.execute(
            f"SELECT n.name, l.weight FROM link l JOIN narrator n ON n.id = l.{other} "
            f"WHERE l.{col} = ? ORDER BY l.weight DESC LIMIT ?",
            (node_id, limit),
        ).fetchall()
        return [{"name": name, "count": weight} for name, weight in rows]

    def teachers(self, name: str, *, limit: int = 50) -> list[dict]:
        """The شيوخ of ``name`` — narrators they narrate *from* — most frequent first."""
        node = self.resolve(name)
        return self._neighbours(node.id, as_teacher=False, limit=limit) if node else []

    def students(self, name: str, *, limit: int = 50) -> list[dict]:
        """The تلاميذ of ``name`` — narrators who narrate *from* them."""
        node = self.resolve(name)
        return self._neighbours(node.id, as_teacher=True, limit=limit) if node else []

    def link_weight(self, student: str, teacher: str) -> int:
        """How many times ``student`` is recorded narrating from ``teacher`` (0 = never)."""
        s, t = self.resolve(student), self.resolve(teacher)
        if not s or not t:
            return 0
        row = self._con.execute(
            "SELECT weight FROM link WHERE teacher = ? AND student = ?", (t.id, s.id)
        ).fetchone()
        return row[0] if row else 0

    def count(self) -> int:
        return self._con.execute("SELECT count(*) FROM narrator").fetchone()[0]

    def close(self) -> None:
        self._con.close()

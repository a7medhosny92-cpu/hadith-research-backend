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
# The eulogy (صلى الله عليه وسلم) — part of a Prophet reference, ignored when testing it.
_EULOGY_TOKENS = {"صلي", "عليه", "وسلم", "واله", "وصحبه", "سلم", "عن"}
# The single canonical node every Prophet reference collapses to.
PROPHET_NODE = "النبي ﷺ"
# Relational pronouns (عن أبيه عن جده): real in the text but not graph-able narrators —
# every «أبيه» would otherwise merge into one bogus hub that is everyone's teacher.
_RELATIVE = {normalize_for_search(w) for w in (
    "أبيه أبيها أمه أمها جده جدها جدته ابنه ابنها بنته عمه عمها خاله خالها أخيه أخيها أخته"
).split()}


def name_tokens(text: str) -> frozenset[str]:
    """Folded tokens for narrator-name matching (kunya cases أبو/أبا/أبي unified)."""
    out = set()
    for t in normalize_for_search(text or "").split():
        out.add("ابو" if t in ("ابو", "ابا", "ابي") else t)
    return frozenset(out)


def is_prophet(name: str) -> bool:
    """True if ``name`` refers to the Prophet ﷺ — its *core* tokens (after dropping the
    eulogy) are all Prophet terms. So «النبي», «رسول الله», «النبي صلى الله عليه وسلم»
    all match, but «النبي مثله» / «محمد بن إسماعيل» do not."""
    core = name_tokens(name) - _EULOGY_TOKENS
    return bool(core) and core <= _PROPHET


def _is_relative(name: str) -> bool:
    toks = name_tokens(name)
    return len(toks) == 1 and next(iter(toks)) in _RELATIVE


# Shared bare names (المشترك): same name, different men. Disambiguate by the company
# they keep — classic cases, each candidate with telltale teachers/students. (The full
# رجال import extends this for every narrator; these are the high-frequency ones.)
_AMBIGUOUS: dict[str, list[tuple[str, list[str]]]] = {
    "سفيان": [
        ("سفيان بن عيينة", ["عمرو بن دينار", "الزهري", "أبو الزناد", "عبد الله بن دينار",
                            "الحميدي", "الشافعي", "علي بن المديني", "ابن أبي عمر"]),
        ("سفيان الثوري", ["منصور", "الأعمش", "أبو إسحاق", "سلمة بن كهيل",
                          "وكيع", "عبد الرزاق", "عبد الرحمن بن مهدي", "أبو نعيم", "الفريابي", "قبيصة"]),
    ],
    "حماد": [
        ("حماد بن زيد", ["أيوب", "عمرو بن دينار", "أنس بن سيرين", "هشام بن عروة"]),
        ("حماد بن سلمة", ["ثابت", "قتادة", "علي بن زيد", "حميد الطويل", "عمار بن أبي عمار"]),
    ],
}
_AMBIG = {" ".join(sorted(name_tokens(k))): v for k, v in _AMBIGUOUS.items()}


def disambiguate(name: str, neighbours: list[str]) -> str:
    """Resolve a shared name to a specific person from its chain neighbours; if no
    marker matches (or the name isn't shared), return it unchanged."""
    candidates = _AMBIG.get(" ".join(sorted(name_tokens(name))))
    if not candidates:
        return name
    around: set[str] = set()
    for nb in neighbours:
        around |= name_tokens(nb)
    best, best_score = name, 0
    for canonical, markers in candidates:
        score = sum(1 for m in markers if name_tokens(m) <= around)
        if score > best_score:
            best, best_score = canonical, score
    return best


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
        """Record a chain: each name narrates *from* the next one (تلميذ → شيخ).

        Every Prophet reference collapses to one canonical node; shared names (سفيان …)
        are resolved from their immediate neighbours; relational pronouns (أبيه/جده)
        create **no** node and break the link on both sides (so they don't form a hub)."""
        names = list(names)
        ids: list[int | None] = []
        for i, name in enumerate(names):
            if _is_relative(name):
                ids.append(None)            # a pronoun — not a node; breaks the chain here
                continue
            canonical = PROPHET_NODE if is_prophet(name) else disambiguate(
                name, [names[i - 1] if i else "", names[i + 1] if i + 1 < len(names) else ""]
            )
            ids.append(self._node_id(canonical))
        for student, teacher in zip(ids, ids[1:]):
            if not student or not teacher or student == teacher:
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

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
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from app.parsing.normalize import fold_kunya, normalize_for_search

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


@lru_cache(maxsize=1 << 17)
def name_tokens(text: str) -> frozenset[str]:
    """Folded tokens for narrator-name matching (kunya cases أبو/أبا/أبي unified, but
    «أبي بن …» kept as the name أُبَيّ). Memoised — called millions of times on repeated
    names while building the graph."""
    return frozenset(fold_kunya(normalize_for_search(text or "").split()))


@lru_cache(maxsize=1 << 17)
def node_key(text: str) -> str:
    """The graph node's identity key: folded tokens in their ORIGINAL order. Order is
    load-bearing — «أنس بن مالك» (a Companion, a *teacher* of al-Zuhrī) and «مالك بن أنس»
    (the Imam, his *student*) share the same token set but are different men, so the key
    must keep the sequence; a sorted key collapses them into one node. (The rijal index
    is order-sensitive for the same reason — «يزيد بن جابر» ≠ «جابر بن يزيد».)"""
    return " ".join(fold_kunya(normalize_for_search(text or "").split()))


# Kinship words that are real in the text but not graph-able narrators: third-person
# possessives (عن أبيه عن جده) AND first-person (حدثني أبي عن أمي), plus a bare kunya
# particle (أبو/أبي/أبا on its own). Without the first-person forms, every «أبي» («my
# father») merges into one bogus hub that becomes everyone's teacher. Built through
# name_tokens so the folding (أبي → ابو) matches the test in _is_relative.
_RELATIVE: set[str] = set()
for _w in (
    "أبيه أبيها أمه أمها جده جدها جدته ابنه ابنها بنته عمه عمها خاله خالها أخيه أخيها أخته "
    "أبي أمي جدي جدتي ابني ابنتي بنتي أخي أختي عمي عمتي خالي خالتي أبو أبا"
).split():
    _RELATIVE |= name_tokens(_w)


def is_prophet(name: str) -> bool:
    """True if ``name`` refers to the Prophet ﷺ — its *core* tokens (after dropping the
    eulogy) are all Prophet terms. So «النبي», «رسول الله», «النبي صلى الله عليه وسلم»
    all match, but «النبي مثله» / «محمد بن إسماعيل» do not."""
    core = name_tokens(name) - _EULOGY_TOKENS
    return bool(core) and core <= _PROPHET


def _is_relative(name: str) -> bool:
    toks = name_tokens(name)
    return len(toks) == 1 and next(iter(toks)) in _RELATIVE


# A kinship reference names a *real* person only by relation: «أبيه» (his father), «جده»
# (his grandfather), «أمه» (his mother), «أخيه» (his brother), «عمه/خاله» (his uncle),
# «ابنه» (his son)… or a bare first-person form («أبي» = my father). Each is resolved to
# the actual person, or kept as an *anchored* placeholder «<label> فلان» — never a hub.
# «أبي بن كعب»/«أبي بكر» are NOT this (a person / a kunya): a first-person form counts only
# when bare.
_NASAB_TOK = {"بن", "ابن"}
# normalized first token → (placeholder label, nasab degree: 1=father, 2=grandfather,
# 0=not a lineal ancestor, so only an apposition or a placeholder can name him).
_KIN: dict[str, tuple[str, int]] = {
    "ابيه": ("والد", 1), "ابيها": ("والد", 1), "ابي": ("والد", 1),
    "جده": ("جدّ", 2), "جدها": ("جدّ", 2), "جدي": ("جدّ", 2), "جدته": ("جدّة", 2),
    "امه": ("والدة", 0), "امها": ("والدة", 0), "امي": ("والدة", 0),
    "اخيه": ("أخو", 0), "اخيها": ("أخو", 0), "اخي": ("أخو", 0), "اخته": ("أخت", 0),
    "عمه": ("عمّ", 0), "عمها": ("عمّ", 0), "عمي": ("عمّ", 0),
    "خاله": ("خال", 0), "خالها": ("خال", 0), "خالي": ("خال", 0),
    "ابنه": ("نجل", 0), "ابنها": ("نجل", 0), "ابني": ("نجل", 0),
    "بنته": ("بنت", 0), "بنتي": ("بنت", 0),
}
# First-person forms (أبي/جدي/أخي…) count only when *bare* — «أبي بكر» is a kunya, not «my
# father»; «أبي بن كعب» the name أُبَيّ. («أبو» folds to it but isn't here → bare أبو drops.)
_KIN_FIRST_PERSON = {"ابي", "جدي", "امي", "اخي", "عمي", "خالي", "ابني", "بنتي"}
# Placeholder label prefixes (deliberately NOT «أم»/«ابن», which begin real names like
# «أم سلمة» / «ابن عباس») — used to spot a synthetic node so it isn't graded.
_KIN_LABELS = {"والد", "والدة", "جدّ", "جد", "جدّة", "أخو", "أخت", "عمّ", "خال", "نجل", "بنت"}


def _kin_relation(name: str) -> tuple[str, int] | None:
    """``(label, degree)`` if ``name`` is a kinship reference, else ``None``."""
    toks = normalize_for_search(name or "").split()
    if not toks:
        return None
    head, info = toks[0], _KIN.get(toks[0])
    if info is None or (head in _KIN_FIRST_PERSON and len(toks) > 1):
        return None
    return info


def _ancestor_from_nasab(anchor: str, degree: int) -> str:
    """The ``degree``-th ancestor named inside ``anchor``'s nasab, or '' if not that deep:
    «عمرو بن شعيب» @1 → «شعيب»; «عبد الله بن أحمد بن حنبل» @1 → «أحمد بن حنبل»."""
    parts = anchor.split()
    norm = [normalize_for_search(p) for p in parts]
    seen = 0
    for k, tok in enumerate(norm):
        if tok in _NASAB_TOK:
            seen += 1
            if seen == degree and k + 1 < len(parts):
                return " ".join(parts[k + 1:]).strip()
    return ""


def _kin_node(label: str, anchor: str) -> str:
    """A synthetic, *anchored* node for an unnamed relative — «والد فلان» / «أخو فلان».

    Keyed to one specific narrator, so the link is kept without inventing a name and
    without a hub: «جدّ عمرو بن شعيب» ≠ «جدّ بهز بن حكيم»."""
    return f"{label} {anchor}"


def is_unnamed_kin(name: str) -> bool:
    """True for a synthetic «<relation> of X» node (a real but unnamed link), so the rijal
    layer doesn't mis-grade it as X himself."""
    return bool(name) and name.split(" ", 1)[0] in _KIN_LABELS


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
    seq: tuple[str, ...] = ()   # ORDERED key tokens — «أنس بن مالك» ≠ «مالك بن أنس»


class NarratorGraph:
    """A teacher↔student graph over narrators, keyed by folded name tokens."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._con = sqlite3.connect(str(db_path), check_same_thread=False)
        # The graph is rebuilt atomically (scripts._atomic.rebuild → temp file, then renamed) and
        # is read-only once served, so the write-heavy build (≈1M node ops + ≈0.9M link ops over
        # the corpus, twice) can trade durability for speed: no fsync, in-memory journal/temp, a
        # bigger page cache. A crash just discards the temp and keeps the previous graph.
        for pragma in ("journal_mode = MEMORY", "synchronous = OFF",
                       "temp_store = MEMORY", "cache_size = -65536"):
            self._con.execute(f"PRAGMA {pragma}")
        self._con.executescript(_SCHEMA)
        self._nodes_cache: list[_Node] | None = None

    # ── building ──────────────────────────────────────────────────────────────
    def _node_id(self, name: str) -> int | None:
        norm = node_key(name)
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

    def add_chain(self, names: Iterable[str], *, canon=None) -> None:
        """Record a chain: each name narrates *from* the next one (تلميذ → شيخ).

        Every Prophet reference collapses to one canonical node; a shared name (سفيان …)
        is resolved from the *whole chain*. A kinship reference (أبيه/جده, or bare «أبي»)
        is **resolved to the real ancestor** — from an apposition or the adjacent
        narrator's nasab — so a real father (often a Companion) is kept, not dropped; only
        an unidentifiable one breaks the chain (never a hub). Other relatives (أمه/أخيه)
        and a bare kunya particle break the chain.

        When a :class:`~app.rijal.canon.Canonicalizer` is supplied, each name is also mapped
        to its رجال canonical identity (الاسم/الكنية/اللقب موحَّدة) so the same man written
        differently collapses to one node — using the *rest of the chain* as context to
        break ties, and keeping the surface form when unsure."""
        names = list(names)
        n = len(names)
        ctx_tokens = [canon.tokens(x) for x in names] if canon is not None else None

        def _canonical(name: str, i: int) -> str:
            if is_prophet(name):
                return PROPHET_NODE
            name = disambiguate(name, [x for j, x in enumerate(names) if j != i])
            if canon is None or n <= 1:
                return name
            context = frozenset().union(*(t for j, t in enumerate(ctx_tokens) if j != i))
            return canon.canonical(name, context)

        resolved: list[str | None] = [None] * n
        # pass 1 — ordinary narrators (everything that is not a kinship reference)
        for i, name in enumerate(names):
            if not _is_relative(name) and _kin_relation(name) is None:
                resolved[i] = _canonical(name, i)
        # pass 2 — kinship references: name the person when the text allows (an apposition,
        # or the anchor's nasab for father/grandfather), else keep the link via an *anchored*
        # «<relation> of X» node. Never dropped while there is a specific narrator (anchor).
        anchor: str | None = None
        for i, name in enumerate(names):
            rel = _kin_relation(name)
            if rel is None:
                if resolved[i] is not None and len(name_tokens(resolved[i])) >= 2:
                    anchor = resolved[i]                # a specific narrator to anchor on
                continue
            label, degree = rel
            apposition = " ".join(name.split()[1:]).strip()   # «أبيه أبي موسى» → «أبي موسى»
            if apposition:
                resolved[i] = _canonical(apposition, i)
                anchor = resolved[i]                    # the named relative is the new anchor
                continue
            if anchor is None:
                continue                                # nothing specific to attach to → break
            named = _ancestor_from_nasab(anchor, degree) if degree else ""
            if not named:
                resolved[i] = _kin_node(label, anchor)
            else:
                # an ancestor's name is a *suffix* of the son's nasab, so the canonicaliser
                # may pull it back up to the son — keep the raw ancestor name when it does.
                cand = _canonical(named, i)
                resolved[i] = named if name_tokens(cand) == name_tokens(anchor) else cand

        ids = [self._node_id(x) if x else None for x in resolved]
        for i in range(len(ids) - 1):
            student, teacher = ids[i], ids[i + 1]
            if not student or not teacher or student == teacher:
                continue
            # the Prophet ﷺ narrates from no one — he is only ever a شيخ (terminal). A pair with
            # him as the التلميذ means a parse error left «النبي» mid-chain; drop the bogus edge so
            # it can't become spurious company (and make him a «student» in the network).
            if resolved[i] == PROPHET_NODE:
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
                _Node(id=r[0], name=r[2], tokens=frozenset(r[1].split()), freq=r[3], seq=tuple(r[1].split()))
                for r in self._con.execute("SELECT id, norm, name, freq FROM narrator")
            ]
        return self._nodes_cache

    def resolve(self, name: str) -> _Node | None:
        """Find the node for ``name``: exact token match, else the most-narrated node
        whose tokens contain the query (so «أبو هريرة» finds «أبو هريرة الدوسي»)."""
        q = name_tokens(name)
        if not q or (len(q) == 1 and next(iter(q)) in _RELATIVE):
            return None     # empty, or a bare kinship particle (أبي/أبيه/جده) — no node
        exact = self._con.execute(
            "SELECT id, norm, name, freq FROM narrator WHERE norm = ?",
            (node_key(name),),
        ).fetchone()
        if exact:
            return _Node(id=exact[0], name=exact[2], tokens=frozenset(exact[1].split()),
                         freq=exact[3], seq=tuple(exact[1].split()))
        # Prefer a node where the query is the LEADING RUN of the ordered key (the natural
        # identity) — «أبو هريرة» → «أبو هريرة الدوسي», but «أنس بن مالك» / bare «أنس» must NOT
        # land on «مالك بن أنس» (anagram). Fall back to a plain token-subset (nisba-only queries
        # like «الزهري» → «محمد بن مسلم الزهري») only when no leading-run node exists.
        qseq = tuple(node_key(name).split())
        lead = sub = None
        for node in self._nodes():
            if node.seq[: len(qseq)] == qseq:
                if lead is None or node.freq > lead.freq:
                    lead = node
            elif q <= node.tokens:
                if sub is None or node.freq > sub.freq:
                    sub = node
        return lead or sub

    def _neighbours(self, node_id: int, *, as_teacher: bool, limit: int | None) -> list[dict]:
        col, other = ("teacher", "student") if as_teacher else ("student", "teacher")
        rows = self._con.execute(
            f"SELECT n.name, l.weight FROM link l JOIN narrator n ON n.id = l.{other} "
            f"WHERE l.{col} = ? ORDER BY l.weight DESC LIMIT ?",
            (node_id, -1 if limit is None else limit),   # SQLite LIMIT -1 = no limit (all)
        ).fetchall()
        return [{"name": name, "count": weight} for name, weight in rows]

    def teachers(self, name: str, *, limit: int | None = None) -> list[dict]:
        """The شيوخ of ``name`` — narrators they narrate *from* — most frequent first.
        ``limit=None`` returns **all** of them (no cap)."""
        node = self.resolve(name)
        return self._neighbours(node.id, as_teacher=False, limit=limit) if node else []

    def students(self, name: str, *, limit: int | None = None) -> list[dict]:
        """The تلاميذ of ``name`` — narrators who narrate *from* them; ``limit=None`` = all."""
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

    def adjacency(self) -> dict[str, list[str]]:
        """Every node → the names of *all* its neighbours (شيوخ ∪ تلاميذ).

        Used to derive each narrator's «recorded company» for context disambiguation —
        the telltale names that decide which of two homonyms a bare ism refers to."""
        name_by_id = {n.id: n.name for n in self._nodes()}
        adj: dict[str, set[str]] = {}
        for teacher, student in self._con.execute("SELECT teacher, student FROM link"):
            tn, sn = name_by_id.get(teacher), name_by_id.get(student)
            if tn and sn:
                adj.setdefault(tn, set()).add(sn)
                adj.setdefault(sn, set()).add(tn)
        return {name: sorted(neigh) for name, neigh in adj.items()}

    def count(self) -> int:
        return self._con.execute("SELECT count(*) FROM narrator").fetchone()[0]

    def close(self) -> None:
        self._con.close()

"""Collapse same-man duplicates in the رجال gradings — deflating «مشترك».

تقريب and الكاشف often spell one narrator two ways — «هشام بن عمار بن نصير السلمي الدمشقي
الخطيب» and «هشام بن عمار أبو الوليد السلمي الدمشقي المقرئ». ``build_rijal.merge_source`` can't
unify them (the tails differ, so the lookup misses), so both land in ``rijal.jsonl``; a chain
citing the bare «هشام بن عمار» then matches BOTH → flagged «مشترك» though it is ONE man. This
collapses such pairs after the sources are merged.

The rule is **prudent — it never fuses two different men**. Inside a group sharing the «ism +
first nasab» (the short form a chain cites), two entries are the same man when:

* they share a specific **nisba** (الدمشقي…) with no **generation** marker conflict
  (الكبير/الصغير/حفيد) and no *strong* grade conflict (one trusted, one weak); OR
* lacking a shared nisba, the **death-year** (±window) or the **kunya** confirm it.

So genuine homonyms — نصر الجهضمي الكبير vs his حفيد, الموصلي vs الدورقي, a ثقة vs a متروك of the
same name — stay apart (correctly «مشترك»). The survivor keeps the fullest name and **both**
critics' opinions (the double-opinion), and the authority's grade.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

from app.parsing.normalize import normalize_for_search
from app.rijal.grades import classify

_BIN = {normalize_for_search(w) for w in ("بن", "ابن")}                 # patronymic links
_GEN = {normalize_for_search(w) for w in                                # «… الكبير» ≠ «… حفيده»
        ("الكبير", "الأكبر", "الحفيد", "حفيد", "الأصغر", "الصغير", "الابن", "الأب", "الجد")}
_KUNYA_P = {normalize_for_search(w) for w in ("أبو", "أبا", "أم")}      # the subject's kunya onset
_TRUSTED_RANK = 5     # rank ≥ this is a "trusted" verdict (ثقة/صدوق/مقبول/صحابي); below it is weak


def _fold(text: str | None) -> str:
    return normalize_for_search(text or "")


def _is_nisba(tok: str) -> bool:
    """A nisba-like token «الـ…ـي» (الدمشقي، الكوفي، الفهمي) — a place/tribe discriminator."""
    return tok.startswith("ال") and tok.endswith("ي") and len(tok) >= 4


def lineage(name: str) -> list[tuple[str, ...]]:
    """The nasab ancestor chain — [(ism), (father…), (grandfather…), …] — stopping at the first
    *descriptor* (the subject's kunya «أبو…», a nisba, or a generation marker). A kunya particle
    right **after a بن** is kept (it names a father «بن أبي بكر»), one not after بن ends the chain
    (it is the subject's own kunya «… عمار أبو الوليد»). So «هشام بن عمار بن نصير … السلمي الدمشقي
    الخطيب» → [(هشام,), (عمار,), (نصير,)] while «أحمد بن عبد الله بن يونس …» → [(احمد,), (عبد,الله),
    (يونس,)] — distinguishing «عبد الله» from «عبد الواحد», and «بن يونس» from «بن محمد»."""
    out: list[tuple[str, ...]] = []
    cur: list[str] = []
    after_bin = False
    for tok in (normalize_for_search(w) for w in name.split()):
        if not tok:
            continue
        if tok in _BIN:
            if cur:
                out.append(tuple(cur))
                cur = []
            after_bin = True
            continue
        if not after_bin and (tok in _KUNYA_P or tok in _GEN or _is_nisba(tok)):
            break                                          # the subject's descriptors begin
        cur.append(tok)
        after_bin = False
    if cur:
        out.append(tuple(cur))
    return out


def lineage_compatible(a: dict, b: dict) -> bool:
    """Do two nasab chains agree on every ancestor they BOTH name (one a prefix of the other)?
    «هشام بن عمار» extends to «هشام بن عمار بن نصير» (compatible); «… بن عبد الله بن يونس» and
    «… بن عبد الله بن محمد» disagree at the grandfather (not the same man)."""
    la, lb = lineage(a["name"]), lineage(b["name"])
    if not la or not lb:
        return False
    return all(x == y for x, y in zip(la, lb))


def ident_key(name: str) -> tuple[str, ...]:
    """«ism + full father» from the lineage — «الليث بن سعد بن عبد الرحمن الفهمي» and «الليث بن
    سعد أبو الحارث» both key on (الليث، سعد), but «أحمد بن عبد الله» and «أحمد بن عبد الواحد» key
    apart. Falls back to the first folded tokens for a name with no nasab."""
    lin = lineage(name)
    if not lin:
        return tuple(t for t in (normalize_for_search(w) for w in name.split()) if t)[:3]
    return lin[0] + (lin[1] if len(lin) > 1 else ())


def tokens(name: str) -> set[str]:
    return {t for t in (normalize_for_search(w) for w in name.split()) if t and t not in _BIN}


def nisbas(toks: set[str]) -> set[str]:
    """Nisba-like tokens: «الـ…ـي» (الدمشقي، الكوفي، الفهمي) — a place/tribe discriminator."""
    return {t for t in toks if _is_nisba(t)}


def _trusted(grade: str | None) -> bool | None:
    """True/False if the grade is a trusted/weak verdict; ``None`` if ungraded."""
    rank = classify(grade or "")[1]
    return None if rank is None else rank >= _TRUSTED_RANK


def _strong_grade_conflict(a: dict, b: dict) -> bool:
    """One man can't be both trusted and weak — a ثقة vs a متروك signals *different* men (or a
    real dispute), so we refuse the merge and leave it «مشترك». Ungraded never conflicts."""
    ta, tb = _trusted(a.get("grade")), _trusted(b.get("grade"))
    return ta is not None and tb is not None and ta != tb


def same_man(a: dict, b: dict, *, window: int = 20) -> bool:
    """Are two entries (already sharing an ``ident_key``) the same narrator? Prudent — see module
    docstring. Returns ``False`` whenever the evidence can't confirm it."""
    if not lineage_compatible(a, b):
        return False                                      # nasab chains disagree → different men
    A, B = tokens(a["name"]), tokens(b["name"])
    if (A & _GEN) != (B & _GEN):
        return False                                      # generation marker conflict
    na, nb = nisbas(A), nisbas(B)
    if na and nb and na.isdisjoint(nb):
        return False                                      # disjoint nisba → two men
    if na & nb:                                           # share a specific nisba → same man…
        return not _strong_grade_conflict(a, b)           # …unless the grades strongly clash
    da, db = a.get("death_year"), b.get("death_year")     # no nisba evidence → confirm by metadata
    if da and db:
        try:
            return abs(int(da) - int(db)) <= window
        except (TypeError, ValueError):
            pass
    ka, kb = _fold(a.get("kunya")), _fold(b.get("kunya"))
    if ka and kb:
        return ka == kb
    return False                                          # can't confirm → keep apart (prudent)


def _opinions_of(rec: dict) -> list[dict]:
    ops = rec.get("opinions")
    if ops:
        return ops
    return [{"source": rec.get("source", ""), "grade": classify(rec.get("grade") or "")[0]}]


def _merge_into(primary: dict, other: dict) -> None:
    """Fold ``other`` (a confirmed same-man duplicate) into ``primary``: keep both critics'
    opinions, fill any gap primary has (grade/death/kunya) from other. Primary's own grade
    (the authority's) is the verdict."""
    ops = primary.setdefault("opinions", _opinions_of(primary)[:])
    have = {o["source"] for o in ops}
    for op in _opinions_of(other):
        if op["source"] not in have:
            ops.append(op)
            have.add(op["source"])
    if classify(primary.get("grade") or "")[1] is None and classify(other.get("grade") or "")[1] is not None:
        primary["grade"] = other["grade"]
        primary["source"] = f"{primary.get('source', '')} + {other.get('source', '')}".strip(" +")
    for field in ("death_year", "kunya"):
        if not primary.get(field) and other.get(field):
            primary[field] = other[field]


def _pick_primary(cluster: list[int], records: list[dict]) -> int:
    """The index to keep: a graded entry with the **fullest** name (most specific, best for
    lookup); ties broken toward the earliest (the authority source comes first)."""
    def key(i: int) -> tuple:
        graded = classify(records[i].get("grade") or "")[1] is not None
        return (graded, len(tokens(records[i]["name"])), -i)
    return max(cluster, key=key)


class CorpusCompany:
    """The narrator network (``narrators.db``) used as a same-man oracle: a name-proposed merge is
    *confirmed* only when the two entries map to the same graph node (or share a chain circle), and
    *vetoed* when the corpus cites them with disjoint company. Built from the PREVIOUS run's graph
    (``build_rijal`` precedes ``build_graph``); the first ever run simply has no graph → name-only."""

    def __init__(self, db_path: str | Path) -> None:
        con = sqlite3.connect(str(db_path))
        self._by_key: dict[tuple[str, ...], list[tuple[int, frozenset, frozenset, int]]] = defaultdict(list)
        for nid, name, freq in con.execute("SELECT id, name, freq FROM narrator"):
            toks = tokens(name or "")
            self._by_key[ident_key(name or "")].append((nid, frozenset(toks), frozenset(nisbas(toks)), freq))
        self._adj: dict[int, set[int]] = defaultdict(set)
        for teacher, student in con.execute("SELECT teacher, student FROM link"):
            self._adj[teacher].add(student)
            self._adj[student].add(teacher)
        con.close()

    def _node_for(self, name: str) -> int | None:
        """The graph node that best cites this رجال name: same ism+father, a compatible nisba,
        most token-overlap then most-narrated. ``None`` when the corpus doesn't carry him."""
        toks = tokens(name)
        nis = nisbas(toks)
        best, best_score = None, (-1, -1)
        for nid, ntoks, nnis, freq in self._by_key.get(ident_key(name), ()):
            if nis and nnis and nis.isdisjoint(nnis):
                continue                                   # the node carries a conflicting nisba
            score = (len(ntoks & toks), freq)
            if score > best_score:
                best, best_score = nid, score
        return best

    def confirms(self, name_a: str, name_b: str) -> bool:
        """Does the corpus *positively* agree the two are one man? Same node, or ≥2 shared chain
        associates. ``False`` on disjoint company OR when either man is absent from the graph —
        used by the strict policy, which merges only what the network confirms."""
        a, b = self._node_for(name_a), self._node_for(name_b)
        if a is None or b is None:
            return False
        return a == b or len(self._adj[a] & self._adj[b]) >= 2

    def vetoes(self, name_a: str, name_b: str) -> bool:
        """A *positive contradiction*: both men are in the graph, as distinct nodes, with **disjoint**
        company (different circles). Absence of evidence is NOT a veto — used by the mix policy,
        which trusts the name unless the corpus proves the two are different men."""
        a, b = self._node_for(name_a), self._node_for(name_b)
        if a is None or b is None or a == b:
            return False
        return bool(self._adj[a]) and bool(self._adj[b]) and self._adj[a].isdisjoint(self._adj[b])


def collapse_duplicates(
    records: list[dict], *, window: int = 20,
    company: "CorpusCompany | None" = None, require_confirm: bool = False,
) -> tuple[list[dict], int]:
    """Return ``(deduped_records, removed)`` — same-man duplicates collapsed into one entry.

    Groups by ``ident_key`` and unions entries by :func:`same_man` (transitively). A
    :class:`CorpusCompany`, when supplied, gates each name-proposed merge against the chain network:

    * **mix** (default, ``require_confirm=False``) — the name proposes, the corpus only **vetoes** a
      merge it positively contradicts (disjoint company); absent men are trusted to the name.
    * **strict** (``require_confirm=True``) — merge only what the corpus **confirms** (same company).

    With no company it is name-only. Order is otherwise preserved."""
    groups: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for i, rec in enumerate(records):
        groups[ident_key(rec.get("name", ""))].append(i)

    drop: set[int] = set()
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        parent = {i: i for i in idxs}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for p in range(len(idxs)):
            for q in range(p + 1, len(idxs)):
                i, j = idxs[p], idxs[q]
                if not same_man(records[i], records[j], window=window):
                    continue
                if company is not None:
                    na, nb = records[i]["name"], records[j]["name"]
                    ok = company.confirms(na, nb) if require_confirm else not company.vetoes(na, nb)
                    if not ok:
                        continue
                parent[find(i)] = find(j)

        clusters: dict[int, list[int]] = defaultdict(list)
        for i in idxs:
            clusters[find(i)].append(i)
        for cluster in clusters.values():
            if len(cluster) < 2:
                continue
            primary = _pick_primary(cluster, records)
            for i in cluster:
                if i != primary:
                    _merge_into(records[primary], records[i])
                    drop.add(i)

    return [r for i, r in enumerate(records) if i not in drop], len(drop)

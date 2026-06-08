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

from collections import defaultdict

from app.parsing.normalize import normalize_for_search
from app.rijal.grades import classify

_BIN = {normalize_for_search(w) for w in ("بن", "ابن")}                 # patronymic links
_GEN = {normalize_for_search(w) for w in                                # «… الكبير» ≠ «… حفيده»
        ("الكبير", "الأكبر", "الحفيد", "حفيد", "الأصغر", "الصغير", "الابن", "الأب", "الجد")}
_TRUSTED_RANK = 5     # rank ≥ this is a "trusted" verdict (ثقة/صدوق/مقبول/صحابي); below it is weak


def _fold(text: str | None) -> str:
    return normalize_for_search(text or "")


def ident_key(name: str) -> tuple[str, ...]:
    """«ism + first nasab»: folded tokens up to and including the first patronymic link —
    «الليث بن سعد بن عبد الرحمن الفهمي» and «الليث بن سعد أبو الحارث» both key on (الليث، سعد)."""
    toks = [t for t in (normalize_for_search(w) for w in name.split()) if t]
    for i, t in enumerate(toks):
        if t in _BIN:
            return tuple(x for x in toks[: i + 2] if x not in _BIN)
    return tuple(toks[:3])                                              # no nasab → first 3 tokens


def tokens(name: str) -> set[str]:
    return {t for t in (normalize_for_search(w) for w in name.split()) if t and t not in _BIN}


def nisbas(toks: set[str]) -> set[str]:
    """Nisba-like tokens: «الـ…ـي» (الدمشقي، الكوفي، الفهمي) — a place/tribe discriminator."""
    return {t for t in toks if t.startswith("ال") and t.endswith("ي") and len(t) >= 4}


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


def collapse_duplicates(records: list[dict], *, window: int = 20) -> tuple[list[dict], int]:
    """Return ``(deduped_records, removed)`` — same-man duplicates collapsed into one entry.

    Groups by ``ident_key``, unions entries by :func:`same_man` (transitively), and merges each
    cluster into its primary. Order is otherwise preserved."""
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
                if same_man(records[i], records[j], window=window):
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

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


def _companion_split(a: dict, b: dict) -> bool:
    """The طبقة guard: a صحابي and a definite non-صحابي of the same name are DIFFERENT men (a Companion
    and a later تابعي can't be one person), so a thin «محمد بن عبد الله» (صحابي, الإصابة) is never folded
    into «… بن عمرو الكوفي» (ثقة تابعي). Ungraded never splits — it could be the same Companion not yet
    graded. (صحابي vs ثقة is not a `_strong_grade_conflict` — both are «trusted» — so this is the lever
    that catches the era boundary the grade-rank can't see.)"""
    ca = classify(a.get("grade") or "")[0]
    cb = classify(b.get("grade") or "")[0]
    return (ca == "صحابي") != (cb == "صحابي") and "غير معروف" not in (ca, cb)


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
    aliases = primary.setdefault("aliases", [])          # keep the merged form(s) searchable (a كنية
    for name in [other.get("name"), *(other.get("aliases") or [])]:   # «أبو أسيد الساعدي» citation still matches)
        if name and name != primary.get("name") and name not in aliases:
            aliases.append(name)


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

    Groups by ``ident_key`` and unions entries by TWO same-man paths (transitively): :func:`same_man`
    (nisba/death/kunya evidence) **and** a prudent built↔built *prefix-extension* — a thin short form
    («عبد الله بن قيس») folded into its single fuller man («… أبو موسى الأشعري») when the discriminators
    :func:`same_man` needs are simply absent, held whenever the short fits ≥2 distinct namesakes or
    crosses the صحابي/non-صحابي طبقة. A :class:`CorpusCompany`, when supplied, gates the merge against
    the chain network:

    * **mix** (default, ``require_confirm=False``) — for :func:`same_man` the name proposes and the
      corpus only **vetoes** a merge it positively contradicts (disjoint company); absent men are
      trusted to the name. The *prefix-extension* one-man fold is name-conclusive (one-man + lineage +
      طبقة), so under mix it is **not** vetoed — the veto there only re-strands a coverage doubling
      (الإصابة/الثقات) that a STALE graph happens to cite as two nodes (the dedup-before-graph circularity).
    * **strict** (``require_confirm=True``) — merge only what the corpus **confirms** (same company),
      for both paths.

    With no company it is name-only. Iterated to a FIXPOINT over BOTH `_collapse_once` (the ident_key
    groups) and `_kunya_shadow_once` (the cross-ident_key كنية/«ابن» shadows): a merge in either can free
    a fold the other had to hold (a removed namesake; a now-unique fuller), so we re-run until a pass
    removes nothing. Order is otherwise preserved."""
    total = 0
    while True:
        records, r1 = _collapse_once(records, window=window, company=company,
                                     require_confirm=require_confirm)
        records, r2 = _kunya_shadow_once(records, company=company, require_confirm=require_confirm)
        total += r1 + r2
        if not (r1 + r2):
            return records, total


def _collapse_once(
    records: list[dict], *, window: int,
    company: "CorpusCompany | None", require_confirm: bool,
) -> tuple[list[dict], int]:
    """One pass of :func:`collapse_duplicates` (which iterates this to a fixpoint)."""
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

        # «نقص قرينة» (built↔built prefix-extension): a thin short form — no nisba/death/kunya, so
        # :func:`same_man` can't confirm it — folded into its SINGLE fuller man («عبد الله بن قيس» →
        # «… أبو موسى الأشعري»). Held when the short fits ≥2 distinct namesakes (``_all_nested`` →
        # honest homonymy) or crosses the صحابي/non-صحابي طبقة (``_companion_split`` → different era).
        gtoks = {i: tokens(records[i].get("name", "")) for i in idxs}
        for i in idxs:
            supersets = [j for j in idxs
                         if j != i and gtoks[i] < gtoks[j]
                         and lineage_compatible(records[i], records[j])
                         and (gtoks[i] & _GEN) == (gtoks[j] & _GEN)
                         and not _strong_grade_conflict(records[i], records[j])
                         and not _companion_split(records[i], records[j])]
            if not (supersets and _all_nested([gtoks[j] for j in supersets])):
                continue
            for j in supersets:
                if require_confirm and company is not None \
                        and not company.confirms(records[i]["name"], records[j]["name"]):
                    continue          # strict needs corpus confirmation; mix TRUSTS the one-man fold
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


def _kunya_shadow_once(
    records: list[dict], *, company: "CorpusCompany | None", require_confirm: bool,
) -> tuple[list[dict], int]:
    """One pass folding a كنية-led / «ابن X» SHADOW into its fuller ism-led man — the cross-``ident_key``
    class (step 5): «أبو أسيد الساعدي» (a coverage Companion, الإصابة) into «مالك بن ربيعة … أبو أسيد
    الساعدي» (تقريب), which `collapse_duplicates` never compares because their ``ident_key`` differs. The
    shadow must appear as a CONTIGUOUS run in the right structural slot — a كنية NOT after «بن» (the
    subject's own, not a father's «… بن أبي أمية»), an «ابن X» as a nasab ancestor — fit exactly ONE man
    (`_all_nested`), share the طبقة (`_companion_split`), and not clash on grade. Held otherwise (honest
    homonymy). The fuller name survives; the shadow becomes an alias (so a كنية citation still matches)."""
    n = len(records)
    toks = [tokens(r.get("name", "")) for r in records]
    fseq = [folded_seq(r.get("name", "")) for r in records]
    keys = [ident_key(r.get("name", "")) for r in records]
    posting: dict[str, list[int]] = defaultdict(list)
    for i, ts in enumerate(toks):
        for t in ts:
            posting[t].append(i)

    parent = {i: i for i in range(n)}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    merged = False
    for i in range(n):
        if not fseq[i] or len(toks[i]) < 2:
            continue
        if fseq[i][0] in _KUNYA_P:
            sub, want_bin = fseq[i], False
        elif fseq[i][0] in _BIN:
            sub, want_bin = fseq[i][1:], True
        else:
            continue
        probe = min(toks[i], key=lambda t: len(posting.get(t, ())))   # rarest token → small scan
        fulls = []
        for j in posting.get(probe, ()):
            if j == i or keys[j] == keys[i] or not (toks[i] < toks[j]):
                continue
            pos = _run_at(sub, fseq[j])
            if pos < 0:
                continue
            after_bin = pos > 0 and fseq[j][pos - 1] in _BIN
            at_tail = pos + len(sub) == len(fseq[j])
            if want_bin and not (after_bin or at_tail):     # «ابن X»: X must sit in the nasab
                continue
            if not want_bin and after_bin:                  # كنية: the subject's own, not a father's
                continue
            if _companion_split(records[i], records[j]):    # a صحابي كنية ≠ a تابعي of that kunya
                continue
            fulls.append(j)
        if not fulls or not _all_nested([toks[j] for j in fulls]):  # ≥2 distinct men → honest homonymy → hold
            continue
        if _strong_grade_conflict(records[i], records[fulls[0]]):
            continue
        for j in fulls:
            if require_confirm and company is not None \
                    and not company.confirms(records[i]["name"], records[j]["name"]):
                continue                                    # strict needs corpus confirmation; mix trusts it
            parent[find(i)] = find(j)
            merged = True

    if not merged:
        return records, 0
    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(i)
    drop: set[int] = set()
    for cluster in clusters.values():
        if len(cluster) < 2:
            continue
        primary = _pick_primary(cluster, records)
        for i in cluster:
            if i != primary:
                _merge_into(records[primary], records[i])
                drop.add(i)
    return [r for i, r in enumerate(records) if i not in drop], len(drop)


# ── seed ↔ built reconciliation (the canonical base: one record per famous man) ───────────────────
# The curated seed (92 famous narrators, short canonical names) is overlaid on the built رجال base at
# LOAD time — AFTER the build-time collapse_duplicates — so the seed «هشام بن عروة» doubles the built
# «هشام بن عروة بن الزبير الأسدي». This folds each seed entry into its unambiguous full built form.
def folded_seq(name: str) -> list[str]:
    """Folded name tokens in order, «بن/ابن» kept (so the nasab structure stays readable)."""
    return [t for t in (normalize_for_search(w) for w in (name or "").split()) if t]


def _run_at(sub: list[str], full: list[str]) -> int:
    """Start index where ``sub`` occurs as a contiguous run in ``full``, else -1."""
    if not sub or len(sub) > len(full):
        return -1
    for s in range(len(full) - len(sub) + 1):
        if full[s:s + len(sub)] == sub:
            return s
    return -1


def _all_nested(tsets: list[set]) -> bool:
    """Are these token-sets pairwise nested (one ⊆ the other) — i.e. plausibly ONE man, not several
    distinct namesakes? Refuses an AMBIGUOUS seed→built fold (عمر بن الخطاب + obscure namesakes)."""
    for a in range(len(tsets)):
        for b in range(a + 1, len(tsets)):
            if not (tsets[a] <= tsets[b] or tsets[b] <= tsets[a]):
                return False
    return True


def _fold_seed_into(built: dict, seed: dict) -> None:
    """One canonical record: the fuller BUILT name survives, carrying the SEED's authoritative grade
    (the curated 92 are hand-verified — this also corrects a mis-extracted built verdict) and both
    sources' opinions; the seed's short form is kept as an alias so an exact citation still reaches him."""
    ops = built.setdefault("opinions", _opinions_of(built)[:])
    have = {o["source"] for o in ops}
    for op in _opinions_of(seed):
        if op["source"] not in have:
            ops.append(op)
            have.add(op["source"])
    if seed.get("grade"):
        built["grade"] = seed["grade"]                  # curated grade wins (عمر الفاروق صحابي, not ثقة)
        built["source"] = seed.get("source") or built.get("source")
    for field in ("death_year", "kunya"):
        if not built.get(field) and seed.get(field):
            built[field] = seed[field]
    aliases = built.setdefault("aliases", [])
    if seed.get("name") and seed["name"] != built["name"] and seed["name"] not in aliases:
        aliases.append(seed["name"])


def reconcile_seed(seed: list[dict], built: list[dict]) -> list[dict]:
    """Fold each curated SEED entry into its UNAMBIGUOUS full built form — so the canonical base carries
    ONE record per famous man, not the seed «هشام بن عروة» beside the built «… بن الزبير الأسدي». The
    fuller built name survives with the seed's authoritative grade + both opinions. A seed that fits
    SEVERAL distinct built men (عمر بن الخطاب + obscure namesakes) is HELD — kept as its own record,
    never fused (لا نختلق). Built entries with no seed match pass through unchanged. Both ism-led
    («هشام بن عروة») and كنية/«ابن»-led («أبو سعيد الخدري») seed forms are placed, each in the right slot."""
    result = [dict(b) for b in built]
    btoks = [tokens(b.get("name", "")) for b in result]
    bseq = [folded_seq(b.get("name", "")) for b in result]
    posting: dict[str, list[int]] = defaultdict(list)
    for i, ts in enumerate(btoks):
        for t in ts:
            posting[t].append(i)

    for s in seed:
        stoks = tokens(s.get("name", ""))
        if len(stoks) < 2:                              # too generic to place safely
            result.append(dict(s))
            continue
        sseq = folded_seq(s.get("name", ""))
        ibn_led, kunya_led = sseq[0] in _BIN, sseq[0] in _KUNYA_P
        probe = min(stoks, key=lambda t: len(posting.get(t, ())))
        matches: list[int] = []
        for j in posting.get(probe, ()):
            if not stoks < btoks[j]:                    # the seed must be a proper subset of the full
                continue
            if kunya_led or ibn_led:                    # a كنية/«ابن» form → require the right slot
                sub = sseq[1:] if ibn_led else sseq
                pos = _run_at(sub, bseq[j])
                if pos < 0:
                    continue
                after_bin = pos > 0 and bseq[j][pos - 1] in _BIN
                at_tail = pos + len(sub) == len(bseq[j])
                if ibn_led and not (after_bin or at_tail):    # «ابن X»: X sits in the nasab
                    continue
                if kunya_led and after_bin:                   # كنية: the subject's own, not a father
                    continue
            elif not (lineage_compatible(s, result[j]) and (stoks & _GEN) == (btoks[j] & _GEN)):
                continue
            matches.append(j)
        if matches and _all_nested([btoks[j] for j in matches]):
            _fold_seed_into(result[max(matches, key=lambda j: len(btoks[j]))], s)
        else:
            result.append(dict(s))                      # no match, or ambiguous → keep the seed
    return result

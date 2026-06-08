"""Takhrij (تخريج): locate the parallel narrations of a hadith across the corpus.

Given a matn, we find other hadith that report the *same* hadith — transmitted
through different collections/chains, often with different wording. Lexical wording
similarity is the *overlap coefficient* of normalised token sets (shared ÷ smaller
set), robust to length differences; when a vector index is available we also match
by *meaning*, so paraphrases ("بمعناه") are caught, not just verbatim parallels.

:func:`analyze_narrations` does the full job: gather every narration (lexical +
semantic recall, no cap), keep only those that are the same report (not merely the
same topic), then **cluster** them into distinct wordings (صيغ) and label each by how
close it is to the source — بِلفظه (verbatim) · بنحوه (near-wording) · بمعناه (by
meaning). :func:`find_parallels` keeps the simple flat list for callers that want it.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache

from app.parsing.normalize import normalize_for_search
from app.qa.rulings import extract_rulings, refine_with_routes
from app.search import HadithIndex, SearchHit
from app.search.embeddings import Embedder, cosine
from app.search.vectors import VectorIndex

# Tuning (overlap = lexical token overlap; sem = embedding cosine, when available):
_KEEP_OVERLAP = 0.40   # below this a candidate is the same *topic*, not the same report…
_KEEP_SEM = 0.78       # …unless it's very close in meaning (catches heavy paraphrase)
_MERGE_OVERLAP = 0.80  # two narrations this alike in wording are the *same* صيغة (variant)
_MERGE_SEM = 0.92      # …or this alike in meaning


def _term_set(text: str) -> set[str]:
    return set(normalize_for_search(text).split())


def _overlap(a: set[str], b: set[str]) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def _label(overlap: float) -> str:
    """How close a narration is to the source, in the muḥaddithīn's idiom."""
    if overlap >= 0.85:
        return "بلفظه"   # verbatim
    if overlap >= 0.60:
        return "بنحوه"   # near-wording
    return "بمعناه"      # by meaning (wording differs)


def _name_tokens(text: str) -> set[str]:
    """Folded tokens for *name* matching: unify the kunya cases أبو/أبا/أبي so a name
    written in the genitive in a chain («عن أبي هريرة») matches its nominative alias."""
    out = set()
    for t in normalize_for_search(text).split():
        out.add("ابو" if t in ("ابو", "ابا", "ابي") else t)
    return out


@lru_cache(maxsize=1)
def _companions() -> list[tuple[str, frozenset[str]]]:
    """Known Companions (الصحابة) as ``(canonical_name, alias_token_set)`` pairs, from the
    bundled rijal seed — the المكثرون and other well-known narrators. Used to recognise
    *who* a narration goes back to."""
    from app.rijal import load_seed

    out: list[tuple[str, frozenset[str]]] = []
    for entry in load_seed():
        if entry.get("grade") not in ("صحابي", "صحابية"):
            continue
        for form in (entry["name"], *entry.get("aliases", [])):
            toks = frozenset(_name_tokens(form))
            if toks:
                out.append((entry["name"], toks))
    # Longer alias token-sets first, so the most specific name wins on a match.
    out.sort(key=lambda pair: -len(pair[1]))
    return out


def _companion_of(isnad: str, matn: str) -> str | None:
    """The Companion a narration goes back to: the known Companion whose name appears in
    the chain (or, if the isnad isn't separated, in the matn). ``None`` if unrecognised."""
    chain = _name_tokens(isnad)
    body = _name_tokens(matn)
    for name, alias in _companions():
        if alias <= chain or alias <= body:
            return name
    return None


def _takhrij_line(narrations: list[dict]) -> str:
    """Classical «أخرجه» summary: each collection with the hadith numbers it reports under."""
    by_book: dict[str, list[str]] = defaultdict(list)
    for n in narrations:
        num = n.get("number")
        if num is not None and str(num) not in by_book[n["collection"]]:
            by_book[n["collection"]].append(str(num))
    parts = [f"{book} ({'، '.join(nums)})" if nums else book for book, nums in by_book.items()]
    return "أخرجه " + " · ".join(parts) if parts else ""


def find_parallels(
    matn: str,
    hadith_index: HadithIndex,
    *,
    exclude_id: int | None = None,
    limit: int | None = 20,
    min_overlap: float = 0.5,
) -> list[tuple[float, SearchHit]]:
    """Return ``(overlap, hit)`` for hadith whose matn overlaps ``matn`` by at least
    ``min_overlap``, best first. ``exclude_id`` drops the source hadith itself.
    ``limit=None`` scans and returns every parallel (no cap)."""
    source = _term_set(matn)
    if not source:
        return []
    scored: list[tuple[float, SearchHit]] = []
    seen: set[tuple[int, int | None]] = set()
    pool = None if limit is None else limit * 5
    for hit in hadith_index.search(matn, field="matn", limit=pool):
        if hit.id == exclude_id:
            continue
        terms = _term_set(hit.matn)
        if not terms:
            continue
        overlap = len(source & terms) / min(len(source), len(terms))
        if overlap < min_overlap:
            continue
        key = (hit.book_id, hit.number)  # collapse exact duplicates within a book
        if key in seen:
            continue
        seen.add(key)
        scored.append((round(overlap, 3), hit))
    scored.sort(key=lambda pair: (-pair[0], -pair[1].score))
    return scored if limit is None else scored[:limit]


def _cluster(items: list[dict], vecs: dict[int, list[float]]) -> list[list[dict]]:
    """Group narrations into distinct wordings (صيغ): union any two that are nearly the
    same in wording (or meaning). Connected components → one cluster per variant."""
    n = len(items)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        parent[find(a)] = find(b)

    for i in range(n):
        for j in range(i + 1, n):
            ov = _overlap(items[i]["terms"], items[j]["terms"])
            sem = 0.0
            if vecs:
                vi, vj = vecs.get(items[i]["hit"].id), vecs.get(items[j]["hit"].id)
                if vi and vj:
                    sem = cosine(vi, vj)
            if ov >= _MERGE_OVERLAP or sem >= _MERGE_SEM:
                union(i, j)

    groups: dict[int, list[dict]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(items[i])
    return list(groups.values())


def _narration(item: dict) -> dict:
    hit = item["hit"]
    return {
        "id": hit.id,
        "book_id": hit.book_id,
        "collection": hit.collection,
        "number": hit.number,
        "grade": hit.grade,
        "chapter": hit.chapter,
        "volume": hit.volume,
        "page": hit.page,
        "matn": hit.matn,
        "isnad": hit.isnad,
        "companion": item.get("companion"),
        "overlap": item["overlap"],
        "semantic": item["semantic"],
        "label": _label(item["overlap"]),
        "rulings": extract_rulings(hit.matn),
    }


def analyze_narrations(
    matn: str,
    hadith_index: HadithIndex,
    *,
    exclude_id: int | None = None,
    vectors: VectorIndex | None = None,
    embedder: Embedder | None = None,
    min_overlap: float = _KEEP_OVERLAP,
    max_candidates: int = 3000,   # scan pool — high enough to cover even widespread reports
) -> dict:
    """Full takhrij of ``matn``: every narration of the same report, grouped into
    distinct wordings (صيغ) and labelled by closeness to the source.

    Recall is hybrid — lexical wording plus, when a vector index is given, meaning —
    so paraphrased narrations are found too. Narrations are grouped by **Companion**
    (who the report goes back to); within each Companion they're clustered into distinct
    wordings (صيغ) and labelled by closeness, and each Companion carries an «أخرجه»
    summary (which collections, with numbers). Returns counts + a by-collection tally."""
    source_terms = _term_set(matn)
    if not source_terms:
        return {"total": 0, "companions": 0, "variants": 0, "by_collection": {}, "groups": []}

    # 1) Gather candidates: lexical (wording) + semantic (meaning), de-duplicated by id.
    #    Use OR recall so differently-worded narrations surface even when a verbatim
    #    parallel exists (AND-first would stop at the exact matches).
    candidates: dict[int, SearchHit] = {}
    for hit in hadith_index.search(matn, field="matn", limit=max_candidates, match="or"):
        if hit.id != exclude_id:
            candidates[hit.id] = hit

    semantic_on = vectors is not None and embedder is not None and bool(vectors.count())
    qvec = embedder.embed([matn])[0] if semantic_on else None
    if semantic_on and qvec is not None:
        for rid, _ in vectors.search(qvec, k=max_candidates):
            if rid != exclude_id and rid not in candidates:
                hit = hadith_index.get(rid)
                if hit is not None:
                    candidates[hit.id] = hit
    cand_vecs = vectors.vectors_for(list(candidates)) if semantic_on else {}

    # 2) Keep only narrations of the *same* report (same wording or very close meaning),
    #    collapsing exact (book, number) duplicates and keeping the best score.
    best: dict[tuple[int, int | None], dict] = {}
    for hit in candidates.values():
        terms = _term_set(hit.matn)
        if not terms:
            continue
        overlap = _overlap(source_terms, terms)
        sem = cosine(qvec, cand_vecs[hit.id]) if (qvec is not None and hit.id in cand_vecs) else 0.0
        if overlap < min_overlap and sem < _KEEP_SEM:
            continue
        key = (hit.book_id, hit.number)
        item = {
            "hit": hit,
            "terms": terms,
            "overlap": round(overlap, 3),
            "semantic": round(sem, 3),
            "companion": _companion_of(hit.isnad or "", hit.matn or ""),
        }
        if key not in best or overlap > best[key]["overlap"]:
            best[key] = item
    items = list(best.values())
    if not items:
        return {"total": 0, "companions": 0, "variants": 0, "by_collection": {}, "groups": []}

    # 3) Group by Companion (who it goes back to); within each, cluster into wordings (صيغ).
    by_companion: dict[str | None, list[dict]] = defaultdict(list)
    for item in items:
        by_companion[item["companion"]].append(item)

    groups: list[dict] = []
    total_variants = 0
    for companion, members in by_companion.items():
        variants: list[dict] = []
        for cluster in _cluster(members, cand_vecs):
            cluster.sort(key=lambda m: -m["overlap"])
            closeness = max(m["overlap"] for m in cluster)
            variants.append(
                {
                    "label": _label(closeness),
                    "closeness": closeness,
                    "count": len(cluster),
                    "narrations": [_narration(m) for m in cluster],
                }
            )
        variants.sort(key=lambda v: (-v["closeness"], -v["count"]))
        total_variants += len(variants)
        flat = [n for v in variants for n in v["narrations"]]
        groups.append(
            {
                "companion": companion,
                "count": len(members),
                "variants_count": len(variants),
                "collections": sorted({m["hit"].collection for m in members}),
                "takhrij": _takhrij_line(flat),
                "variants": variants,
            }
        )
    # Identified Companions first (most-narrated first); the unidentified group last.
    groups.sort(key=lambda g: (g["companion"] is None, -g["count"]))

    # Resolve «حسن صحيح» with the actual number of chains seen (source + parallels):
    # more than one ⇒ صحيح from a way, حسن from another; a single one ⇒ imams differed.
    routes = len(items) + 1
    for g in groups:
        for v in g["variants"]:
            for n in v["narrations"]:
                refine_with_routes(n["rulings"], routes)

    by_collection = Counter(m["hit"].collection for m in items)
    return {
        "total": len(items),
        "companions": sum(1 for g in groups if g["companion"] is not None),
        "variants": total_variants,
        "by_collection": dict(by_collection),
        "groups": groups,
    }

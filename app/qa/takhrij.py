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

from app.parsing.normalize import normalize_for_search
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
        "page": hit.page,
        "matn": hit.matn,
        "isnad": hit.isnad,
        "overlap": item["overlap"],
        "semantic": item["semantic"],
        "label": _label(item["overlap"]),
    }


def analyze_narrations(
    matn: str,
    hadith_index: HadithIndex,
    *,
    exclude_id: int | None = None,
    vectors: VectorIndex | None = None,
    embedder: Embedder | None = None,
    min_overlap: float = _KEEP_OVERLAP,
    max_candidates: int = 400,
) -> dict:
    """Full takhrij of ``matn``: every narration of the same report, grouped into
    distinct wordings (صيغ) and labelled by closeness to the source.

    Recall is hybrid — lexical wording plus, when a vector index is given, meaning —
    so paraphrased narrations are found too. Returns counts, a by-collection tally,
    and ``groups`` (one per variant, best/closest first)."""
    source_terms = _term_set(matn)
    if not source_terms:
        return {"total": 0, "variants": 0, "by_collection": {}, "groups": []}

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
        item = {"hit": hit, "terms": terms, "overlap": round(overlap, 3), "semantic": round(sem, 3)}
        if key not in best or overlap > best[key]["overlap"]:
            best[key] = item
    items = list(best.values())
    if not items:
        return {"total": 0, "variants": 0, "by_collection": {}, "groups": []}

    # 3) Cluster the narrations into distinct wordings, then describe each group.
    groups: list[dict] = []
    for members in _cluster(items, cand_vecs):
        members.sort(key=lambda m: -m["overlap"])
        closeness = max(m["overlap"] for m in members)
        groups.append(
            {
                "label": _label(closeness),
                "closeness": closeness,
                "semantic": max(m["semantic"] for m in members),
                "count": len(members),
                "collections": sorted({m["hit"].collection for m in members}),
                "narrations": [_narration(m) for m in members],
            }
        )
    groups.sort(key=lambda g: (-g["closeness"], -g["count"]))

    by_collection = Counter(m["hit"].collection for m in items)
    return {
        "total": len(items),
        "variants": len(groups),
        "by_collection": dict(by_collection),
        "groups": groups,
    }

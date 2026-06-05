"""Takhrij (تخريج): locate the parallel narrations of a hadith across the corpus.

Given a matn, we find other hadith whose wording substantially overlaps it — the
same report transmitted through different collections/chains. Similarity is the
*overlap coefficient* of normalised token sets (shared ÷ smaller set), which is
robust to length differences (a short matn quoted inside a longer one still scores
high). Lexical for now; an embedding backend can later widen recall to paraphrases.
"""

from __future__ import annotations

from app.parsing.normalize import normalize_for_search
from app.search import HadithIndex, SearchHit


def _term_set(text: str) -> set[str]:
    return set(normalize_for_search(text).split())


def find_parallels(
    matn: str,
    hadith_index: HadithIndex,
    *,
    exclude_id: int | None = None,
    limit: int = 20,
    min_overlap: float = 0.5,
) -> list[tuple[float, SearchHit]]:
    """Return ``(overlap, hit)`` for hadith whose matn overlaps ``matn`` by at least
    ``min_overlap``, best first. ``exclude_id`` drops the source hadith itself."""
    source = _term_set(matn)
    if not source:
        return []
    scored: list[tuple[float, SearchHit]] = []
    seen: set[tuple[int, int | None]] = set()
    for hit in hadith_index.search(matn, field="matn", limit=limit * 5):
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
    return scored[:limit]

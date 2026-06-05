"""The /takhrij endpoint: find a hadith's parallel narrations across collections.

Pass ``hadith_id`` (an indexed hadith) or a free ``q`` matn. Returns the parallels
grouped by collection, each with its citation and grade.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query

from app.qa.takhrij import find_parallels
from app.routers.search import get_index
from app.search import HadithIndex

router = APIRouter(tags=["takhrij"])


def _parallel(overlap: float, hit) -> dict:
    return {
        "id": hit.id,
        "book_id": hit.book_id,
        "collection": hit.collection,
        "number": hit.number,
        "grade": hit.grade,
        "chapter": hit.chapter,
        "page": hit.page,
        "matn": hit.matn,
        "overlap": overlap,
    }


@router.get("/takhrij")
def takhrij(
    hadith_id: int | None = Query(None, description="indexed hadith to trace"),
    q: str | None = Query(None, min_length=2, description="or a free matn text"),
    limit: int = Query(20, ge=1, le=100),
    min_overlap: float = Query(0.5, ge=0.1, le=1.0, description="min matn overlap (0–1)"),
    index: HadithIndex = Depends(get_index),
) -> dict:
    if hadith_id is not None:
        source_hit = index.get(hadith_id)
        if source_hit is None:
            raise HTTPException(status_code=404, detail="hadith not found")
        matn, source = source_hit.matn, source_hit.to_dict()
    elif q:
        matn, source = q, {"matn": q}
    else:
        raise HTTPException(status_code=422, detail="provide hadith_id or q")

    parallels = find_parallels(
        matn, index, exclude_id=hadith_id, limit=limit, min_overlap=min_overlap
    )
    by_collection = Counter(hit.collection for _, hit in parallels)
    return {
        "source": source,
        "count": len(parallels),
        "by_collection": dict(by_collection),
        "parallels": [_parallel(overlap, hit) for overlap, hit in parallels],
    }

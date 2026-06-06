"""Hadith search endpoints.

``GET /search`` ranks hadith by relevance to a query (lexical, Arabic-folded).
``GET /hadith/{id}`` returns a single indexed hadith with its citation.

The active index is provided by :func:`get_index` — a process-wide singleton that
opens the prebuilt sqlite index (``scripts.index``) or, for dev convenience, builds
one in memory from the parsed JSONL. Tests override this dependency.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings
from app.search import HadithIndex

router = APIRouter(tags=["search"])


@lru_cache(maxsize=1)
def get_index() -> HadithIndex:
    settings = get_settings()
    if settings.index_path.exists():
        return HadithIndex(settings.index_path)
    if settings.processed_dir.exists() and any(settings.processed_dir.glob("*.jsonl")):
        return HadithIndex.build_from_processed(settings.processed_dir)
    return HadithIndex()  # empty — /search returns no results until the corpus is built


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, description="Arabic query (diacritics optional)"),
    field: str = Query("all", pattern="^(all|matn|isnad)$"),
    collection: int | None = Query(None, description="restrict to a collection (book id)"),
    grade: str | None = Query(None, description="restrict to an authenticity grade"),
    limit: int | None = Query(None, ge=1, description="cap results; omit for all matches"),
    index: HadithIndex = Depends(get_index),
) -> dict:
    hits = index.search(
        q, limit=limit, collection_id=collection, grade=grade, field=field
    )
    return {"query": q, "count": len(hits), "results": [h.to_dict() for h in hits]}


@router.get("/hadith/{hadith_id}")
def get_hadith(hadith_id: int, index: HadithIndex = Depends(get_index)) -> dict:
    hit = index.get(hadith_id)
    if hit is None:
        raise HTTPException(status_code=404, detail="hadith not found")
    return hit.to_dict()

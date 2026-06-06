"""The /takhrij endpoint: a full survey of a hadith's narrations across the corpus.

Pass ``hadith_id`` (an indexed hadith) or a free ``q`` matn. Returns *every* narration
of the same report (lexical + semantic recall, no cap), grouped into distinct wordings
(صيغ) and labelled by closeness to the source — بِلفظه / بنحوه / بمعناه — plus a
by-collection tally and a flat ``parallels`` list. Uses the semantic index when built.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.qa.takhrij import analyze_narrations
from app.routers.search import get_embedder, get_index, get_vectors
from app.search import HadithIndex, VectorIndex
from app.search.embeddings import Embedder

router = APIRouter(tags=["takhrij"])


@router.get("/takhrij")
def takhrij(
    hadith_id: int | None = Query(None, description="indexed hadith to trace"),
    q: str | None = Query(None, min_length=2, description="or a free matn text"),
    min_overlap: float = Query(0.4, ge=0.1, le=1.0, description="min matn overlap to keep (0–1)"),
    index: HadithIndex = Depends(get_index),
    vectors: VectorIndex | None = Depends(get_vectors),
    embedder: Embedder | None = Depends(get_embedder),
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

    analysis = analyze_narrations(
        matn, index, exclude_id=hadith_id, vectors=vectors, embedder=embedder,
        min_overlap=min_overlap,
    )
    # Flat list (every narration, closest first) for callers that don't want the groups.
    parallels = sorted(
        (n for g in analysis["groups"] for v in g["variants"] for n in v["narrations"]),
        key=lambda n: -n["overlap"],
    )
    return {
        "source": source,
        "count": analysis["total"],
        "companions": analysis["companions"],
        "variants": analysis["variants"],
        "by_collection": analysis["by_collection"],
        "groups": analysis["groups"],
        "parallels": parallels,
    }

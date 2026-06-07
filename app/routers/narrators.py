"""The /narrator endpoint: a narrator's card (شبكة الرواة) — profile, grade, شيوخ/تلاميذ.

Thin wrapper over :func:`app.qa.dossier.narrator_dossier`; the graph is built by
``scripts.build_graph`` and the grade comes from the rijal database.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.qa.dossier import narrator_dossier
from app.rijal import RijalIndex
from app.rijal.graph import NarratorGraph
from app.routers.verify_isnad import get_graph, get_rijal

router = APIRouter(tags=["rijal"])


@router.get("/narrator")
def narrator(
    name: str = Query(..., min_length=2, description="narrator name (any common form)"),
    limit: int | None = Query(None, ge=1, description="max شيوخ / تلاميذ; omit for all"),
    graph: NarratorGraph | None = Depends(get_graph),
    rijal: RijalIndex = Depends(get_rijal),
) -> dict:
    if graph is None or not graph.count():
        raise HTTPException(
            status_code=503,
            detail="narrator graph not built — run `python -m scripts.build_graph`",
        )
    dossier = narrator_dossier(name, graph, rijal, limit=limit)
    if dossier is None:
        raise HTTPException(status_code=404, detail="narrator not found in the corpus")
    return dossier

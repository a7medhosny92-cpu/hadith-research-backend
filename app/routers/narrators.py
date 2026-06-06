"""The /narrator endpoint: explore a narrator's place in the network (شبكة الرواة).

Given a name, return who they narrate *from* (شيوخ) and who narrates *from* them
(تلاميذ), weighted by frequency in the corpus, plus the narrator's grade when the
rijal database knows them. The graph is built by ``scripts.build_graph``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.rijal import RijalIndex
from app.rijal.graph import NarratorGraph
from app.routers.verify_isnad import get_graph, get_rijal

router = APIRouter(tags=["rijal"])


@router.get("/narrator")
def narrator(
    name: str = Query(..., min_length=2, description="narrator name (any common form)"),
    limit: int = Query(50, ge=1, le=500, description="max شيوخ / تلاميذ to return"),
    graph: NarratorGraph | None = Depends(get_graph),
    rijal: RijalIndex = Depends(get_rijal),
) -> dict:
    if graph is None or not graph.count():
        raise HTTPException(
            status_code=503,
            detail="narrator graph not built — run `python -m scripts.build_graph`",
        )
    node = graph.resolve(name)
    if node is None:
        raise HTTPException(status_code=404, detail="narrator not found in the corpus")

    match = rijal.lookup(node.name)
    return {
        "name": node.name,
        "grade": match.to_dict() if match else None,
        "teachers": graph.teachers(node.name, limit=limit),   # شيوخ — narrates from
        "students": graph.students(node.name, limit=limit),   # تلاميذ — narrate from him
    }

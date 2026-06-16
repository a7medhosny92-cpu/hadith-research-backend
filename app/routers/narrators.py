"""The /narrator + /narrators endpoints: one narrator's card, and a browsable index of all.

``/narrator`` is a thin wrapper over :func:`app.qa.dossier.narrator_dossier`; the graph is
built by ``scripts.build_graph`` and the grade comes from the rijal database. ``/narrators``
lists every graded narrator (paged, with letter/درجة facets) so the user can *browse* the
رجال without searching — pick a letter or a grade and scroll, then open any card.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query

from app.parsing.normalize import normalize_for_search
from app.qa.dossier import narrator_dossier
from app.rijal import RijalIndex
from app.rijal.graph import NarratorGraph
from app.rijal.grades import RANKS
from app.rijal.index import _ALPHABET
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
    rijal.set_prominence(graph.frequencies())   # prominence prior → the candidate list prefers the prolific man
    dossier = narrator_dossier(name, graph, rijal, limit=limit)
    if dossier is None:
        raise HTTPException(status_code=404, detail="narrator not found in the corpus")
    return dossier


@router.get("/narrators")
def narrators_index(
    letter: str | None = Query(None, description="filter by first letter (folded)"),
    grade: str | None = Query(None, description="filter by درجة category"),
    q: str | None = Query(None, description="filter by a name substring"),
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=200),
    rijal: RijalIndex = Depends(get_rijal),
) -> dict:
    """Browse every graded narrator — paged, with letter + درجة facets. Each facet's counts
    respect the OTHER active filters (pick «ثقة» and the letter counts narrow to ثقات), so the
    chips stay honest. Items are ``{name, grade, death_year, kunya}``; click one → ``/narrator``."""
    rows = rijal.browse_rows()
    qn = normalize_for_search(q) if q else None

    def keep(r: dict, *, by_letter: bool = True, by_grade: bool = True) -> bool:
        if by_letter and letter and r["letter"] != letter:
            return False
        if by_grade and grade and r["grade"] != grade:
            return False
        if qn and qn not in normalize_for_search(r["name"]):
            return False
        return True

    letters = Counter(r["letter"] for r in rows if keep(r, by_letter=False))   # respects grade + q
    grades = Counter(r["grade"] for r in rows if keep(r, by_grade=False))       # respects letter + q
    filtered = [r for r in rows if keep(r)]
    return {
        "grand_total": len(rows),
        "total": len(filtered),
        "offset": offset,
        "limit": limit,
        "letters": [{"letter": ch, "count": letters.get(ch, 0)} for ch in _ALPHABET],
        "grades": [
            {"grade": g, "count": n}
            for g, n in sorted(grades.items(), key=lambda kv: (-(RANKS.get(kv[0]) or -1), kv[0]))
        ],
        "items": filtered[offset:offset + limit],
    }

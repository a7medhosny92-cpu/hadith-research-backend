"""The /verify-isnad endpoint: parse and structurally analyse a chain of narrators.

Pass ``hadith_id`` (use that hadith's isnad) or a free ``isnad`` string. Returns the
ordered narrators and chain features (transmission modes, تحويل, عنعنة, reach to the
Prophet ﷺ). Narrator grading needs a rijal database — flagged in the notes.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings
from app.qa.isnad import analyze_isnad
from app.rijal import RijalIndex, load_entries
from app.rijal.graph import NarratorGraph
from app.routers.search import get_index
from app.search import HadithIndex

router = APIRouter(tags=["isnad"])


@lru_cache(maxsize=1)
def _rijal_index() -> RijalIndex:
    return RijalIndex(load_entries(get_settings().rijal_path))


def get_rijal() -> RijalIndex:
    return _rijal_index()


@lru_cache(maxsize=1)
def _graph() -> NarratorGraph | None:
    path = get_settings().narrator_graph_path
    return NarratorGraph(path) if path.exists() else None


def get_graph() -> NarratorGraph | None:
    return _graph()


def _continuity(narrators: list[dict], graph: NarratorGraph) -> dict:
    """Check each link against the corpus network: is this تلميذ→شيخ pair ever recorded?

    A link never seen together is a flag for a possible break (انقطاع) — a *structural*
    hint from the texts, not a verdict on سماع."""
    links = []
    for student, teacher in zip(narrators, narrators[1:]):
        weight = graph.link_weight(student["name"], teacher["name"])
        links.append(
            {"from": student["name"], "to": teacher["name"], "count": weight, "seen": weight > 0}
        )
    seen = sum(1 for link in links if link["seen"])
    if not links:
        note = "السند قصير؛ لا حلقات للمقابلة."
    elif seen == len(links):
        note = "كلّ حلقات الإسناد لها رواية معروفة في النصوص."
    else:
        note = (
            f"{len(links) - seen} من {len(links)} حلقة لم تُعرف روايتها في النصوص؛ "
            "يُنظر في الاتصال (قد يكون انقطاعًا أو اختلاف صيغة الاسم)."
        )
    return {"links": links, "seen": seen, "total": len(links), "note": note}


@router.get("/verify-isnad")
def verify_isnad(
    hadith_id: int | None = Query(None, description="indexed hadith whose isnad to analyse"),
    isnad: str | None = Query(None, min_length=2, description="or a free isnad string"),
    index: HadithIndex = Depends(get_index),
    rijal: RijalIndex = Depends(get_rijal),
    graph: NarratorGraph | None = Depends(get_graph),
) -> dict:
    if hadith_id is not None:
        hit = index.get(hadith_id)
        if hit is None:
            raise HTTPException(status_code=404, detail="hadith not found")
        chain, source = hit.isnad, hit.to_dict()
    elif isnad:
        chain, source = isnad, {"isnad": isnad}
    else:
        raise HTTPException(status_code=422, detail="provide hadith_id or isnad")

    analysis = analyze_isnad(chain, rijal=rijal).to_dict()
    result = {"source": source, "analysis": analysis}
    if graph is not None and graph.count():
        result["continuity"] = _continuity(analysis["narrators"], graph)
    return result

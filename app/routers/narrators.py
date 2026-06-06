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

    grade = rijal.lookup(node.name)
    grade_d = grade.to_dict() if grade else None
    teachers = graph.teachers(node.name, limit=limit)   # شيوخ — narrates from
    students = graph.students(node.name, limit=limit)   # تلاميذ — narrate from him
    return {
        "name": node.name,
        "grade": grade_d,
        "summary": _summary(node.name, grade_d, teachers, students),
        "sources": _sources(grade_d),
        "teachers": teachers,
        "students": students,
    }


def _summary(name: str, grade: dict | None, teachers: list[dict], students: list[dict]) -> str:
    """A one-paragraph profile composed from what we know (rijal entry + the network)."""
    bits = [name]
    if grade and grade.get("kunya"):
        bits.append(f"({grade['kunya']})")
    if grade and grade.get("death_year"):
        bits.append(f"المتوفّى سنة {grade['death_year']}هـ")
    line = "، ".join(bits)
    if grade and grade.get("verdict"):
        line += f". الحُكم فيه: {grade['verdict']}"
    line += (
        f". يروي في النصوص المفهرسة عن {len(teachers)} شيخًا، "
        f"ويروي عنه {len(students)} راويًا"
    )
    if teachers:
        line += f"؛ من أبرز شيوخه: {'، '.join(t['name'] for t in teachers[:3])}"
    if students:
        line += f"، ومن أبرز تلاميذه: {'، '.join(s['name'] for s in students[:3])}"
    return line + "."


def _sources(grade: dict | None) -> list[dict]:
    """Where each part of the profile comes from — kept explicit and verifiable."""
    out: list[dict] = []
    if grade:
        out.append({
            "what": "الترجمة والحُكم",
            "from": grade.get("source") or "قاعدة الرجال (البذرة المنسّقة)",
        })
    else:
        out.append({"what": "الحُكم", "from": "غير مُدرَج في قاعدة الرجال الحالية"})
    out.append({
        "what": "الشيوخ والتلاميذ",
        "from": "مُستخرَجة من أسانيد الكتب المفهرسة على هذا الجهاز",
    })
    return out

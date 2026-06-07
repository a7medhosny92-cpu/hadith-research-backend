"""Assemble *dossiers* — complete, cross-linked cards for one entity, not one datum.

A **hadith dossier** brings together, for a single hadith: the متن + citation + grade,
its إسناد (with continuity), its تخريج (all narrations → variants → Companions), the
scholars' أحكام (by era), the relevant شروح, and brief cards for the narrators in the
chain. A **narrator dossier** is the راوٍ card: profile, grade, شيوخ/تلاميذ, sources.

This is the assembly layer: it reuses the existing engines (search, takhrij, isnad,
rulings, rijal, sharh) and just composes them, so every figure stays attributable.
"""

from __future__ import annotations

from app.qa.answer import _complete_sharh
from app.qa.isnad import analyze_isnad, continuity
from app.qa.rulings import collect_illal, collect_rulings, refine_with_routes
from app.qa.takhrij import analyze_narrations
from app.rijal import RijalIndex
from app.rijal.graph import is_unnamed_kin
from app.search import HadithIndex, SearchHit, SharhIndex, VectorIndex
from app.search.embeddings import Embedder


def _narrator_card(name: str, rijal: RijalIndex) -> dict:
    """A compact narrator chip for a chain: name + verdict + death year, when known."""
    match = rijal.lookup(name)
    d = match.to_dict() if match else None
    return {
        "name": name,
        "verdict": d.get("verdict") if d else None,
        "death_year": d.get("death_year") if d else None,
    }


def hadith_dossier(
    hit: SearchHit,
    *,
    hadith_index: HadithIndex,
    sharh_index: SharhIndex,
    rijal: RijalIndex,
    graph=None,
    vectors: VectorIndex | None = None,
    embedder: Embedder | None = None,
) -> dict:
    """Everything known about one hadith, in one card."""
    # شروح of this exact hadith, as complete passages.
    sharh = (
        sharh_index.by_hadith(hit.book_id, hit.number, limit=5)
        if hit.number is not None
        else []
    )
    sharh_sources = _complete_sharh(sharh, sharh_index)

    # Takhrij (all narrations → variants → Companions), then resolve «حسن صحيح» by routes.
    takhrij = analyze_narrations(
        hit.matn, hadith_index, exclude_id=hit.id, vectors=vectors, embedder=embedder
    )

    # Scholars' rulings from the matn + its شروح, ordered by era.
    ruling_texts = [hit.matn] + [s.get("text") or s.get("excerpt") or "" for s in sharh_sources]
    rulings = collect_rulings(ruling_texts)
    refine_with_routes(rulings, takhrij["total"] + 1)
    illal = collect_illal(ruling_texts)   # stated hidden defects (علل)

    # Isnad structure + continuity against the network.
    isnad = analyze_isnad(hit.isnad or "", rijal=rijal).to_dict()
    if graph is not None and graph.count():
        isnad["continuity"] = continuity(isnad["narrators"], graph)

    return {
        "kind": "hadith",
        "hadith": hit.to_dict(),
        "rulings": rulings,
        "illal": illal,
        "sharh": sharh_sources,
        "takhrij": takhrij,
        "isnad": isnad,
        "narrators": [_narrator_card(n["name"], rijal) for n in isnad["narrators"]],
    }


def narrator_summary(name: str, grade: dict | None, teachers: list[dict], students: list[dict]) -> str:
    """One-paragraph profile composed from the rijal entry + the network."""
    bits = [name]
    if grade and grade.get("kunya"):
        bits.append(f"({grade['kunya']})")
    if grade and grade.get("death_year"):
        bits.append(f"المتوفّى سنة {grade['death_year']}هـ")
    line = "، ".join(bits)
    if grade and grade.get("verdict"):
        line += f". الحُكم فيه: {grade['verdict']}"
    line += f". يروي في النصوص المفهرسة عن {len(teachers)} شيخًا، ويروي عنه {len(students)} راويًا"
    if teachers:
        line += f"؛ من أبرز شيوخه: {'، '.join(t['name'] for t in teachers[:3])}"
    if students:
        line += f"، ومن أبرز تلاميذه: {'، '.join(s['name'] for s in students[:3])}"
    return line + "."


def narrator_sources(grade: dict | None) -> list[dict]:
    out: list[dict] = []
    out.append(
        {"what": "الترجمة والحُكم", "from": grade.get("source") or "قاعدة الرجال (البذرة المنسّقة)"}
        if grade
        else {"what": "الحُكم", "from": "غير مُدرَج في قاعدة الرجال الحالية"}
    )
    out.append({"what": "الشيوخ والتلاميذ", "from": "مُستخرَجة من أسانيد الكتب المفهرسة على هذا الجهاز"})
    return out


def narrator_dossier(name: str, graph, rijal: RijalIndex, *, limit: int | None = None) -> dict | None:
    """The راوٍ card: profile + grade + شيوخ/تلاميذ + sources. ``None`` if unknown.
    ``limit=None`` returns **all** شيوخ/تلاميذ (no cap)."""
    node = graph.resolve(name) if graph is not None else None
    if node is None:
        return None
    # A synthetic «father/grandfather of X» node is a real but *unnamed* link — never
    # grade it (it would otherwise be mis-matched to X himself in the رijال database).
    grade = None if is_unnamed_kin(node.name) else rijal.lookup(node.name)
    grade_d = grade.to_dict() if grade else None

    def _graded(people: list[dict]) -> list[dict]:
        for p in people:                      # tag each neighbour with its grade (for the graph view)
            m = None if is_unnamed_kin(p["name"]) else rijal.lookup(p["name"])
            p["grade"] = m.entry.category if m else None
        return people

    teachers = _graded(graph.teachers(node.name, limit=limit))
    students = _graded(graph.students(node.name, limit=limit))
    return {
        "kind": "person",
        "name": node.name,
        "grade": grade_d,
        "summary": narrator_summary(node.name, grade_d, teachers, students),
        "sources": narrator_sources(grade_d),
        "teachers": teachers,
        "students": students,
    }

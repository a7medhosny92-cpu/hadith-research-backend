"""The /verify-isnad endpoint: parse and structurally analyse a chain of narrators.

Pass ``hadith_id`` (use that hadith's isnad) or a free ``isnad`` string. Returns the
ordered narrators and chain features (transmission modes, تحويل, عنعنة, reach to the
Prophet ﷺ). Narrator grading needs a rijal database — flagged in the notes.
"""

from __future__ import annotations

import json
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings
from app.qa.isnad import analyze_isnad, continuity, overall_ruling
from app.rijal import RijalIndex, load_entries
from app.rijal.canon import Canonicalizer
from app.rijal.graph import NarratorGraph
from app.rijal.index import _clean_tokens
from app.routers.search import get_index
from app.search import HadithIndex

router = APIRouter(tags=["isnad"])


@lru_cache(maxsize=1)
def _rijal_index() -> RijalIndex:
    # seed + the full رجال file (explicit RIJAL_PATH, else auto data/rijal.jsonl).
    return RijalIndex(load_entries(get_settings().rijal_file))


def get_rijal() -> RijalIndex:
    return _rijal_index()


@lru_cache(maxsize=1)
def _graph() -> NarratorGraph | None:
    path = get_settings().narrator_graph_path
    return NarratorGraph(path) if path.exists() else None


def get_graph() -> NarratorGraph | None:
    return _graph()


@lru_cache(maxsize=1)
def _canonicalizer() -> Canonicalizer:
    """A Canonicalizer whose «company» profiles come from the built network, so the verdict
    can identify a shared name (مهمل) from the chain it sits in — the same context tier the
    network uses. Falls back to context-free matching when no graph is present."""
    rijal = _rijal_index()
    graph = _graph()
    if graph is None or not graph.count():
        return Canonicalizer(rijal)
    profiles = {
        name: set().union(*(_clean_tokens(nb) for nb in neigh)) if neigh else set()
        for name, neigh in graph.adjacency().items()
    }
    return Canonicalizer(rijal, associations=profiles)


def get_canon() -> Canonicalizer:
    return _canonicalizer()


@router.get("/verify-isnad")
def verify_isnad(
    hadith_id: int | None = Query(None, description="indexed hadith whose isnad to analyse"),
    isnad: str | None = Query(None, min_length=2, description="or a free isnad string"),
    index: HadithIndex = Depends(get_index),
    rijal: RijalIndex = Depends(get_rijal),
    graph: NarratorGraph | None = Depends(get_graph),
    canon: Canonicalizer = Depends(get_canon),
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

    # canon resolves a shared name from the chain's company before grading (تمييز المهمل)
    analysis = analyze_isnad(chain, rijal=rijal, canon=canon).to_dict()
    result = {"source": source, "analysis": analysis}
    if graph is not None and graph.count():
        result["continuity"] = continuity(analysis["narrators"], graph)
    # The single bottom-line verdict «الحكم على الإسناد» (rijal + اتصال + عنعنة).
    result["ruling"] = overall_ruling(analysis, result.get("continuity"))
    return result


@router.get("/audit")
def audit() -> dict:
    """The prebuilt isnad-audit report (``scripts.audit_isnad``) for the «التدقيق» tab —
    the chains whose narrator grading is likely wrong, to be reviewed by hand. Returns
    ``{available: False}`` when the report hasn't been built yet."""
    path = get_settings().data_dir / "audit.json"
    if not path.exists():
        return {"available": False}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": False}
    report["available"] = True
    return report

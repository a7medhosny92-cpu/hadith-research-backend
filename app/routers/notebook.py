"""The /notebook endpoints: the user's study notebook (دفتر) — save items + notes.

Save a hadith, narrator, or answer with a personal note and tags; list/search them;
edit the note; delete. Stored locally and kept across updates (see app.notebook).
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.config import get_settings
from app.notebook import Notebook

router = APIRouter(tags=["notebook"])


@lru_cache(maxsize=1)
def get_notebook() -> Notebook:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return Notebook(settings.notebook_path)


@router.get("/notebook")
def list_notes(
    q: str | None = Query(None, description="filter across title/body/note/tags"),
    kind: str | None = Query(None, description="filter by kind (hadith|narrator|answer…)"),
    notebook: Notebook = Depends(get_notebook),
) -> dict:
    items = notebook.list(q, kind=kind)
    return {"count": len(items), "items": items}


@router.post("/notebook")
def add_note(payload: dict = Body(...), notebook: Notebook = Depends(get_notebook)) -> dict:
    title = (payload.get("title") or "").strip()
    if not title and not (payload.get("body") or "").strip():
        raise HTTPException(status_code=422, detail="title or body required")
    return notebook.add(
        kind=payload.get("kind") or "note",
        title=title,
        body=payload.get("body") or "",
        meta=payload.get("meta") or {},
        note=payload.get("note") or "",
        tags=payload.get("tags") or "",
    )


@router.patch("/notebook/{note_id}")
def edit_note(
    note_id: int, payload: dict = Body(...), notebook: Notebook = Depends(get_notebook)
) -> dict:
    updated = notebook.update(note_id, note=payload.get("note"), tags=payload.get("tags"))
    if updated is None:
        raise HTTPException(status_code=404, detail="note not found")
    return updated


@router.delete("/notebook/{note_id}")
def delete_note(note_id: int, notebook: Notebook = Depends(get_notebook)) -> dict:
    if not notebook.delete(note_id):
        raise HTTPException(status_code=404, detail="note not found")
    return {"deleted": note_id}

"""The /notebook endpoints: the user's study notebook (دفتر) — save items + notes.

Save a hadith, narrator, or answer with a personal note and tags; list/search them;
edit the note; delete. Stored locally and kept across updates (see app.notebook).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import get_settings
from app.notebook import Notebook

router = APIRouter(tags=["notebook"])


class NoteCreate(BaseModel):
    """A saved item. Typed so a wrong field type is a clean 422, not a 500."""
    kind: str = "note"
    title: str = ""
    body: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
    note: str = ""
    tags: str = ""


class NoteUpdate(BaseModel):
    note: str | None = None
    tags: str | None = None


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
def add_note(payload: NoteCreate, notebook: Notebook = Depends(get_notebook)) -> dict:
    title = payload.title.strip()
    if not title and not payload.body.strip():
        raise HTTPException(status_code=422, detail="title or body required")
    return notebook.add(
        kind=payload.kind or "note", title=title, body=payload.body,
        meta=payload.meta, note=payload.note, tags=payload.tags,
    )


@router.patch("/notebook/{note_id}")
def edit_note(
    note_id: int, payload: NoteUpdate, notebook: Notebook = Depends(get_notebook)
) -> dict:
    updated = notebook.update(note_id, note=payload.note, tags=payload.tags)
    if updated is None:
        raise HTTPException(status_code=404, detail="note not found")
    return updated


@router.delete("/notebook/{note_id}")
def delete_note(note_id: int, notebook: Notebook = Depends(get_notebook)) -> dict:
    if not notebook.delete(note_id):
        raise HTTPException(status_code=404, detail="note not found")
    return {"deleted": note_id}

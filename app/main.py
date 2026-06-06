"""FastAPI application entrypoint.

Run locally:  ``uvicorn app.main:app --reload``
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app import __version__
from app.routers import (
    admin, ask, dossier, health, narrators, notebook, search, takhrij, verify_isnad,
)

app = FastAPI(
    title="Hadith Research Backend",
    version=__version__,
    summary="Search, study and verify hadith (RAG, Classical Arabic) over the turath.io corpus.",
)

app.include_router(health.router)
app.include_router(search.router)
app.include_router(ask.router)
app.include_router(takhrij.router)
app.include_router(verify_isnad.router)
app.include_router(narrators.router)
app.include_router(dossier.router)
app.include_router(notebook.router)
app.include_router(admin.router)


@app.get("/", tags=["root"])
def root() -> dict:
    return {
        "name": "hadith-research-backend",
        "version": __version__,
        "docs": "/docs",
        "app": "/app",
        "endpoints": [
            "/dossier", "/search", "/hadith/{id}", "/ask", "/takhrij",
            "/verify-isnad", "/narrator", "/notebook",
        ],
    }


_UI_FILE = Path(__file__).parent / "static" / "index.html"


@app.get("/app", include_in_schema=False)
def desktop_ui() -> FileResponse:
    """The simple interactive UI — used by the native desktop window and any browser."""
    return FileResponse(_UI_FILE)

"""FastAPI application entrypoint.

Run locally:  ``uvicorn app.main:app --reload``
"""

from __future__ import annotations

from fastapi import FastAPI

from app import __version__
from app.routers import ask, health, search, takhrij, verify_isnad

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


@app.get("/", tags=["root"])
def root() -> dict:
    return {
        "name": "hadith-research-backend",
        "version": __version__,
        "docs": "/docs",
        "endpoints": ["/search", "/hadith/{id}", "/ask", "/takhrij", "/verify-isnad"],
        "endpoints_planned": ["semantic search & LLM synthesis (production)"],
    }

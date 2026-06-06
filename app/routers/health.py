"""Health and ingestion-status endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter

from app import __version__
from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/health/ingestion")
def ingestion_status() -> dict:
    """Summarise the resumable download manifest, if a crawl has started."""
    manifest_path = get_settings().raw_dir / "manifest.json"
    if not manifest_path.exists():
        return {"started": False, "books": 0}
    try:                                  # a crawl may be mid-write — don't 500 on that
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"started": True, "books": 0, "error": f"manifest unreadable: {exc}"}
    books = manifest.get("books", {})
    by_status: dict[str, int] = {}
    pages = 0
    for entry in books.values():
        status = entry.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        pages += entry.get("pages_fetched", 0)
    return {"started": True, "books": len(books), "pages_fetched": pages, "by_status": by_status}

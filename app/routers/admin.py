"""Admin: reload the in-memory index singletons after a rebuild.

The index/vector/graph/rijal/sharh providers are ``@lru_cache`` singletons that open
their sqlite file once. After re-running the build scripts (scripts.index / embed /
build_graph / build_rijal) a long-running server would keep serving the *old* data —
or error on a replaced file. POST ``/admin/reload`` closes the open handles and clears
the caches, so the next request reopens the fresh files (no restart needed).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.routers import ask, search, verify_isnad

router = APIRouter(tags=["admin"])

# The cached providers backed by on-disk files rebuilt by the scripts. (The notebook is
# deliberately excluded — it's written at request time and never rebuilt.)
_PROVIDERS = (
    search.get_index, search.get_vectors, search.get_embedder,
    ask.get_sharh_index, verify_isnad._rijal_index, verify_isnad._graph,
)


@router.post("/admin/reload")
def reload_indexes() -> dict:
    """Close and drop the cached index singletons so the next request reopens them."""
    reloaded = []
    for provider in _PROVIDERS:
        try:
            current = provider()
            if hasattr(current, "close"):
                current.close()
        except Exception:  # noqa: BLE001 — best-effort close; clear regardless
            pass
        provider.cache_clear()
        reloaded.append(provider.__name__)
    return {"reloaded": reloaded}

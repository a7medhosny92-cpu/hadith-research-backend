"""Hadith search endpoints.

``GET /search`` ranks hadith by relevance to a query (lexical, Arabic-folded).
``GET /hadith/{id}`` returns a single indexed hadith with its citation.

The active index is provided by :func:`get_index` — a process-wide singleton that
opens the prebuilt sqlite index (``scripts.index``) or, for dev convenience, builds
one in memory from the parsed JSONL. Tests override this dependency.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings
from app.qa.rulings import extract_rulings
from app.search import HadithIndex, HybridSearcher, VectorIndex
from app.search.embeddings import Embedder

router = APIRouter(tags=["search"])


@lru_cache(maxsize=1)
def get_index() -> HadithIndex:
    settings = get_settings()
    if settings.index_path.exists():
        return HadithIndex(settings.index_path)
    if settings.processed_dir.exists() and any(settings.processed_dir.glob("*.jsonl")):
        return HadithIndex.build_from_processed(settings.processed_dir)
    return HadithIndex()  # empty — /search returns no results until the corpus is built


@lru_cache(maxsize=1)
def get_vectors() -> VectorIndex | None:
    """The semantic index, if it's been built (``scripts.embed``); else ``None``."""
    settings = get_settings()
    return VectorIndex(settings.vector_index_path) if settings.vector_index_path.exists() else None


@lru_cache(maxsize=1)
def get_embedder() -> Embedder | None:
    """Load the query embedder only when there's a vector index to search."""
    settings = get_settings()
    if not settings.vector_index_path.exists():
        return None  # no vectors → don't pay to load a model
    from app.search.embeddings import load_embedder

    return load_embedder(settings)


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, description="Arabic query (diacritics optional)"),
    field: str = Query("all", pattern="^(all|matn|isnad)$"),
    collection: int | None = Query(None, description="restrict to a collection (book id)"),
    grade: str | None = Query(None, description="restrict to an authenticity grade"),
    limit: int | None = Query(None, ge=1, description="cap results; omit for all matches"),
    mode: str = Query(
        "lexical",
        pattern="^(lexical|semantic|hybrid)$",
        description="lexical (words, uncapped) | semantic (meaning) | hybrid (both, fused). "
        "semantic/hybrid need the vector index (scripts.embed) and are top-k.",
    ),
    index: HadithIndex = Depends(get_index),
    vectors: VectorIndex | None = Depends(get_vectors),
    embedder: Embedder | None = Depends(get_embedder),
) -> dict:
    searcher = HybridSearcher(index, vectors, embedder)
    # lexical stays uncapped (limit=None → all matches); semantic/hybrid are top-k.
    eff_limit = limit if mode == "lexical" else (limit or 50)
    hits = searcher.search(
        q, limit=eff_limit, collection_id=collection, grade=grade, field=field, mode=mode
    )
    effective = mode if (mode == "lexical" or searcher.semantic_ready()) else "lexical"
    return {
        "query": q,
        "mode": effective,
        "count": len(hits),
        "results": [_with_rulings(h.to_dict()) for h in hits],
    }


def _with_rulings(record: dict) -> dict:
    """Attach any scholars' verdicts stated in the matn itself (e.g. الترمذي's)."""
    record["rulings"] = extract_rulings(record.get("matn") or "")
    return record


@router.get("/hadith/{hadith_id}")
def get_hadith(hadith_id: int, index: HadithIndex = Depends(get_index)) -> dict:
    hit = index.get(hadith_id)
    if hit is None:
        raise HTTPException(status_code=404, detail="hadith not found")
    return _with_rulings(hit.to_dict())

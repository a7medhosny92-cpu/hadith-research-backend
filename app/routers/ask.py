"""The /ask endpoint: answer a question with hadith + scholarly commentary, cited.

Retrieval-grounded and extractive by default (no LLM needed). The hadith index is
shared with /search; the sharh index is provided here (prebuilt sharh_index.db or
built in memory from processed/sharh JSONL).
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, Query

from app.config import get_settings
from app.qa import answer_question
from app.qa.answer import Synthesizer
from app.routers.search import get_index
from app.search import HadithIndex, SharhIndex

router = APIRouter(tags=["ask"])


def resolve_engine(requested: str, settings) -> str:
    """Map a requested engine to a concrete one: ``"auto"`` → the configured default."""
    return settings.llm_default_engine if requested == "auto" else requested


def build_synthesizer(engine: str, settings) -> Synthesizer | None:
    """The synthesizer for ``engine`` (``"off"`` → None → an extractive answer)."""
    from app.qa.llm import synthesizer_for_engine  # lazy: optional 'llm' extra

    return synthesizer_for_engine(engine, settings)


@lru_cache(maxsize=1)
def get_sharh_index() -> SharhIndex:
    settings = get_settings()
    if settings.sharh_index_path.exists():
        return SharhIndex(settings.sharh_index_path)
    sharh_dir = settings.processed_dir / "sharh"
    if sharh_dir.exists() and any(sharh_dir.glob("*.jsonl")):
        return SharhIndex.build_from_processed(sharh_dir)
    return SharhIndex()  # empty — answers still work, just without commentary


@router.get("/ask")
def ask(
    q: str = Query(..., min_length=2, description="question in Arabic"),
    k_hadith: int = Query(5, ge=1, le=20),
    k_sharh: int = Query(3, ge=0, le=10),
    engine: str = Query(
        "auto",
        pattern="^(auto|local|remote|off)$",
        description="which LLM brain answers: auto (config default) | local (Ollama) "
        "| remote (cloud, e.g. Claude) | off (extractive, no LLM)",
    ),
    hadith_index: HadithIndex = Depends(get_index),
    sharh_index: SharhIndex = Depends(get_sharh_index),
) -> dict:
    settings = get_settings()
    resolved = resolve_engine(engine, settings)
    out = answer_question(
        q, hadith_index, sharh_index,
        k_hadith=k_hadith, k_sharh=k_sharh,
        synthesize=build_synthesizer(resolved, settings),
    )
    out["engine"] = resolved
    return out

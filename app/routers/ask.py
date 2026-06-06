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
from app.routers.search import get_embedder, get_index, get_vectors
from app.search import HadithIndex, HybridSearcher, SharhIndex, VectorIndex
from app.search.embeddings import Embedder

router = APIRouter(tags=["ask"])


def resolve_engine(requested: str, settings) -> str:
    """Map a requested engine to a concrete one: ``"auto"`` → the configured default."""
    return settings.llm_default_engine if requested == "auto" else requested


def build_synthesizer(engine: str, settings, model: str | None = None) -> Synthesizer | None:
    """The synthesizer for ``engine`` (``"off"`` → None → an extractive answer).
    ``model`` optionally overrides the engine's model with any litellm id."""
    from app.qa.llm import synthesizer_for_engine  # lazy: optional 'llm' extra

    return synthesizer_for_engine(engine, settings, model)


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
        "| remote (cloud, any provider) | off (extractive, no LLM)",
    ),
    model: str | None = Query(
        None,
        description="optional litellm model id to use (any provider): "
        "anthropic/claude-sonnet-4-6 · openai/gpt-4o · gemini/gemini-2.0-flash · ollama/llama3 …",
    ),
    hadith_index: HadithIndex = Depends(get_index),
    sharh_index: SharhIndex = Depends(get_sharh_index),
    vectors: VectorIndex | None = Depends(get_vectors),
    embedder: Embedder | None = Depends(get_embedder),
) -> dict:
    settings = get_settings()
    resolved = resolve_engine(engine, settings)
    # Retrieve with semantic+lexical hybrid when the vector index is available; this
    # degrades to pure lexical when it isn't, so /ask works before the corpus is embedded.
    retriever = HybridSearcher(hadith_index, vectors, embedder)
    kw = dict(k_hadith=k_hadith, k_sharh=k_sharh)
    try:
        out = answer_question(
            q, retriever, sharh_index,
            synthesize=build_synthesizer(resolved, settings, model), **kw,
        )
    except Exception:
        # The LLM brain is unreachable (Ollama not running, missing API key, or the
        # optional 'llm' extra not installed). Don't fail the request — fall back to
        # the cited extractive answer and tell the user what happened.
        out = answer_question(q, retriever, sharh_index, synthesize=None, **kw)
        out["warning"] = (
            "تعذّر تشغيل محرّك الذكاء الاصطناعي — تأكّد من تشغيل Ollama للمحرّك المحلي، "
            "أو من ضبط مفتاح API للمحرّك السحابي. وهذه إجابة استخراجية من المصادر."
        )
        resolved = "off"
    out["engine"] = resolved
    if resolved == "local":
        out["model"] = model or settings.llm_local_model
    elif resolved == "remote":
        out["model"] = model or settings.llm_remote_model
    return out

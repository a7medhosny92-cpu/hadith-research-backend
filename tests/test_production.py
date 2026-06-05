"""Tests for the production hooks that run without heavy deps: the embedding
baseline, the grounded LLM prompt, and the /ask synthesizer wiring."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.qa.llm import SYSTEM_PROMPT, build_prompt
from app.routers.ask import build_synthesizer
from app.search.embeddings import HashingEmbedder, cosine, load_embedder


def test_hashing_embedder_is_normalised_and_meaningful():
    emb = HashingEmbedder(dim=128)
    near_a, near_b, far = emb.embed([
        "الصلاة واجبة على كل مسلم",
        "الصلاة فرض على كل مسلم",
        "زكاة الإبل والغنم",
    ])
    assert len(near_a) == 128
    assert cosine(near_a, near_a) == pytest.approx(1.0, abs=1e-6)   # L2-normalised
    assert cosine(near_a, near_b) > cosine(near_a, far)            # shared words rank higher


def test_load_embedder_falls_back_without_torch():
    emb = load_embedder(get_settings())  # no torch here → HashingEmbedder
    vecs = emb.embed(["نص تجريبي"])
    assert len(vecs) == 1 and len(vecs[0]) == emb.dim


def test_build_prompt_is_grounded_and_cited():
    hadith = [{"collection": "صحيح البخاري", "number": 1,
               "matn": "إنما الأعمال بالنيات", "grade": "صحيح"}]
    sharh = [{"sharh": "فتح الباري", "hadith_number": 1, "excerpt": "النية محلها القلب"}]
    prompt = build_prompt("ما أهمية النية؟", hadith, sharh)
    assert "صحيح البخاري رقم 1" in prompt        # citation present
    assert "إنما الأعمال بالنيات" in prompt       # the matn is in context
    assert "فتح الباري" in prompt                 # commentary is in context
    assert "ما أهمية النية؟" in prompt            # the question is asked
    assert "المصادر المعطاة فقط" in SYSTEM_PROMPT  # the prompt forbids outside knowledge


def test_default_engine_is_off_extractive():
    # the engine switch ships as "off" → /ask stays extractive (no LLM)
    s = get_settings()
    assert s.llm_default_engine == "off"
    assert build_synthesizer("off", s) is None


def test_models_match_storage_schema():
    pytest.importorskip("pgvector")  # production-only dependency
    from app.models.tables import Hadith, SharhPassage

    assert Hadith.__tablename__ == "hadith"
    assert SharhPassage.__tablename__ == "sharh_passage"

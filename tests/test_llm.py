"""Tests for the LLM engine wiring (engine switch, API-key export, prompt)."""

from __future__ import annotations

import os

from app.config import Settings
from app.qa.llm import _load_dotenv_provider_keys, build_prompt, synthesizer_for_engine


def test_off_engine_is_extractive():
    assert synthesizer_for_engine("off", Settings()) is None


def test_remote_engine_exports_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = Settings(anthropic_api_key="sk-ant-test", llm_remote_model="anthropic/claude-sonnet-4-6")
    syn = synthesizer_for_engine("remote", settings)
    assert syn is not None                                   # a synthesizer is built
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-test"  # key reaches litellm's env


def test_existing_env_key_is_not_overwritten(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    synthesizer_for_engine("remote", Settings(anthropic_api_key="sk-from-dotenv"))
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-from-env"  # the environment wins


def test_local_engine_does_not_need_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    syn = synthesizer_for_engine("local", Settings())
    assert syn is not None and "ANTHROPIC_API_KEY" not in os.environ


def test_model_override_any_provider():
    # Any litellm model id can be chosen per engine; a synthesizer is built for each.
    assert synthesizer_for_engine("remote", Settings(openai_api_key="x"), model="openai/gpt-4o")
    assert synthesizer_for_engine("local", Settings(), model="ollama/llama3")
    assert synthesizer_for_engine("remote", Settings(), model="gemini/gemini-2.0-flash")


def test_dotenv_exports_any_provider_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        'GEMINI_API_KEY="g-123"\nGROQ_API_KEY=gr-456\nNOT_A_KEY=secret\n', encoding="utf-8"
    )
    _load_dotenv_provider_keys(str(env))
    assert os.environ["GEMINI_API_KEY"] == "g-123"   # quotes stripped
    assert os.environ["GROQ_API_KEY"] == "gr-456"
    assert os.environ.get("NOT_A_KEY") is None        # only *_API_KEY/_BASE/_VERSION


def test_prompt_carries_sources_and_question():
    prompt = build_prompt(
        "ما حكم هذا الحديث؟",
        [{"collection": "صحيح البخاري", "number": 1, "matn": "إنما الأعمال بالنيات", "grade": "صحيح"}],
        [{"sharh": "فتح الباري", "hadith_number": 1, "text": "شرح الحديث"}],
    )
    assert "صحيح البخاري" in prompt and "فتح الباري" in prompt and "السؤال" in prompt

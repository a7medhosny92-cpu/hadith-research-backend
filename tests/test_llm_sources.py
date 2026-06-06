"""The LLM prompt builder must tolerate null titles/bodies (audit API-1)."""

from __future__ import annotations

from app.qa.llm import build_prompt, litellm_synthesizer


def test_sources_block_tolerates_null_sharh_title_and_matn():
    # a commentary with no title and a hadith with no matn must not crash build_prompt
    prompt = build_prompt(
        "ما حكمه؟",
        [{"collection": "البخاري", "number": 1, "matn": None, "grade": "صحيح"}],
        [{"sharh": None, "hadith_number": 5, "text": "كلام الشارح"}],
    )
    assert "كلام الشارح" in prompt and "البخاري رقم 1" in prompt


def test_synthesizer_coalesces_none_content(monkeypatch):
    # a provider returning content=None (refusal/tool turn) yields "" rather than crashing
    import app.qa.llm as llm

    class _Resp(dict):
        pass

    def fake_completion(**kwargs):
        return {"choices": [{"message": {"content": None}}]}

    monkeypatch.setitem(__import__("sys").modules, "litellm",
                        type("M", (), {"completion": staticmethod(fake_completion)}))
    out = litellm_synthesizer("ollama/x")("q", [], [])
    assert out == ""

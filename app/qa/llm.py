"""Optional LLM synthesis for /ask — grounded, provider-agnostic via litellm.

Off by default. When an engine other than ``off`` is selected (``local`` Ollama or
``remote`` cloud), /ask hands the retrieved hadith and شرح to that model to write a
prose Arabic answer. The prompt is strict: use only the supplied sources, cite the
collection and number, and say "لا أعلم" when they do not answer — so the output
stays verifiable against what was actually retrieved. The sources are returned
alongside the answer regardless.
"""

from __future__ import annotations

from app.qa.answer import Synthesizer

SYSTEM_PROMPT = (
    "أنت مساعد بحثي متخصص في الحديث النبوي. أجب اعتمادًا على المصادر المعطاة فقط، "
    "ولا تستشهد بشيء خارجها. اذكر العزو (اسم الكتاب ورقم الحديث) لكل ما تنقله، "
    "وانقل حكم الحديث كما ورد. وإن كانت المصادر لا تجيب عن السؤال فقل: لا أعلم."
)


def _sources_block(hadith: list[dict], sharh: list[dict]) -> str:
    lines: list[str] = ["# الأحاديث"]
    for h in hadith:
        cite = f"{h.get('collection')} رقم {h.get('number')}"
        grade = f" [الحكم: {h['grade']}]" if h.get("grade") else ""
        lines.append(f"- ({cite}){grade}: {h.get('matn')}")
    if sharh:
        lines.append("\n# الشروح")
        for s in sharh:
            ref = s.get("sharh")
            if s.get("hadith_number"):
                ref += f" (عند الحديث {s['hadith_number']})"
            lines.append(f"- ({ref}): {s.get('excerpt')}")
    return "\n".join(lines)


def build_prompt(question: str, hadith: list[dict], sharh: list[dict]) -> str:
    """The user message: the retrieved sources followed by the question."""
    return f"{_sources_block(hadith, sharh)}\n\n# السؤال\n{question}\n\n# الجواب\n"


def litellm_synthesizer(
    model: str, *, api_base: str | None = None, temperature: float = 0.2
) -> Synthesizer:
    """A Synthesizer that calls ``model`` via litellm (lazy import).

    ``api_base`` is only meaningful for a local server (Ollama). For a cloud model
    it must be ``None`` — otherwise litellm would send the request to localhost.
    """

    def synthesize(question: str, hadith: list[dict], sharh: list[dict]) -> str:
        import litellm  # lazy: optional 'llm' extra

        response = litellm.completion(
            model=model,
            api_base=api_base,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(question, hadith, sharh)},
            ],
            temperature=temperature,
        )
        return response["choices"][0]["message"]["content"].strip()

    return synthesize


def synthesizer_for_engine(engine: str, settings) -> Synthesizer | None:
    """Build the synthesizer for an LLM engine; ``"off"`` → ``None`` (extractive).

    ``"local"`` routes to the Ollama model + ``ollama_api_base``; ``"remote"`` routes
    to the cloud model with no ``api_base``. Each reads its model id from settings,
    so the engine is a pure config switch (no code changes to swap brains).
    """
    if engine == "off":
        return None
    if engine == "local":
        return litellm_synthesizer(
            settings.llm_local_model,
            api_base=settings.ollama_api_base,
            temperature=settings.llm_temperature,
        )
    if engine == "remote":
        return litellm_synthesizer(
            settings.llm_remote_model,
            api_base=None,
            temperature=settings.llm_temperature,
        )
    raise ValueError(f"unknown LLM engine: {engine!r}")

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
            lines.append(f"- ({ref}): {s.get('text') or s.get('excerpt')}")
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


def _load_dotenv_provider_keys(path: str = ".env") -> None:
    """Make *any* provider credential set in .env visible to litellm (which reads
    os.environ): any VAR ending in _API_KEY / _API_BASE / _API_VERSION (Anthropic,
    OpenAI, Gemini, Mistral, Groq, Cohere, DeepSeek, …). Pre-set env vars win."""
    import os
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return
    suffixes = ("_API_KEY", "_API_BASE", "_API_VERSION")
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value and key.endswith(suffixes) and not os.environ.get(key):
            os.environ[key] = value


def _export_api_keys(settings) -> None:
    """Make cloud keys visible to litellm. Typed settings keys first, then any other
    provider key found in .env — so the remote engine works with *any* litellm
    provider, not just Anthropic. A pre-existing environment variable always wins."""
    import os

    for var, value in (
        ("ANTHROPIC_API_KEY", getattr(settings, "anthropic_api_key", None)),
        ("OPENAI_API_KEY", getattr(settings, "openai_api_key", None)),
    ):
        if value and not os.environ.get(var):
            os.environ[var] = value
    _load_dotenv_provider_keys()


def synthesizer_for_engine(engine: str, settings, model: str | None = None) -> Synthesizer | None:
    """Build the synthesizer for an LLM engine; ``"off"`` → ``None`` (extractive).

    ``model`` (optional) overrides the engine's configured model with any litellm id
    — ``anthropic/claude-sonnet-4-6``, ``openai/gpt-4o``, ``gemini/gemini-2.0-flash``,
    ``ollama/llama3``, ``groq/…`` — so any provider/model can be chosen per request.
    ``"local"`` routes to Ollama + ``ollama_api_base``; ``"remote"`` routes to the
    cloud model with no ``api_base`` (and exports the provider key so litellm can auth).
    """
    if engine == "off":
        return None
    if engine == "local":
        return litellm_synthesizer(
            model or settings.llm_local_model,
            api_base=settings.ollama_api_base,
            temperature=settings.llm_temperature,
        )
    if engine == "remote":
        _export_api_keys(settings)
        return litellm_synthesizer(
            model or settings.llm_remote_model,
            api_base=None,
            temperature=settings.llm_temperature,
        )
    raise ValueError(f"unknown LLM engine: {engine!r}")

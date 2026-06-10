"""Application settings, loaded from environment / .env (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"

    # ── turath.io ───────────────────────────────────────────────────────────
    turath_api_base: str = "https://api.turath.io"
    turath_files_base: str = "https://files.turath.io"
    turath_rate_per_sec: float = 4.0
    turath_max_retries: int = 4
    turath_timeout: float = 30.0
    turath_user_agent: str = (
        "HadithResearchBot/0.1 (+https://github.com/a7medhosny92-cpu/hadith-research-backend)"
    )

    # ── Storage ─────────────────────────────────────────────────────────────
    data_dir: Path = Path("data")

    # ── Database ────────────────────────────────────────────────────────────
    database_url: str = "postgresql+psycopg://hadith:hadith@localhost:5432/hadith"

    # ── Embeddings / LLM ────────────────────────────────────────────────────
    embedding_model: str = "Omartificial-Intelligence-Space/Arabic-Triplet-Matryoshka-V2"
    embedding_dim: int = 768

    # The /ask LLM "brain" is a switch with three positions, selectable per request
    # (``/ask?engine=local|remote|off``) or defaulted here:
    #   off    → cited, extractive answer; no LLM, runs anywhere (the default)
    #   local  → Ollama on this machine (private, free, offline)
    #   remote → a cloud model (Claude, …) — fast/strong even on a laptop without GPU
    # Switching is config-only: LiteLLM talks to all of them, no code changes.
    llm_default_engine: Literal["off", "local", "remote"] = "off"
    llm_local_model: str = "ollama/qwen2.5:7b"             # the local brain (Ollama)
    llm_remote_model: str = "anthropic/claude-sonnet-4-6"  # the remote brain (cloud)
    # The build-time *extraction* model (scripts.build_rijal_llm, run by update.bat) — kept
    # separate from the /ask «brain» so corpus extraction always uses a capable, faithful model
    # no matter what local/remote are set to. Default: Ollama Cloud's gemma4:31b-cloud — free,
    # fast (direct answer, no chain-of-thought) and reached through the local Ollama daemon, so
    # no GPU/RAM is needed. Override in .env to use a different extractor.
    llm_extract_model: str = "ollama/gemma4:31b-cloud"
    llm_temperature: float = 0.2
    llm_timeout: float = 60.0                               # seconds per LLM call (no hang)
    ollama_api_base: str = "http://localhost:11434"        # local Ollama server
    # Cloud API keys, read from .env. We export them to the process environment so
    # litellm (which reads os.environ) can authenticate — otherwise a key set only in
    # .env never reaches the remote engine.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # ── Rijal (narrator gradings) ────────────────────────────────────────────
    # /verify-isnad always uses the bundled curated seed; set this to a full رجال
    # JSONL to grade more narrators. If unset, the app auto-discovers the one built
    # by `scripts.build_rijal` at data/rijal.jsonl (see the rijal_file property).
    rijal_path: str | None = None

    # ── Hadith corpus scope ─────────────────────────────────────────────────
    # turath.io category ids that make up the hadith sciences. Confirmed against
    # the live catalog (files.turath.io/data-v3.json):
    #   6  كتب السنة            (hadith collections)
    #   7  شروح الحديث          (commentaries / shuruh)
    #   8  التخريج والأطراف     (takhrij & atraf)
    #   9  العلل والسؤلات       (hidden defects / ʿilal)
    #   10 علوم الحديث          (methodology / mustalah)
    #   26 التراجم والطبقات     (narrator biographies / rijal)
    hadith_category_ids: tuple[int, ...] = Field(default=(6, 7, 8, 9, 10, 26))

    @property
    def raw_dir(self) -> Path:
        """Directory holding the downloaded raw turath corpus."""
        return self.data_dir / "raw" / "turath"

    @property
    def processed_dir(self) -> Path:
        """Directory holding parsed hadith/sharh JSONL (output of scripts.parse)."""
        return self.data_dir / "processed"

    @property
    def index_path(self) -> Path:
        """sqlite FTS index of hadith built by scripts.index (dev search backend)."""
        return self.data_dir / "index.db"

    @property
    def sharh_index_path(self) -> Path:
        """sqlite FTS index of commentary passages (dev backend for /ask)."""
        return self.data_dir / "sharh_index.db"

    @property
    def vector_index_path(self) -> Path:
        """sqlite store of dense hadith vectors for semantic search (dev backend)."""
        return self.data_dir / "vectors.db"

    @property
    def embed_cache_path(self) -> Path:
        """Persistent text-hash → vector cache, so re-embedding only touches changed
        matns (re-indexing assigns fresh row ids, so we key by content, not id)."""
        return self.data_dir / "embed_cache.db"

    @property
    def narrator_graph_path(self) -> Path:
        """sqlite narrator network (شيوخ/تلاميذ links) built from the corpus chains."""
        return self.data_dir / "narrators.db"

    @property
    def notebook_path(self) -> Path:
        """The study notebook (saved items + notes) — persistent, never rebuilt."""
        return self.data_dir / "notebook.db"

    @property
    def rijal_file(self) -> str | None:
        """The full رجال JSONL to load on top of the seed: an explicit ``rijal_path``
        wins, else the one built by ``scripts.build_rijal`` (data/rijal.jsonl) if present."""
        if self.rijal_path:
            return self.rijal_path
        built = self.data_dir / "rijal.jsonl"
        return str(built) if built.exists() else None


@lru_cache
def get_settings() -> Settings:
    return Settings()

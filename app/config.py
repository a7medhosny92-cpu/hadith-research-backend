"""Application settings, loaded from environment / .env (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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
        "HadithResearchBot/0.1 (+https://github.com/a7medhosny92-cpu/review-backend)"
    )

    # ── Storage ─────────────────────────────────────────────────────────────
    data_dir: Path = Path("data")

    # ── Database ────────────────────────────────────────────────────────────
    database_url: str = "postgresql+psycopg://hadith:hadith@localhost:5432/hadith"

    # ── Embeddings / LLM ────────────────────────────────────────────────────
    embedding_model: str = "Omartificial-Intelligence-Space/Arabic-Triplet-Matryoshka-V2"
    llm_model: str = "ollama/qwen2.5:7b"
    ollama_api_base: str = "http://localhost:11434"

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
        """sqlite FTS index built by scripts.index (dev lexical search backend)."""
        return self.data_dir / "index.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()

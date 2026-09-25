"""Configuração central da aplicação (12-factor: tudo vem de variáveis de ambiente)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # OpenAI
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    llm_temperature: float = Field(default=0.4, alias="LLM_TEMPERATURE")
    use_fake_llm: bool = Field(default=False, alias="USE_FAKE_LLM")

    # Banco
    database_url: str = Field(default="sqlite:///./data/laria.db", alias="DATABASE_URL")

    # RAG
    rag_index_dir: str = Field(default="./data/index", alias="RAG_INDEX_DIR")
    rag_top_k: int = Field(default=4, alias="RAG_TOP_K")

    # Follow-up
    followup_enabled: bool = Field(default=True, alias="FOLLOWUP_ENABLED")
    followup_after_hours: int = Field(default=24, alias="FOLLOWUP_AFTER_HOURS")
    followup_max_attempts: int = Field(default=3, alias="FOLLOWUP_MAX_ATTEMPTS")
    followup_scan_interval_minutes: int = Field(
        default=30, alias="FOLLOWUP_SCAN_INTERVAL_MINUTES"
    )

    # App
    app_env: str = Field(default="dev", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_base_url: str = Field(default="http://localhost:8000", alias="API_BASE_URL")

    # WhatsApp (opcional)
    whatsapp_verify_token: str = Field(default="", alias="WHATSAPP_VERIFY_TOKEN")

    # Telegram (opcional / diferencial — adapter de canal real)
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")

    @property
    def llm_enabled(self) -> bool:
        """Há credencial real da OpenAI configurada?"""
        key = self.openai_api_key.strip()
        return bool(key) and key.startswith("sk-") and "xxxx" not in key

    @property
    def fake_mode(self) -> bool:
        """Roda sem chamar a OpenAI (demo offline / testes / CI)."""
        return self.use_fake_llm or not self.llm_enabled

    @property
    def index_dir(self) -> Path:
        p = (ROOT_DIR / self.rag_index_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def sqlite_path(self) -> Path | None:
        if self.database_url.startswith("sqlite"):
            raw = self.database_url.split("///")[-1]
            return (ROOT_DIR / raw).resolve()
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

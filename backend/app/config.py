"""Application configuration.

Every setting is read from the environment (or a ``.env`` file) - nothing that
looks like a secret is ever hard-coded. See ``backend/.env.example`` for the
full list with explanations.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> <repo root>
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent
PROJECT_ROOT: Path = BACKEND_DIR.parent

# The `ml` package lives at the repository root and is shared between the
# training scripts and this service. Both must import the *same* preprocessing
# module, otherwise train/serve skew silently degrades predictions.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---------------------------------------------------------
    APP_NAME: str = "Finora"
    APP_DESCRIPTION: str = "AI-powered personal finance platform"
    APP_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # --- Database ------------------------------------------------------------
    # Production/Docker uses PostgreSQL. When DATABASE_URL is unset we fall back
    # to a local SQLite file so the project can be run without installing
    # PostgreSQL; this is a development convenience only and is logged loudly.
    DATABASE_URL: str = ""
    SQL_ECHO: bool = False

    # --- Security ------------------------------------------------------------
    JWT_SECRET: str = "dev-only-insecure-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Uploads / OCR -------------------------------------------------------
    UPLOAD_DIR: str = str(BACKEND_DIR / "uploads")
    MAX_UPLOAD_MB: int = 8
    ALLOWED_UPLOAD_TYPES: str = "image/png,image/jpeg,image/jpg,image/webp,image/bmp,image/tiff"
    TESSERACT_CMD: str = ""
    OCR_LANGUAGES: str = "eng"

    # --- AI provider ---------------------------------------------------------
    # The assistant works without these: when no key is configured the backend
    # falls back to a deterministic, template-based explainer that uses the same
    # verified financial facts. See app/ai/provider.py.
    AI_PROVIDER: str = "anthropic"
    AI_API_KEY: str = ""
    AI_MODEL: str = "claude-sonnet-5"
    AI_BASE_URL: str = ""
    AI_MAX_TOKENS: int = 900
    AI_TIMEOUT_SECONDS: int = 30

    # --- Demo / seed ---------------------------------------------------------
    DEMO_EMAIL: str = "demo@finora.app"
    DEMO_PASSWORD: str = "FinoraDemo123!"
    DEMO_NAME: str = "Divyanshi"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _normalise_database_url(cls, value: str | None) -> str:
        if not value:
            return ""
        value = str(value).strip()
        # SQLAlchemy 2.x + psycopg 3 driver naming.
        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @property
    def effective_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"sqlite:///{(BACKEND_DIR / 'finora.db').as_posix()}"

    @property
    def is_sqlite(self) -> bool:
        return self.effective_database_url.startswith("sqlite")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_upload_types(self) -> set[str]:
        return {t.strip().lower() for t in self.ALLOWED_UPLOAD_TYPES.split(",") if t.strip()}

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    @property
    def upload_path(self) -> Path:
        path = Path(self.UPLOAD_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def ai_configured(self) -> bool:
        return bool(self.AI_API_KEY.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

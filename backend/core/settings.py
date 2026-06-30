"""
core/settings.py

Centralized application configuration for PartnerOS.

Uses Pydantic v2's `pydantic-settings` package (the successor to
`pydantic.BaseSettings`, which was moved out of core Pydantic in v2) to load
configuration from environment variables and/or a `.env` file via
`python-dotenv` integration.

Design notes:
- A single `Settings` class is the source of truth for all configuration.
- `get_settings()` is cached with `lru_cache` so the environment is parsed
  exactly once per process, and is exposed as a FastAPI dependency so
  consumers never instantiate `Settings` directly (dependency injection).
- Values have sane defaults for local development but are fully
  overridable via environment variables, keeping the app 12-factor
  compliant.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory of the backend package (.../backend)
BASE_DIR: Path = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    Application-wide configuration.

    All fields can be overridden via environment variables (case-insensitive)
    or a `.env` file located at the project root. See `model_config` below.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- General application metadata -----------------------------------
    APP_NAME: str = Field(default="PartnerOS", description="Human-readable application name.")
    APP_VERSION: str = Field(default="0.1.0", description="Semantic version of the backend.")
    ENVIRONMENT: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Deployment environment; controls logging verbosity and debug behavior.",
    )
    DEBUG: bool = Field(default=True, description="Enable debug mode (verbose errors, auto-reload, etc.).")

    # --- API server -------------------------------------------------------
    API_HOST: str = Field(default="127.0.0.1", description="Host interface for the API server.")
    API_PORT: int = Field(default=8000, ge=1, le=65535, description="Port for the API server.")
    API_V1_PREFIX: str = Field(default="/api/v1", description="URL prefix for version 1 of the API.")

    # --- Database -----------------------------------------------------------
    # Defaults to a local SQLite database file using the async `aiosqlite`
    # driver. The DSN is fully overridable so the same codebase can later
    # point at PostgreSQL, MySQL, etc. without code changes.
    DATABASE_URL: str = Field(
        default=f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'partneros.db'}",
        description="SQLAlchemy async database connection string.",
    )
    DATABASE_ECHO: bool = Field(default=False, description="Echo raw SQL statements (debugging only).")
    DATABASE_POOL_SIZE: int = Field(default=5, ge=1, description="Connection pool size (ignored for SQLite).")
    DATABASE_MAX_OVERFLOW: int = Field(default=10, ge=0, description="Max overflow connections beyond pool size.")

    # --- Logging ------------------------------------------------------------
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Minimum severity level captured by the logger."
    )
    LOG_DIR: Path = Field(default=BASE_DIR / "logs", description="Directory where log files are written.")
    LOG_FILE_NAME: str = Field(default="partneros.log", description="Base name of the rotating log file.")
    LOG_MAX_BYTES: int = Field(default=5 * 1024 * 1024, description="Max size (bytes) before a log file rotates.")
    LOG_BACKUP_COUNT: int = Field(default=5, description="Number of rotated log files to retain.")

    @field_validator("LOG_DIR", mode="before")
    @classmethod
    def _ensure_log_dir_is_path(cls, value: str | Path) -> Path:
        """Normalize LOG_DIR to a Path instance regardless of input type."""
        return Path(value)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached, process-wide `Settings` instance.

    Wrapped in `lru_cache` so environment parsing happens once. Exposed as a
    callable (rather than a module-level singleton) so it can be used as a
    FastAPI dependency, e.g.:

        @router.get("/info")
        def info(settings: Settings = Depends(get_settings)) -> dict:
            return {"app_name": settings.APP_NAME}

    This keeps configuration access dependency-injected and easily
    overridable in tests via `app.dependency_overrides[get_settings]`.
    """
    return Settings()

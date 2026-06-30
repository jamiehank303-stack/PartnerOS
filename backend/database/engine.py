"""
database/engine.py

SQLAlchemy async engine construction for PartnerOS.

Responsible solely for building and caching the `AsyncEngine`. Session
management lives in `database/session.py`, and ORM model definitions live in
`database/models.py` -- keeping each module to a single responsibility.

The engine is built from `Settings.DATABASE_URL`, which defaults to a local
SQLite file (via the `aiosqlite` async driver) but can be pointed at any
SQLAlchemy-supported async DSN (e.g. PostgreSQL via `asyncpg`) purely
through configuration, with no code changes required.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from core.logger import get_logger
from core.settings import Settings, get_settings

logger = get_logger(__name__)


def _is_sqlite(database_url: str) -> bool:
    """Return True if the given DSN targets SQLite."""
    return database_url.startswith("sqlite")


def _is_in_memory_sqlite(database_url: str) -> bool:
    """Return True if the given DSN targets an in-memory SQLite database."""
    return _is_sqlite(database_url) and ":memory:" in database_url


def build_engine(settings: Settings) -> AsyncEngine:
    """
    Construct a new `AsyncEngine` from the given settings.

    Args:
        settings: Application settings providing the database DSN and
            connection-pool tuning parameters.

    Returns:
        A configured `AsyncEngine` instance. Pooling arguments are only
        applied for non-SQLite backends, since SQLite (especially the
        on-disk, file-based mode used by default) does not benefit from --
        and in some configurations cannot use -- SQLAlchemy's standard
        connection pool sizing options.

    Notes:
        This function does not cache its result; use `get_engine()` for the
        cached, dependency-injectable, process-wide engine. A separate,
        uncached factory function is kept available so tests can construct
        isolated engines (e.g. pointed at an in-memory SQLite database)
        without disturbing the cached singleton.
    """
    engine_kwargs: dict[str, object] = {
        "echo": settings.DATABASE_ECHO,
        "future": True,
    }

    if _is_sqlite(settings.DATABASE_URL):
        # SQLite does not support the standard pool-size/overflow knobs.
        # For in-memory SQLite, a StaticPool is required so that all
        # connections share the same in-memory database instead of each
        # getting its own (which would otherwise appear empty).
        if _is_in_memory_sqlite(settings.DATABASE_URL):
            engine_kwargs["poolclass"] = StaticPool
            engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Non-SQLite backends (e.g. PostgreSQL, MySQL): apply standard
        # connection-pool sizing from settings.
        engine_kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
        engine_kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW

    logger.info("Building database engine | dsn=%s", settings.DATABASE_URL)
    return create_async_engine(settings.DATABASE_URL, **engine_kwargs)


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """
    Return a cached, process-wide `AsyncEngine`.

    Exposed as a callable (rather than a bare module-level instance) so it
    can be used as a FastAPI dependency or easily swapped out in tests via
    `lru_cache`-aware monkeypatching, in keeping with the project's
    dependency-injection requirement.
    """
    return build_engine(get_settings())

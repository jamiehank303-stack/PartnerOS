"""
database/session.py

Async session management for PartnerOS.

Provides:
  - `get_session_factory()`: a cached `async_sessionmaker` bound to the
    process-wide engine.
  - `get_db_session()`: a FastAPI-compatible async generator dependency
    that yields a single `AsyncSession` per request and guarantees it is
    closed afterward, with automatic rollback on error.

Keeping session lifecycle management here (separate from engine
construction and ORM model definitions) follows the Single Responsibility
Principle and allows route handlers / services to depend only on an
`AsyncSession`, never on the engine or session factory directly --
dependency injection via FastAPI's `Depends`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from core.logger import get_logger
from database.engine import get_engine

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Return a cached `async_sessionmaker` bound to the process-wide engine.

    `expire_on_commit=False` is set so that ORM instances returned from a
    session remain usable (e.g. for serialization into a Pydantic schema)
    after the session has committed, which is the common pattern in
    request/response-cycle web applications.
    """
    engine: AsyncEngine = get_engine()
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a request-scoped `AsyncSession`.

    Usage:

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db_session)) -> list[Item]:
            ...

    Behavior:
        - Opens a new session for the duration of the request.
        - Rolls back the transaction if an exception propagates out of the
          request handler, preventing partially-applied changes.
        - Always closes the session afterward, returning the connection to
          the pool regardless of success or failure.

    Yields:
        An `AsyncSession` instance scoped to the current request.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            logger.exception("Session error; rolling back transaction.")
            await session.rollback()
            raise
        finally:
            await session.close()

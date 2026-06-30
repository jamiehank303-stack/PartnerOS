"""
core/exceptions.py

Custom exception hierarchy for PartnerOS.

Defining application-specific exceptions (rather than raising bare
`Exception` or relying solely on `HTTPException`) lets business logic stay
decoupled from the web framework: services and repositories can raise
domain-meaningful errors, and the API layer translates them into HTTP
responses in one centralized place. This follows the Single Responsibility
and Open/Closed principles -- new error types can be added by subclassing
`AppException` without modifying existing handling code.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from core.logger import get_logger

logger = get_logger(__name__)


class AppException(Exception):
    """
    Base class for all application-specific exceptions.

    Attributes:
        message: Human-readable error description.
        status_code: HTTP status code to return when this exception
            surfaces through the API layer.
        details: Optional structured context (e.g. validation info,
            offending field names) useful for debugging or client display.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppException):
    """Raised when a requested resource does not exist."""

    status_code = status.HTTP_404_NOT_FOUND


class ValidationError(AppException):
    """Raised when input data fails domain-level validation rules."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class ConflictError(AppException):
    """Raised when an operation conflicts with the current state (e.g. duplicate unique key)."""

    status_code = status.HTTP_409_CONFLICT


class UnauthorizedError(AppException):
    """Raised when authentication is missing or invalid."""

    status_code = status.HTTP_401_UNAUTHORIZED


class ForbiddenError(AppException):
    """Raised when an authenticated principal lacks permission for an action."""

    status_code = status.HTTP_403_FORBIDDEN


class DatabaseError(AppException):
    """Raised when a database operation fails unexpectedly."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register centralized exception handlers on the given FastAPI app.

    This is called once during application startup (from the file that
    constructs the `FastAPI` instance) so that every `AppException` raised
    anywhere in the codebase is converted into a consistent JSON error
    response, and unexpected exceptions are logged with full context
    instead of leaking a raw traceback to the client.

    Args:
        app: The FastAPI application instance to attach handlers to.
    """

    @app.exception_handler(AppException)
    async def handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
        """Convert a known `AppException` into a structured JSON response."""
        logger.warning(
            "Handled AppException | path=%s | type=%s | message=%s",
            request.url.path,
            type(exc).__name__,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": type(exc).__name__,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        """
        Catch-all for unanticipated exceptions.

        Logs the full exception with stack trace for diagnostics while
        returning a generic, non-leaky message to the client.
        """
        logger.exception(
            "Unhandled exception | path=%s | type=%s",
            request.url.path,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "An unexpected error occurred.",
                "details": {},
            },
        )

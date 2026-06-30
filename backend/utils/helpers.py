"""
utils/helpers.py

Generic, stateless utility functions for PartnerOS.

These helpers are intentionally free of any dependency on FastAPI,
SQLAlchemy, or application settings, so they can be imported anywhere in
the codebase (core, database, future service/route layers) without risking
circular imports. Anything that needs configuration or framework context
belongs in `core/` or the relevant layer instead, not here.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def utcnow() -> datetime:
    """
    Return the current time as a timezone-aware UTC `datetime`.

    Centralizing this avoids accidental use of naive `datetime.utcnow()`
    (deprecated and easy to misuse) scattered across the codebase.
    """
    return datetime.now(timezone.utc)


def generate_uuid() -> uuid.UUID:
    """Generate a new random (version 4) UUID."""
    return uuid.uuid4()


def slugify(value: str) -> str:
    """
    Convert an arbitrary string into a URL-safe, lowercase, hyphenated slug.

    Example:
        >>> slugify("Partner Account #42!")
        'partner-account-42'

    Args:
        value: The input string to slugify.

    Returns:
        A lowercase string containing only `[a-z0-9-]`, with runs of
        invalid characters collapsed into a single hyphen and leading/
        trailing hyphens stripped.
    """
    normalized = value.strip().lower()
    slug = _SLUG_INVALID_CHARS.sub("-", normalized)
    return slug.strip("-")


def safe_dict_get(data: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    """
    Retrieve a nested value from a dictionary using dot-separated key path.

    Example:
        >>> safe_dict_get({"a": {"b": {"c": 1}}}, "a.b.c")
        1
        >>> safe_dict_get({"a": {}}, "a.b.c", default="missing")
        'missing'

    Args:
        data: The dictionary to traverse.
        dotted_key: A dot-separated path of nested keys, e.g. `"a.b.c"`.
        default: Value returned if any key in the path is missing or a
            non-dict value is encountered before the path is fully resolved.

    Returns:
        The resolved value, or `default` if the path could not be resolved.
    """
    current: Any = data
    for key in dotted_key.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def truncate_string(value: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate a string to `max_length` characters, appending `suffix` if cut.

    Args:
        value: The string to truncate.
        max_length: Maximum allowed length of the returned string,
            including the suffix.
        suffix: Marker appended when truncation occurs (default `"..."`).

    Returns:
        The original string if it already fits within `max_length`,
        otherwise a truncated string ending in `suffix`.

    Raises:
        ValueError: If `max_length` is shorter than `suffix`, making
            truncation impossible to satisfy.
    """
    if max_length < len(suffix):
        raise ValueError("max_length must be at least as long as the suffix.")
    if len(value) <= max_length:
        return value
    return value[: max_length - len(suffix)] + suffix

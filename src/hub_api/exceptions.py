from __future__ import annotations

__all__ = ["BadParameterError", "NotFoundError"]


class NotFoundError(Exception):
    """Not found error."""


class BadParameterError(Exception):
    """Bad parameter error."""

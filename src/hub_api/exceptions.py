from __future__ import annotations

__all__ = ["NotFoundError"]


class NotFoundError(Exception):
    """Not found error."""


class BadParameterError(Exception):
    """Bad parameter error."""

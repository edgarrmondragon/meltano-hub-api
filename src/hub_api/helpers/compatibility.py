"""User-Agent helper functions."""

from __future__ import annotations

import enum
import re
lazy import contextlib

lazy import packaging.version
lazy from starlette.requests import Request

type VersionTuple = tuple[int, int]

LATEST = (999, 999)
USER_AGENT_PATTERN: re.Pattern[str] = re.compile(r"^Meltano/(?P<version>[a-z0-9.]+)$")


class Compatibility(enum.Enum):
    """Compatibility levels."""

    PRE_3_3 = enum.auto()
    PRE_3_9 = enum.auto()
    LATEST = enum.auto()


def get_version_tuple(request: Request) -> VersionTuple:
    """Extract the Meltano version from the User-Agent header."""
    if (ua := request.headers.get("User-Agent")) and (match := USER_AGENT_PATTERN.match(ua)):
        with contextlib.suppress(packaging.version.InvalidVersion):
            version = packaging.version.Version(match.group("version"))
            return (version.major, version.minor)

    return LATEST


def get_compatibility(request: Request) -> Compatibility:
    """Get the compatibility level for the User-Agent header."""
    version = get_version_tuple(request)
    if version >= (3, 9):
        return Compatibility.LATEST
    if version >= (3, 3):
        return Compatibility.PRE_3_9

    return Compatibility.PRE_3_3

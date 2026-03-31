"""ETag implementation.

This combination of FastAPI middleware and dependency will add an ETag header to all responses.
The ETag value is a hash of the installed package version, the database file mtime, and the
compatibility level. The incoming request's If-None-Match header is compared to the ETag value.
If they match, a 304 Not Modified response is returned. Otherwise, the response is returned as
normal.

https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/ETag
"""  # noqa: I002

import hashlib
import http
import importlib.metadata
from typing import TYPE_CHECKING, Annotated, override

from fastapi import Header, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from . import compatibility

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path


def _compute_etag(
    package_version: str,
    db_mtime: int,
    compat: compatibility.Compatibility,
) -> str:
    digest = hashlib.sha256(f"{package_version}:{db_mtime}:{compat.name}".encode()).hexdigest()[:16]
    return f'"etag-{digest}"'


ETAGS: dict[compatibility.Compatibility, str] = {}


def init(db_path: Path) -> None:
    """Initialize ETags from the database path and installed package version."""
    package_version = importlib.metadata.version("hub-api")
    db_mtime = db_path.stat().st_mtime_ns
    ETAGS.update({c: _compute_etag(package_version, db_mtime, c) for c in compatibility.Compatibility})


def _get_etag(request: Request) -> str:
    """Get the ETag value for the request."""
    return ETAGS[compatibility.get_compatibility(request)]


class ETagMiddleware(BaseHTTPMiddleware):
    """ETag middleware."""

    @override
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Add ETag header to response."""
        response = await call_next(request)
        response.headers["ETag"] = _get_etag(request)
        return response


DESCRIPTION = """\
The `If-None-Match` HTTP request header makes the request conditional.
For `GET` and `HEAD` methods, the server will return the requested resource, \
with a `200` status, only if it doesn't have an `ETag` matching the given ones.
For other methods, the request will be processed only if the eventually existing \
resource's `ETag` doesn't match any of the values listed.

https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/If-None-Match
"""


def check_etag(
    request: Request,
    if_none_match: Annotated[
        str,  # noqa: RUF013
        Header(
            description=DESCRIPTION,
            pattern=r'^"etag-[0-9a-f]{16}"$',
        ),
    ] = None,  # type: ignore[assignment] # ty:ignore[invalid-parameter-default]
) -> None:
    """Get ETag value."""
    if if_none_match == _get_etag(request):
        raise HTTPException(status_code=http.HTTPStatus.NOT_MODIFIED)

"""ETag implementation.

This combination of FastAPI middleware and dependency will add an ETag header to all responses.
The ETag value is the version of the hub-api package. The incoming request's If-None-Match
header is compared to the ETag value. If they match, a 304 Not Modified response is returned.
Otherwise, the response is returned as normal.

https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/ETag
"""  # noqa: I002

import http
import uuid
from typing import TYPE_CHECKING, Annotated, override

from fastapi import Header, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from . import compatibility

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


def get_new_etag() -> str:
    """Get a new ETag value."""
    return f'"etag-{uuid.uuid4()}"'


ETAGS: dict[compatibility.Compatibility, str] = {
    compatibility.Compatibility.PRE_3_3: get_new_etag(),
    compatibility.Compatibility.PRE_3_9: get_new_etag(),
    compatibility.Compatibility.LATEST: get_new_etag(),
}


def get_etag(request: Request) -> str:
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
        response.headers["ETag"] = get_etag(request)
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
            # pattern=r'^"W/etag-[A-Za-z0-9-]+"$',
            pattern=r'^"etag-[A-Za-z0-9-]+"$',
        ),
    ] = None,  # type: ignore[assignment] # ty:ignore[invalid-parameter-default]
) -> None:
    """Get ETag value."""
    if if_none_match == get_etag(request):
        raise HTTPException(status_code=http.HTTPStatus.NOT_MODIFIED)

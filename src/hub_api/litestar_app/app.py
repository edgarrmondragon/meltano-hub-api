from __future__ import annotations

import http

from litestar import Litestar, MediaType, Request, Response
from litestar.config.compression import CompressionConfig
from litestar.exceptions import MethodNotAllowedException
from litestar.plugins.pydantic import PydanticPlugin

from hub_api.exceptions import NotFoundError

from . import maintainers, plugins


def not_found_exception_handler(_: Request, exc: NotFoundError) -> Response:  # type: ignore[type-arg]
    """Default handler for exceptions subclassed from HTTPException."""
    return Response(
        media_type=MediaType.JSON,
        content={"details": exc.args[0]},
        status_code=http.HTTPStatus.NOT_FOUND,
    )


def method_not_allowed_exception_handler(_: Request, exc: MethodNotAllowedException) -> Response:  # type: ignore[type-arg]
    """Default handler for exceptions subclassed from HTTPException."""
    return Response(
        media_type=MediaType.JSON,
        content={"details": exc.args[0]},
        status_code=http.HTTPStatus.METHOD_NOT_ALLOWED,
        headers=exc.headers,
    )


app = Litestar(
    [
        maintainers.MaintainersController,
        plugins.PluginsController,
    ],
    compression_config=CompressionConfig(backend="gzip", minimum_size=1000),
    exception_handlers={
        NotFoundError: not_found_exception_handler,
        MethodNotAllowedException: method_not_allowed_exception_handler,
    },
    plugins=[
        PydanticPlugin(
            exclude_none=True,
            exclude_unset=True,
        ),
    ],
    debug=True,
)

"""Hub API."""

from __future__ import annotations

import http
from contextlib import asynccontextmanager
from importlib import metadata
from typing import TYPE_CHECKING

import fastapi
from fastapi import staticfiles
from fastapi.encoders import ENCODERS_BY_TYPE
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from hub_api import api, database, exception_handlers, exceptions
from hub_api.helpers import compression, etag
from hub_api.schemas import rfc9457

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

DESCRIPTION = """\
The Meltano Hub API provides access to Meltano's plugin registry. It allows you to search for plugins, \
view their details, and download the necessary files to install them.

- The API is versioned, with the current version being v1.
- The API is read-only, and no authentication is required.
"""

# TODO: Remove once https://github.com/fastapi/fastapi/discussions/16158 is resolved
ENCODERS_BY_TYPE[sentinel] = repr


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI) -> AsyncGenerator[None]:  # ruff: ignore[unused-function-argument]
    etag.init(database.get_db_path())
    yield


app: fastapi.FastAPI = fastapi.FastAPI(
    title="Meltano Hub API",
    description=DESCRIPTION,
    version=metadata.version("hub-api"),
    lifespan=lifespan,
    dependencies=[fastapi.Depends(etag.check_etag)],
    servers=[
        {
            "url": "http://localhost:8000",
            "description": "Local development server",
        },
    ],
    responses={
        http.HTTPStatus.METHOD_NOT_ALLOWED: {
            "description": "Method Not Allowed",
            "model": rfc9457.Problem,
        },
        http.HTTPStatus.UNPROCESSABLE_ENTITY: {
            "description": "Validation Error",
            "model": rfc9457.ValidationErrorProblem,
        },
        http.HTTPStatus.INTERNAL_SERVER_ERROR: {
            "description": "Internal Server Error",
            "model": rfc9457.Problem,
        },
    },
)
app.add_middleware(compression.CompressionMiddleware, minimum_size=1000)
app.add_middleware(etag.ETagMiddleware)
app.add_exception_handler(HTTPException, exception_handlers.http_exception_handler)  # type: ignore[arg-type] # ty: ignore[invalid-argument-type] # pyrefly: ignore[bad-argument-type]
app.add_exception_handler(RequestValidationError, exception_handlers.request_validation_exception_handler)  # type: ignore[arg-type] # ty: ignore[invalid-argument-type] # pyrefly: ignore[bad-argument-type]
app.add_exception_handler(exceptions.BadParameterError, exception_handlers.bad_parameter_exception_handler)  # type: ignore[arg-type] # ty: ignore[invalid-argument-type] # pyrefly: ignore[bad-argument-type]
app.add_exception_handler(exceptions.NotFoundError, exception_handlers.not_found_exception_handler)  # type: ignore[arg-type] # ty: ignore[invalid-argument-type] # pyrefly: ignore[bad-argument-type]

app.include_router(api.v1.api.router, prefix="/meltano/api/v1")
app.mount("/assets", staticfiles.StaticFiles(packages=[("hub_api.static", "assets")]), name="assets")

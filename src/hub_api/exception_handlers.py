from __future__ import annotations

import http

from fastapi.utils import is_body_allowed_for_status_code
lazy import fastapi
lazy from fastapi.encoders import jsonable_encoder
lazy from fastapi.exceptions import RequestValidationError
lazy from fastapi.responses import JSONResponse, Response
lazy from starlette.exceptions import HTTPException

lazy from hub_api import exceptions
lazy from hub_api.schemas import rfc9457


def http_exception_handler(request: fastapi.Request, exc: HTTPException) -> Response:  # ruff: ignore[unused-function-argument]
    headers = getattr(exc, "headers", None)
    if not is_body_allowed_for_status_code(exc.status_code):
        return Response(status_code=exc.status_code, headers=headers)

    return JSONResponse(
        status_code=exc.status_code,
        headers=headers,
        content=rfc9457.Problem(
            type=f"https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/{exc.status_code}",
            status=exc.status_code,
            title=exc.detail,
        ).model_dump(mode="json", fallback=jsonable_encoder),
    )


def request_validation_exception_handler(request: fastapi.Request, exc: RequestValidationError) -> JSONResponse:  # ruff: ignore[unused-function-argument]
    return JSONResponse(
        status_code=http.HTTPStatus.UNPROCESSABLE_ENTITY,
        content=rfc9457.ValidationErrorProblem(
            type="https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/422",
            status=http.HTTPStatus.UNPROCESSABLE_ENTITY,
            title="Validation error",
            errors=jsonable_encoder(exc.errors()),
        ).model_dump(mode="json", fallback=jsonable_encoder),
    )


def bad_parameter_exception_handler(request: fastapi.Request, exc: exceptions.BadParameterError) -> Response:  # ruff: ignore[unused-function-argument]
    return JSONResponse(
        status_code=http.HTTPStatus.BAD_REQUEST,
        content=rfc9457.Problem(
            type="https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/400",
            status=http.HTTPStatus.BAD_REQUEST,
            title="Bad Parameter",
            detail=exc.args[0],
        ).model_dump(mode="json", fallback=jsonable_encoder),
    )


def not_found_exception_handler(
    request: fastapi.Request,  # ruff: ignore[unused-function-argument]
    exc: exceptions.NotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=http.HTTPStatus.NOT_FOUND,
        content=rfc9457.Problem(
            type="https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/404",
            status=http.HTTPStatus.NOT_FOUND,
            title="Not Found",
            detail=exc.args[0],
        ).model_dump(mode="json", fallback=jsonable_encoder),
    )

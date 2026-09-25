"""Structured API errors: {"error": {"code", "message", "details"}}."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(
        self, message: str, *, code: str | None = None, details: Any = None, status_code: int | None = None
    ):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details


class NotFound(ApiError):
    status_code = 404
    code = "not_found"

    def __init__(self, message: str = "Not found", **kw: Any):
        super().__init__(message, **kw)


class Forbidden(ApiError):
    status_code = 403
    code = "forbidden"

    def __init__(self, message: str = "You do not have permission to perform this action", **kw: Any):
        super().__init__(message, **kw)


class Unauthorized(ApiError):
    status_code = 401
    code = "unauthenticated"

    def __init__(self, message: str = "Authentication required", **kw: Any):
        super().__init__(message, **kw)


class Conflict(ApiError):
    status_code = 409
    code = "conflict"


class Unprocessable(ApiError):
    status_code = 422
    code = "unprocessable"


class TooManyRequests(ApiError):
    status_code = 429
    code = "rate_limited"


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content=_body("validation_error", "Invalid request", details))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed", 401: "unauthenticated", 403: "forbidden"}.get(
            exc.status_code, "http_error"
        )
        return JSONResponse(status_code=exc.status_code, content=_body(code, str(exc.detail)))

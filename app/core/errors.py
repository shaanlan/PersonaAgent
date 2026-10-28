from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL = "INTERNAL"
    UNAVAILABLE = "UNAVAILABLE"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"


_DEFAULT_STATUS: dict[ErrorCode, int] = {
    ErrorCode.INVALID_ARGUMENT: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL: 500,
    ErrorCode.UNAVAILABLE: 503,
    ErrorCode.UPSTREAM_TIMEOUT: 504,
}


class AppError(Exception):
    code: ErrorCode = ErrorCode.INTERNAL
    status_code: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        elif self.code in _DEFAULT_STATUS:
            self.status_code = _DEFAULT_STATUS[self.code]
        self.details = details or {}
        self.retryable = retryable
        self.retry_after = retry_after


class ValidationError(AppError):
    def __init__(self, message: str = "invalid argument", **kwargs: Any) -> None:
        kwargs.setdefault("code", ErrorCode.INVALID_ARGUMENT)
        super().__init__(message, **kwargs)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "unauthorized", **kwargs: Any) -> None:
        kwargs.setdefault("code", ErrorCode.UNAUTHORIZED)
        super().__init__(message, **kwargs)


class ForbiddenError(AppError):
    def __init__(self, message: str = "forbidden", **kwargs: Any) -> None:
        kwargs.setdefault("code", ErrorCode.FORBIDDEN)
        super().__init__(message, **kwargs)


class NotFoundError(AppError):
    def __init__(self, message: str = "not found", **kwargs: Any) -> None:
        kwargs.setdefault("code", ErrorCode.NOT_FOUND)
        super().__init__(message, **kwargs)


class ConflictError(AppError):
    def __init__(self, message: str = "conflict", **kwargs: Any) -> None:
        kwargs.setdefault("code", ErrorCode.CONFLICT)
        super().__init__(message, **kwargs)


class PayloadTooLargeError(AppError):
    def __init__(self, message: str = "payload too large", **kwargs: Any) -> None:
        kwargs.setdefault("code", ErrorCode.PAYLOAD_TOO_LARGE)
        super().__init__(message, **kwargs)


class RateLimitedError(AppError):
    def __init__(self, message: str = "rate limited", retry_after: int = 60, **kwargs: Any) -> None:
        kwargs.setdefault("code", ErrorCode.RATE_LIMITED)
        kwargs.setdefault("retryable", True)
        super().__init__(message, retry_after=retry_after, **kwargs)


class UnavailableError(AppError):
    def __init__(self, message: str = "service unavailable", **kwargs: Any) -> None:
        kwargs.setdefault("code", ErrorCode.UNAVAILABLE)
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class UpstreamTimeoutError(AppError):
    def __init__(self, message: str = "upstream timeout", **kwargs: Any) -> None:
        kwargs.setdefault("code", ErrorCode.UPSTREAM_TIMEOUT)
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


def error_envelope(
    code: ErrorCode | str,
    message: str,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code.value if isinstance(code, ErrorCode) else code,
            "message": message,
            "request_id": request_id or request_id_var.get(),
            "details": details or {},
        }
    }


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {}
        if exc.retry_after is not None:
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(exc.code, exc.message, details=exc.details),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = {"errors": [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()[:5]]}
        return JSONResponse(
            status_code=400,
            content=error_envelope(ErrorCode.INVALID_ARGUMENT, "invalid request body", details=details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        mapping = {
            400: ErrorCode.INVALID_ARGUMENT,
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
            409: ErrorCode.CONFLICT,
            413: ErrorCode.PAYLOAD_TOO_LARGE,
            429: ErrorCode.RATE_LIMITED,
            503: ErrorCode.UNAVAILABLE,
        }
        code = mapping.get(
            exc.status_code, ErrorCode.INTERNAL if exc.status_code >= 500 else ErrorCode.INVALID_ARGUMENT
        )
        detail = exc.detail if isinstance(exc.detail, str) else "request failed"
        return JSONResponse(
            status_code=exc.status_code, content=error_envelope(code, detail), headers=getattr(exc, "headers", None)
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        from app.core.logging import get_logger

        get_logger("app").exception("unhandled_error", path=request.url.path, error=type(exc).__name__)
        return JSONResponse(status_code=500, content=error_envelope(ErrorCode.INTERNAL, "internal server error"))

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.observability.tracing import request_id_var

logger = logging.getLogger("app.errors")


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id_var.get()}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(_body(exc.code, exc.message), status_code=exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse(_body("http_error", str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) or "body" for e in exc.errors())
        return JSONResponse(_body("validation_error", f"Invalid request: {fields}"), status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.error("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(_body("internal_error", "Internal server error"), status_code=500)

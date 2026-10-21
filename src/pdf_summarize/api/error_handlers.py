"""Manejo centralizado de excepciones con formato JSON uniforme."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from pdf_summarize.domain.errors import InternalError, SummarizeError
from pdf_summarize.schemas import ErrorDetail

logger = logging.getLogger("pdf_summarize.errors")


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _error_response(status_code: int, detail: ErrorDetail) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": detail.model_dump()},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Registra los manejadores de errores de la aplicación."""

    @app.exception_handler(SummarizeError)
    async def handle_domain_error(
        request: Request, exc: SummarizeError
    ) -> JSONResponse:
        logger.warning(
            "domain_error code=%s status=%d request_id=%s",
            exc.code,
            exc.status_code,
            _request_id(request),
        )
        return _error_response(
            exc.status_code,
            ErrorDetail.from_error(exc, request_id=_request_id(request)),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception request_id=%s", _request_id(request))
        internal = InternalError(str(exc))
        return _error_response(
            internal.status_code,
            ErrorDetail.from_error(internal, request_id=_request_id(request)),
        )

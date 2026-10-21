"""Rutas de la API: sumarización, salud y métricas."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from pdf_summarize.api.metrics import render_metrics
from pdf_summarize.config import Settings
from pdf_summarize.domain.errors import (
    EmptyPdfError,
    PdfTooLargeError,
    UnsupportedMediaTypeError,
)
from pdf_summarize.schemas import (
    HealthResponse,
    ReadinessResponse,
    SummarizeResponse,
)

logger = logging.getLogger("pdf_summarize.routes")

router = APIRouter()

PDF_CONTENT_TYPES = {"application/pdf"}


def _is_pdf_content_type(request: Request) -> bool:
    content_type = (
        (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    )
    return content_type in PDF_CONTENT_TYPES


async def read_body_with_limit(request: Request, limit: int) -> bytes:
    """Rechaza temprano por Content-Length y lee el stream acotado."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = 0
        if declared > limit:
            raise PdfTooLargeError(
                f"PDF size {declared} bytes exceeds limit of {limit} bytes"
            )

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise PdfTooLargeError("PDF size exceeds limit")
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("/health/live", response_model=HealthResponse, summary="Liveness probe")
async def health_live() -> HealthResponse:
    """Indica que el proceso está vivo; no consulta dependencias."""
    return HealthResponse(status="alive")


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"model": ReadinessResponse, "description": "No está listo."}},
)
async def health_ready(request: Request) -> Response:
    """Indica si el servicio tiene la configuración esencial para trabajar."""
    settings: Settings = request.app.state.settings
    if settings.llm_configured():
        return JSONResponse(content=ReadinessResponse(status="ready").model_dump())
    return JSONResponse(
        status_code=503,
        content=ReadinessResponse(
            status="not_ready", reason="LLM_API_KEY no está configurada."
        ).model_dump(),
    )


@router.get("/metrics", summary="Métricas Prometheus")
async def metrics() -> PlainTextResponse:
    """Expone las métricas del proceso en formato Prometheus."""
    return PlainTextResponse(
        content=render_metrics().decode("utf-8"),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.post(
    "/summarize",
    response_model=SummarizeResponse,
    summary="Resume un documento PDF",
    status_code=200,
    responses={
        400: {"description": "Cuerpo vacío."},
        413: {"description": "Archivo excede el tamaño máximo."},
        415: {"description": "Content-Type no soportado."},
        422: {"description": "PDF rechazado por Validation o sin texto útil."},
        503: {"description": "Dependencia no disponible o IA no configurada."},
        502: {"description": "Fallo del proveedor de IA."},
        504: {"description": "Timeout del proveedor de IA."},
    },
)
async def summarize(request: Request) -> SummarizeResponse:
    """Coordina Validation, Extract y el modelo de IA para resumir un PDF."""
    if not _is_pdf_content_type(request):
        raise UnsupportedMediaTypeError()

    settings: Settings = request.app.state.settings
    pdf_bytes = await read_body_with_limit(request, settings.max_pdf_size_bytes)

    if not pdf_bytes:
        raise EmptyPdfError()

    request_id = request.state.request_id
    logger.info("summarize_requested size=%d request_id=%s", len(pdf_bytes), request_id)
    result = await request.app.state.container.use_case.execute(pdf_bytes, request_id)
    return SummarizeResponse(
        summary=result.summary,
        page_count=result.page_count,
        file_size_bytes=result.file_size_bytes,
        checksum=result.checksum,
        checksum_algorithm=result.checksum_algorithm,
        model=result.model,
        request_id=request_id,
    )

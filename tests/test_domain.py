"""Pruebas del dominio: excepciones, modelos y esquemas HTTP."""

import pytest

from pdf_summarize.domain import errors
from pdf_summarize.schemas import (
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    SummarizeResponse,
)


class TestDomainExceptions:
    def test_every_error_carries_code_message_and_status(self):
        cases = [
            (errors.UnsupportedMediaTypeError(), "UNSUPPORTED_MEDIA_TYPE", 415),
            (errors.EmptyPdfError(), "EMPTY_PDF", 400),
            (errors.PdfTooLargeError(), "PDF_TOO_LARGE", 413),
            (
                errors.ValidationRejectedError("INVALID_PDF", "PDF inválido."),
                "INVALID_PDF",
                422,
            ),
            (
                errors.ValidationUnavailableError("sin respuesta"),
                "VALIDATION_UNAVAILABLE",
                503,
            ),
            (errors.ExtractionFailedError("PDF inválido."), "EXTRACTION_FAILED", 422),
            (
                errors.ExtractUnavailableError("sin respuesta"),
                "EXTRACT_UNAVAILABLE",
                503,
            ),
            (errors.NoUsefulTextError(), "NO_USEFUL_TEXT", 422),
            (errors.LLMNotConfiguredError(), "LLM_NOT_CONFIGURED", 503),
            (errors.LLMAuthError("credenciales rechazadas"), "LLM_AUTH_ERROR", 502),
            (errors.LLMRateLimitError("límite de uso"), "LLM_RATE_LIMITED", 503),
            (errors.LLMTimeoutError("expiró"), "LLM_TIMEOUT", 504),
            (errors.LLMProviderError("respuesta inválida"), "LLM_PROVIDER_ERROR", 502),
            (
                errors.PersistenceUnavailableError("sin respuesta"),
                "PERSISTENCE_UNAVAILABLE",
                503,
            ),
            (
                errors.PersistenceConflictError("datos distintos"),
                "PERSISTENCE_CONFLICT",
                409,
            ),
            (
                errors.PersistenceRejectedError("payload inválido"),
                "PERSISTENCE_REJECTED",
                502,
            ),
            (errors.InternalError("inesperado"), "INTERNAL_ERROR", 500),
        ]
        for exc, code, status in cases:
            assert exc.code == code
            assert exc.message
            assert exc.status_code == status

    def test_summarize_error_is_base_class(self):
        exc = errors.EmptyPdfError()
        assert isinstance(exc, errors.SummarizeError)

    def test_validation_rejected_preserves_upstream_code(self):
        exc = errors.ValidationRejectedError("ENCRYPTED_PDF", "cifrado")
        assert exc.code == "ENCRYPTED_PDF"
        assert exc.message == "cifrado"


class TestSchemas:
    def test_summarize_response_fields(self):
        payload = {
            "summary": "Resumen breve.",
            "page_count": 3,
            "file_size_bytes": 1234,
            "checksum": "abc123",
            "checksum_algorithm": "sha256",
            "model": "meta/llama-3.1-8b-instruct",
            "request_id": "req-1",
        }
        response = SummarizeResponse.model_validate(payload)
        assert response.summary == "Resumen breve."
        assert response.page_count == 3
        assert response.model == "meta/llama-3.1-8b-instruct"

    def test_health_response(self):
        assert HealthResponse(status="alive").status == "alive"

    def test_error_detail_requires_code_and_message(self):
        detail = ErrorDetail(code="EMPTY_PDF", message="Cuerpo vacío.")
        wrapped = ErrorResponse(error=detail)
        assert wrapped.error.code == "EMPTY_PDF"

    def test_error_detail_optional_request_id(self):
        payload = {"error": {"code": "X", "message": "y", "request_id": "req-9"}}
        wrapped = ErrorResponse.model_validate(payload)
        assert wrapped.error.request_id == "req-9"

    @pytest.mark.parametrize(
        "exc",
        [
            errors.EmptyPdfError(),
            errors.ValidationUnavailableError("x"),
            errors.InternalError("x"),
        ],
    )
    def test_error_detail_from_exception_includes_request_id(self, exc):
        detail = ErrorDetail.from_error(exc, request_id="req-42")
        assert detail.code == exc.code
        assert detail.message == exc.message
        assert detail.request_id == "req-42"

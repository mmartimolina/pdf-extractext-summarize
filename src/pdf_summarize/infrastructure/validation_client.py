r"""Cliente HTTP del microservicio Validation.

Contrato verificado en ``D:\pdf-extractext-validation`` (véase
``docs/integration-contracts.md``):

- ``POST /validate`` con el PDF binario y ``Content-Type: application/pdf``.
- Éxito 200: ``{"valid", "file_size_bytes", "checksum", "checksum_algorithm"}``.
- Error: ``{"error": {"code", "message"}}`` con 400/413/415/422.
"""

import logging

import httpx

from pdf_summarize.domain.errors import (
    EmptyPdfError,
    PdfTooLargeError,
    SummarizeError,
    UnsupportedMediaTypeError,
    ValidationRejectedError,
    ValidationUnavailableError,
)
from pdf_summarize.domain.models import ValidationReport

logger = logging.getLogger("pdf_summarize.validation_client")


class ValidationClient:
    """Adaptador del puerto ``Validator`` sobre HTTP."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    async def validate(self, pdf_bytes: bytes, request_id: str) -> ValidationReport:
        """Valida el PDF y devuelve el informe con el checksum."""
        try:
            response = await self._http.post(
                f"{self._base_url}/validate",
                content=pdf_bytes,
                headers={
                    "Content-Type": "application/pdf",
                    "X-Request-ID": request_id,
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("validation_call_failed request_id=%s", request_id)
            raise ValidationUnavailableError(str(exc)) from exc

        if response.status_code != 200:
            raise self._map_error(response)

        try:
            payload = response.json()
            report = ValidationReport(
                file_size_bytes=int(payload["file_size_bytes"]),
                checksum=str(payload["checksum"]),
                checksum_algorithm=str(payload["checksum_algorithm"]),
            )
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "validation_bad_payload request_id=%s status=%d",
                request_id,
                response.status_code,
            )
            raise ValidationUnavailableError("respuesta inválida") from exc
        return report

    async def aclose(self) -> None:
        """Cierra el cliente HTTP subyacente."""
        await self._http.aclose()

    @staticmethod
    def _map_error(response: httpx.Response) -> SummarizeError:
        """Convierte la respuesta de error de Validation en una excepción."""
        try:
            payload = response.json()
            code = str(payload["error"]["code"])
            message = str(payload["error"]["message"])
        except (ValueError, KeyError, TypeError):
            raise ValidationUnavailableError(
                f"estado inesperado {response.status_code}"
            ) from None

        if response.status_code >= 500:
            raise ValidationUnavailableError(f"estado {response.status_code}")

        if code == "EMPTY_PDF":
            raise EmptyPdfError()
        if code == "PDF_TOO_LARGE":
            raise PdfTooLargeError(message)
        if code == "UNSUPPORTED_MEDIA_TYPE":
            raise UnsupportedMediaTypeError()
        raise ValidationRejectedError(code, message)

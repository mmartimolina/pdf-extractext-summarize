r"""Cliente HTTP del microservicio Extract.

Contrato verificado en ``D:\pdf-extractext-extract`` (véase
``docs/integration-contracts.md``):

- ``POST /extract`` con el PDF binario y ``Content-Type: application/pdf``.
- Éxito 200: ``{"content", "page_count"}``.
- Error: ``{"detail": str}`` con 400/413/415.
"""

import logging

import httpx

from pdf_summarize.domain.errors import (
    ExtractionFailedError,
    ExtractUnavailableError,
    PdfTooLargeError,
    UnsupportedMediaTypeError,
)
from pdf_summarize.domain.models import ExtractionResult

logger = logging.getLogger("pdf_summarize.extract_client")


class ExtractClient:
    """Adaptador del puerto ``Extractor`` sobre HTTP."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    async def extract(self, pdf_bytes: bytes, request_id: str) -> ExtractionResult:
        """Extrae el texto del PDF mediante el microservicio Extract."""
        try:
            response = await self._http.post(
                f"{self._base_url}/extract",
                content=pdf_bytes,
                headers={
                    "Content-Type": "application/pdf",
                    "X-Request-ID": request_id,
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("extract_call_failed request_id=%s", request_id)
            raise ExtractUnavailableError(str(exc)) from exc

        if response.status_code != 200:
            raise self._map_error(response)

        try:
            payload = response.json()
            return ExtractionResult(
                content=str(payload["content"]),
                page_count=int(payload["page_count"]),
            )
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "extract_bad_payload request_id=%s status=%d",
                request_id,
                response.status_code,
            )
            raise ExtractUnavailableError("respuesta inválida") from exc

    async def aclose(self) -> None:
        """Cierra el cliente HTTP subyacente."""
        await self._http.aclose()

    @staticmethod
    def _map_error(response: httpx.Response) -> Exception:
        """Convierte la respuesta de error de Extract en una excepción."""
        if response.status_code >= 500:
            raise ExtractUnavailableError(f"estado {response.status_code}")
        try:
            detail = str(response.json()["detail"])
        except (ValueError, KeyError, TypeError):
            detail = "respuesta de error sin detalle"
        if response.status_code == 413:
            raise PdfTooLargeError(detail)
        if response.status_code == 415:
            raise UnsupportedMediaTypeError()
        raise ExtractionFailedError(detail)

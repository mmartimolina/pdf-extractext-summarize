r"""Cliente HTTP del microservicio Persistence.

Contrato verificado en ``D:\pdf-extractext-persistence`` (véase
``docs/integration-contracts.md``):

- ``POST /documents`` con JSON (``checksum`` obligatorio, campos
  opcionales) y ``X-Request-ID``.
- Éxito: ``201`` (creado) o ``200`` (repetición idempotente con datos
  idénticos).
- Error: ``{"error": {"code", "message"}}`` con 409 (conflicto), 422
  (datos inválidos), 503 (MongoDB no disponible) y 504 (timeout).
"""

import logging

import httpx

from pdf_summarize.domain.errors import (
    PersistenceConflictError,
    PersistenceRejectedError,
    PersistenceUnavailableError,
)
from pdf_summarize.domain.models import DocumentRecord

logger = logging.getLogger("pdf_summarize.persistence_client")


class PersistenceClient:
    """Adaptador del puerto ``Persister`` sobre HTTP."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    async def save(self, record: DocumentRecord, request_id: str) -> None:
        """Registra el documento procesado; idempotente por checksum."""
        payload = {
            "checksum": record.checksum,
            "checksum_algorithm": record.checksum_algorithm,
            "text": record.text,
            "summary": record.summary,
            "page_count": record.page_count,
            "file_size_bytes": record.file_size_bytes,
            "model": record.model,
        }
        try:
            response = await self._http.post(
                f"{self._base_url}/documents",
                json=payload,
                headers={"X-Request-ID": request_id},
            )
        except httpx.HTTPError as exc:
            logger.warning("persistence_call_failed request_id=%s", request_id)
            raise PersistenceUnavailableError(str(exc)) from exc

        if response.status_code in (200, 201):
            return

        raise self._map_error(response)

    async def aclose(self) -> None:
        """Cierra el cliente HTTP subyacente."""
        await self._http.aclose()

    @staticmethod
    def _map_error(response: httpx.Response) -> Exception:
        """Convierte la respuesta de error de Persistence en una excepción."""
        try:
            message = str(response.json()["error"]["message"])
        except (ValueError, KeyError, TypeError):
            message = f"estado {response.status_code}"

        if response.status_code == 409:
            raise PersistenceConflictError(message)
        if response.status_code >= 500:
            raise PersistenceUnavailableError(message)
        raise PersistenceRejectedError(message)

"""Adaptador HTTP de Persistence para la SAGA de sumarización."""

import httpx

from pdf_summarize.domain.errors import (
    PersistenceConflictError,
    PersistenceRejectedError,
    PersistenceUnavailableError,
)
from pdf_summarize.domain.models import DocumentRecord
from pdf_summarize.infrastructure.consul import ConsulResolver


class PersistenceClient:
    """Operaciones idempotentes de reserva, confirmación y compensación."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        resolver: ConsulResolver | None = None,
    ) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._resolver = resolver

    async def _base(self) -> str:
        return (
            await self._resolver.resolve("pdf-persistence", self._base_url)
            if self._resolver is not None
            else self._base_url
        )

    async def begin(
        self, checksum: str, checksum_algorithm: str, request_id: str
    ) -> None:
        """Crea la reserva PENDING identificada por la solicitud."""
        payload = {
            "checksum": checksum,
            "checksum_algorithm": checksum_algorithm,
            "metadata": {"saga_id": request_id, "saga_status": "PENDING"},
        }
        try:
            response = await self._http.post(
                f"{await self._base()}/documents",
                json=payload,
                headers={"X-Request-ID": request_id},
            )
        except httpx.HTTPError as exc:
            raise PersistenceUnavailableError(str(exc)) from exc
        if response.status_code == 201:
            return
        if response.status_code == 200:
            try:
                metadata = response.json().get("metadata") or {}
            except (ValueError, AttributeError):
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            if (
                metadata.get("saga_id") == request_id
                and metadata.get("saga_status") == "PENDING"
            ):
                return
            raise PersistenceConflictError(
                "El checksum ya está reservado por otra operación o SAGA."
            )
        raise self._map_error(response)

    async def save(self, record: DocumentRecord, request_id: str) -> None:
        """Confirma los datos procesados y cambia el estado a COMPLETED."""
        payload = {
            "checksum_algorithm": record.checksum_algorithm,
            "text": record.text,
            "summary": record.summary,
            "page_count": record.page_count,
            "file_size_bytes": record.file_size_bytes,
            "model": record.model,
            "metadata": {"saga_id": request_id, "saga_status": "COMPLETED"},
        }
        await self._request(
            "PUT", f"{await self._base()}/documents/{record.checksum}",
            payload, request_id,
        )

    async def compensate(self, checksum: str, request_id: str) -> None:
        """Compensa la reserva mediante eliminación lógica."""
        await self._request(
            "DELETE", f"{await self._base()}/documents/{checksum}", None, request_id
        )

    async def _request(
        self, method: str, url: str, payload: dict | None, request_id: str
    ) -> None:
        try:
            response = await self._http.request(
                method, url, json=payload, headers={"X-Request-ID": request_id}
            )
        except httpx.HTTPError as exc:
            raise PersistenceUnavailableError(str(exc)) from exc
        if response.status_code in (200, 201, 204):
            return
        raise self._map_error(response)

    async def aclose(self) -> None:
        await self._http.aclose()

    @staticmethod
    def _map_error(response: httpx.Response) -> Exception:
        try:
            message = str(response.json()["error"]["message"])
        except (ValueError, KeyError, TypeError):
            message = f"estado {response.status_code}"
        if response.status_code == 409:
            raise PersistenceConflictError(message)
        if response.status_code >= 500:
            raise PersistenceUnavailableError(message)
        raise PersistenceRejectedError(message)

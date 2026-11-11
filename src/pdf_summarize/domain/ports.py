"""Puertos (interfaces) que la capa de negocio requiere de la infraestructura."""

from typing import Protocol

from pdf_summarize.domain.models import (
    DocumentRecord,
    ExtractionResult,
    ValidationReport,
)


class Validator(Protocol):
    async def validate(self, pdf_bytes: bytes, request_id: str) -> ValidationReport: ...


class Extractor(Protocol):
    async def extract(self, pdf_bytes: bytes, request_id: str) -> ExtractionResult: ...


class Summarizer(Protocol):
    @property
    def model_name(self) -> str: ...

    async def summarize(self, prompt: str) -> str: ...

class Persister(Protocol):
    """Puerto de Persistence con operaciones de SAGA y compensación."""

    async def begin(
        self, checksum: str, checksum_algorithm: str, request_id: str
    ) -> None:
        """Reserva un documento en estado PENDING; es el primer paso con efecto."""

    async def save(self, record: DocumentRecord, request_id: str) -> None:
        """Confirma el documento como COMPLETED."""

    async def compensate(self, checksum: str, request_id: str) -> None:
        """Compensa la reserva mediante eliminación lógica."""
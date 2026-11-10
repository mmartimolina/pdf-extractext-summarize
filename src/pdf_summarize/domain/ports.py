"""Puertos requeridos por la capa de aplicación."""

from typing import Protocol

from pdf_summarize.domain.models import (
    DocumentRecord,
    ExtractionResult,
    ValidationReport,
)


class Validator(Protocol):
    """Puerto del microservicio Validation."""

    async def validate(self, pdf_bytes: bytes, request_id: str) -> ValidationReport: ...


class Extractor(Protocol):
    """Puerto del microservicio Extract."""

    async def extract(self, pdf_bytes: bytes, request_id: str) -> ExtractionResult: ...


class Summarizer(Protocol):
    """Puerto del proveedor de modelos de lenguaje."""

    @property
    def model_name(self) -> str: ...

    async def summarize(self, prompt: str) -> str: ...


class Persister(Protocol):
    """Puerto de Persistence con operaciones SAGA."""

    async def begin(
        self, checksum: str, checksum_algorithm: str, request_id: str
    ) -> None:
        """Reserva un documento en estado PENDING."""

    async def save(self, record: DocumentRecord, request_id: str) -> None:
        """Confirma el documento en estado COMPLETED."""

    async def compensate(self, checksum: str, request_id: str) -> None:
        """Compensa la reserva mediante eliminación lógica."""

"""Puertos (interfaces) que la capa de negocio requiere de la infraestructura.

Permiten sustituir los clientes reales por dobles de prueba sin acoplar
la capa de aplicación a HTTP o a un proveedor concreto.
"""

from typing import Protocol

from pdf_summarize.domain.models import (
    DocumentRecord,
    ExtractionResult,
    ValidationReport,
)


class Validator(Protocol):
    """Puerto del microservicio Validation."""

    async def validate(self, pdf_bytes: bytes, request_id: str) -> ValidationReport:
        """Valida el PDF y devuelve el informe con el checksum."""
        ...


class Extractor(Protocol):
    """Puerto del microservicio Extract."""

    async def extract(self, pdf_bytes: bytes, request_id: str) -> ExtractionResult:
        """Extrae el texto del PDF."""
        ...


class Summarizer(Protocol):
    """Puerto del proveedor de modelos de lenguaje."""

    @property
    def model_name(self) -> str:
        """Identificador del modelo configurado."""
        ...

    async def summarize(self, prompt: str) -> str:
        """Genera el resumen a partir del prompt."""
        ...


class Persister(Protocol):
    """Puerto del microservicio Persistence."""

    async def save(self, record: DocumentRecord, request_id: str) -> None:
        """Registra el documento procesado de forma idempotente."""
        ...

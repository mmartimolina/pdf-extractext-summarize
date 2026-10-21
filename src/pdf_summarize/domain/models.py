"""Modelos de dominio compartidos entre capas."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationReport:
    """Resultado de validar un PDF mediante el microservicio Validation."""

    file_size_bytes: int
    checksum: str
    checksum_algorithm: str


@dataclass(frozen=True)
class ExtractionResult:
    """Texto extraído de un PDF mediante el microservicio Extract."""

    content: str
    page_count: int


@dataclass(frozen=True)
class SummaryResult:
    """Resultado completo del flujo de sumarización."""

    summary: str
    page_count: int
    file_size_bytes: int
    checksum: str
    checksum_algorithm: str
    model: str


@dataclass(frozen=True)
class DocumentRecord:
    """Documento procesado listo para registrar en el microservicio Persistence."""

    checksum: str
    checksum_algorithm: str
    text: str
    summary: str
    page_count: int
    file_size_bytes: int
    model: str

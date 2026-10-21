"""Esquemas del contrato HTTP (capa de presentación).

Todas las respuestas, incluidos los errores, son JSON con un formato
uniforme y estable.
"""

from pydantic import BaseModel, Field

from pdf_summarize.domain.errors import SummarizeError


class HealthResponse(BaseModel):
    """Respuesta de los healthchecks."""

    status: str


class ReadinessResponse(BaseModel):
    """Respuesta del readiness probe, con el motivo cuando no está listo."""

    status: str
    reason: str | None = Field(default=None, description="Motivo si no está listo.")


class SummarizeResponse(BaseModel):
    """Respuesta exitosa de ``POST /summarize``."""

    summary: str = Field(description="Resumen generado por el modelo de IA.")
    page_count: int = Field(description="Cantidad de páginas del documento.")
    file_size_bytes: int = Field(description="Tamaño del archivo, en bytes.")
    checksum: str = Field(description="Checksum SHA-256 del contenido, hexadecimal.")
    checksum_algorithm: str = Field(description="Algoritmo del checksum.")
    model: str = Field(description="Modelo de IA utilizado para el resumen.")
    request_id: str = Field(
        description="Identificador correlacionable de la solicitud."
    )


class ErrorDetail(BaseModel):
    """Detalle estructurado de un error."""

    code: str = Field(description="Código identificable y estable del error.")
    message: str = Field(description="Mensaje legible y seguro para el consumidor.")
    request_id: str | None = Field(
        default=None, description="Identificador de la solicitud, si corresponde."
    )

    @classmethod
    def from_error(cls, error: SummarizeError, request_id: str | None) -> "ErrorDetail":
        return cls(code=error.code, message=error.message, request_id=request_id)


class ErrorResponse(BaseModel):
    """Envoltura uniforme de errores."""

    error: ErrorDetail

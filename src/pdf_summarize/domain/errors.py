"""Excepciones específicas del dominio con código estable y estado HTTP.

Cada excepción transporta un ``code`` identificable, un ``message`` apto
para el consumidor y el ``status_code`` HTTP asociado. Nunca incluyen
secretos, prompts ni contenido del documento.
"""

from typing import Final


class SummarizeError(Exception):
    """Error base del microservicio.

    Args:
        message: mensaje legible y seguro para el consumidor.
        status_code: estado HTTP asociado.
    """

    code: Final[str] = "SUMMARIZE_ERROR"

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class UnsupportedMediaTypeError(SummarizeError):
    """El Content-Type de la solicitud no es application/pdf."""

    code = "UNSUPPORTED_MEDIA_TYPE"

    def __init__(self) -> None:
        super().__init__("Se requiere Content-Type application/pdf.", status_code=415)


class EmptyPdfError(SummarizeError):
    """El cuerpo de la solicitud está vacío."""

    code = "EMPTY_PDF"

    def __init__(self) -> None:
        super().__init__("Request body is empty", status_code=400)


class PdfTooLargeError(SummarizeError):
    """El archivo excede el tamaño máximo configurado."""

    code = "PDF_TOO_LARGE"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message or "El archivo excede el tamaño máximo permitido.",
            status_code=413,
        )


class ValidationRejectedError(SummarizeError):
    """El microservicio Validation rechazó el documento."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message, status_code=422)
        self.code = code


class ValidationUnavailableError(SummarizeError):
    """Validation no responde o devolvió una respuesta inesperada."""

    code = "VALIDATION_UNAVAILABLE"

    def __init__(self, message: str) -> None:
        super().__init__(
            "El servicio de validación no está disponible.", status_code=503
        )
        self._detail = message


class ExtractionFailedError(SummarizeError):
    """El microservicio Extract no pudo procesar el documento."""

    code = "EXTRACTION_FAILED"

    def __init__(self, message: str) -> None:
        super().__init__(
            "No fue posible extraer el texto del documento.", status_code=422
        )


class ExtractUnavailableError(SummarizeError):
    """Extract no responde o devolvió una respuesta inesperada."""

    code = "EXTRACT_UNAVAILABLE"

    def __init__(self, message: str) -> None:
        super().__init__(
            "El servicio de extracción no está disponible.", status_code=503
        )


class NoUsefulTextError(SummarizeError):
    """La extracción no produjo texto suficiente para resumir."""

    code = "NO_USEFUL_TEXT"

    def __init__(self) -> None:
        super().__init__(
            "El documento no contiene texto útil para resumir.",
            status_code=422,
        )


class LLMNotConfiguredError(SummarizeError):
    """No hay credenciales configuradas para el proveedor de IA."""

    code = "LLM_NOT_CONFIGURED"

    def __init__(self) -> None:
        super().__init__(
            "El proveedor de IA no está configurado; no puede generarse "
            "un resumen real.",
            status_code=503,
        )


class LLMAuthError(SummarizeError):
    """El proveedor rechazó las credenciales (401/403)."""

    code = "LLM_AUTH_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(
            "El proveedor de IA rechazó las credenciales.", status_code=502
        )


class LLMRateLimitError(SummarizeError):
    """Se alcanzó el límite de uso del proveedor (429)."""

    code = "LLM_RATE_LIMITED"

    def __init__(self, message: str) -> None:
        super().__init__(
            "Se alcanzó el límite de uso del proveedor de IA.",
            status_code=503,
        )


class LLMTimeoutError(SummarizeError):
    """La llamada al proveedor de IA superó el timeout configurado."""

    code = "LLM_TIMEOUT"

    def __init__(self, message: str) -> None:
        super().__init__(
            "El proveedor de IA no respondió dentro del tiempo límite.",
            status_code=504,
        )


class LLMProviderError(SummarizeError):
    """El proveedor devolvió un error o una respuesta inválida."""

    code = "LLM_PROVIDER_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(
            "El proveedor de IA devolvió una respuesta inválida o falló.",
            status_code=502,
        )


class PersistenceUnavailableError(SummarizeError):
    """Persistence no responde o devolvió una respuesta inesperada."""

    code = "PERSISTENCE_UNAVAILABLE"

    def __init__(self, message: str) -> None:
        super().__init__(
            "El servicio de persistencia no está disponible.", status_code=503
        )
        self._detail = message


class PersistenceConflictError(SummarizeError):
    """El checksum ya está registrado en Persistence con datos distintos."""

    code = "PERSISTENCE_CONFLICT"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message or "Ya existe un documento registrado con datos distintos.",
            status_code=409,
        )


class PersistenceRejectedError(SummarizeError):
    """Persistence rechazó los datos del documento."""

    code = "PERSISTENCE_REJECTED"

    def __init__(self, message: str) -> None:
        super().__init__(
            "El servicio de persistencia rechazó los datos del documento.",
            status_code=502,
        )
        self._detail = message


class InternalError(SummarizeError):
    """Error interno no anticipado."""

    code = "INTERNAL_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__("Error interno del servicio.", status_code=500)

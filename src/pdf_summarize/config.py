"""Configuración del microservicio mediante variables de entorno (12-Factor)."""

import os
from dataclasses import dataclass

#: Tamaño máximo predeterminado de archivo, en bytes (20 MiB).
DEFAULT_MAX_PDF_SIZE_MIB = 20

#: Modelo inicial del proveedor de IA, usado en el proyecto original.
DEFAULT_LLM_MODEL = "meta/llama-3.1-8b-instruct"


def _read_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} debe ser un entero, se recibió: {raw!r}") from None
    if value <= 0:
        raise ValueError(f"{name} debe ser un entero positivo, se recibió: {value}")
    return value


def _read_float(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{name} debe ser un número, se recibió: {raw!r}") from None
    if value <= 0:
        raise ValueError(f"{name} debe ser un número positivo, se recibió: {value}")
    return value


def _read_url(name: str, default: str) -> str:
    """Lee una URL recortando la barra final para componer rutas de forma segura."""
    return os.environ.get(name, default).rstrip("/")


@dataclass(frozen=True)
class Settings:
    """Configuración inmutable de la aplicación.

    Toda la configuración proviene del entorno; los secretos nunca se
    escriben en el repositorio.
    """

    max_pdf_size_bytes: int
    validation_service_url: str
    extract_service_url: str
    persistence_service_url: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout_seconds: float
    llm_max_tokens: int
    upstream_timeout_seconds: float
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Construye la configuración desde variables de entorno.

        Variables:
            MAX_PDF_SIZE_MIB: tamaño máximo aceptado del PDF, en MiB.
            VALIDATION_SERVICE_URL: URL base del microservicio Validation.
            EXTRACT_SERVICE_URL: URL base del microservicio Extract.
            PERSISTENCE_SERVICE_URL: URL base del microservicio Persistence.
            LLM_BASE_URL: URL base de la API compatible con OpenAI.
            LLM_API_KEY: clave del proveedor de IA (secreto).
            LLM_MODEL: identificador del modelo.
            LLM_TIMEOUT_SECONDS: timeout de las llamadas al proveedor.
            LLM_MAX_TOKENS: longitud máxima de salida del resumen.
            UPSTREAM_TIMEOUT_SECONDS: timeout hacia los microservicios.
            LOG_LEVEL: nivel de logging (INFO por defecto).

        Raises:
            ValueError: si alguna variable numérica es inválida.
        """
        return cls(
            max_pdf_size_bytes=_read_int("MAX_PDF_SIZE_MIB", DEFAULT_MAX_PDF_SIZE_MIB)
            * 1024
            * 1024,
            validation_service_url=_read_url(
                "VALIDATION_SERVICE_URL", "http://pdf-validation:8000"
            ),
            extract_service_url=_read_url("EXTRACT_SERVICE_URL", "http://extract:8000"),
            persistence_service_url=_read_url(
                "PERSISTENCE_SERVICE_URL", "http://pdf-persistence:8003"
            ),
            llm_base_url=_read_url(
                "LLM_BASE_URL", "https://integrate.api.nvidia.com/v1"
            ),
            llm_api_key=os.environ.get("LLM_API_KEY", ""),
            llm_model=os.environ.get("LLM_MODEL", DEFAULT_LLM_MODEL),
            llm_timeout_seconds=_read_float("LLM_TIMEOUT_SECONDS", 60.0),
            llm_max_tokens=_read_int("LLM_MAX_TOKENS", 1000),
            upstream_timeout_seconds=_read_float("UPSTREAM_TIMEOUT_SECONDS", 30.0),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )

    def llm_configured(self) -> bool:
        """Indica si el proveedor de IA tiene credenciales configuradas."""
        return bool(self.llm_api_key)

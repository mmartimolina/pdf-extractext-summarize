"""Configuración de logs estructurados en formato JSON.

Nunca se registran bytes del PDF, texto extraído, prompts ni claves de
API: solo códigos, tamaños, checksums e identificadores de solicitud.
"""

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Formateador JSON de una línea por registro de log."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """Configura el logger raíz con salida JSON por stdout."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def log_level_from_name(name: str) -> int:
    """Traduce un nombre de nivel (``INFO``, ``DEBUG``, ...) a entero."""
    return getattr(logging, name.upper(), logging.INFO)

"""Métricas Prometheus del microservicio.

Métricas expuestas en ``GET /metrics``:

- ``pdf_summarize_requests_total``: contador de solicitudes HTTP
  procesadas, etiquetado por ruta y código de estado.
- ``pdf_summarize_request_latency_seconds``: histograma de la latencia
  de procesamiento de cada solicitud, etiquetado por ruta.
"""

from prometheus_client import Counter, Histogram, generate_latest

REQUESTS_TOTAL = Counter(
    "pdf_summarize_requests_total",
    "Solicitudes HTTP procesadas por ruta y código de estado.",
    ["route", "status"],
)

REQUEST_LATENCY = Histogram(
    "pdf_summarize_request_latency_seconds",
    "Latencia de procesamiento de solicitudes HTTP por ruta, en segundos.",
    ["route"],
)


def render_metrics() -> bytes:
    """Devuelve las métricas en el formato de exposición de Prometheus."""
    return generate_latest()

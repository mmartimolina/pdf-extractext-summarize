"""Middlewares de la API: correlación de solicitudes, métricas y logs."""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

from pdf_summarize.api.metrics import REQUEST_LATENCY, REQUESTS_TOTAL

logger = logging.getLogger("pdf_summarize.http")

#: Rutas de infraestructura que no generan métricas de negocio.
_UNMEASURED_ROUTES = {"/metrics"}


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Propaga ``X-Request-ID`` entrante o genera uno nuevo por solicitud."""

    async def dispatch(self, request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Registra cada solicitud y mide su latencia y resultado.

    No se registran cuerpos, archivos PDF ni contenido sensible; solo
    ruta, estado, latencia e identificador de solicitud.
    """

    async def dispatch(self, request, call_next):
        route = request.url.path
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            REQUESTS_TOTAL.labels(route=route, status="500").inc()
            logger.exception(
                "request_failed method=%s route=%s request_id=%s",
                request.method,
                route,
                getattr(request.state, "request_id", "-"),
            )
            raise
        latency = time.perf_counter() - start
        if route not in _UNMEASURED_ROUTES:
            REQUEST_LATENCY.labels(route=route).observe(latency)
            REQUESTS_TOTAL.labels(route=route, status=str(response.status_code)).inc()
        logger.info(
            "request_completed method=%s route=%s status=%d latency_ms=%d "
            "request_id=%s",
            request.method,
            route,
            response.status_code,
            int(latency * 1000),
            getattr(request.state, "request_id", "-"),
        )
        return response

"""Rate limiting local por ventana móvil para proteger la API."""

import os
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Limita solicitudes por IP y ventana; excluye health y métricas."""

    def __init__(self, app):
        super().__init__(app)
        self.limit = int(os.environ.get("RATE_LIMIT_REQUESTS", "60"))
        self.window = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
        if self.limit < 1 or self.window < 1:
            raise ValueError("Los parámetros RATE_LIMIT deben ser positivos")
        self.requests: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request, call_next):
        if request.url.path in {"/health/live", "/health/ready", "/metrics"}:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        timestamps = self.requests[client_ip]
        while timestamps and now - timestamps[0] >= self.window:
            timestamps.popleft()

        if len(timestamps) >= self.limit:
            retry_after = max(1, int(self.window - (now - timestamps[0])))
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "RATE_LIMIT_EXCEEDED",
                                   "message": "Demasiadas solicitudes. Intente nuevamente."}},
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)
        return await call_next(request)

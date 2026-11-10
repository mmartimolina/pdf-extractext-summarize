"""Cliente HTTP con reintentos acotados y Circuit Breaker."""

import asyncio
import time
from typing import Any

import httpx


class CircuitOpenError(httpx.TransportError):
    """La dependencia está temporalmente bloqueada por el Circuit Breaker."""


class ResilientHttpClient:
    """Envuelve AsyncClient con Retry y Circuit Breaker por dependencia."""

    RETRYABLE_STATUS = frozenset({502, 503, 504})

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_attempts: int = 3,
        failure_threshold: int = 5,
        recovery_timeout: float = 20.0,
        retry_delay: float = 0.2,
    ) -> None:
        if max_attempts < 1 or failure_threshold < 1:
            raise ValueError("max_attempts y failure_threshold deben ser positivos")
        self._client = client
        self._max_attempts = max_attempts
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._retry_delay = retry_delay
        self._failures = 0
        self._opened_at: float | None = None
        self._probe_in_flight = False
        self._lock = asyncio.Lock()

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Ejecuta POST con Retry y Circuit Breaker."""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Ejecuta PUT con Retry y Circuit Breaker."""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Ejecuta DELETE con Retry y Circuit Breaker."""
        return await self.request("DELETE", url, **kwargs)

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Ejecuta un método HTTP con reintentos ante fallos transitorios."""
        method = method.upper()
        await self._allow_request(method, url)
        try:
            for attempt in range(self._max_attempts):
                try:
                    response = await self._client.request(method, url, **kwargs)
                except httpx.TransportError:
                    if attempt + 1 >= self._max_attempts:
                        raise
                    await asyncio.sleep(self._retry_delay * (2**attempt))
                    continue

                if (
                    response.status_code in self.RETRYABLE_STATUS
                    and attempt + 1 < self._max_attempts
                ):
                    await response.aread()
                    await response.aclose()
                    await asyncio.sleep(self._retry_delay * (2**attempt))
                    continue

                if response.status_code >= 500:
                    await self._record_failure()
                else:
                    await self._record_success()
                return response

            raise RuntimeError("bucle de reintentos finalizado inesperadamente")
        except Exception:
            await self._record_failure()
            raise

    async def _allow_request(self, method: str, url: str) -> None:
        async with self._lock:
            if self._opened_at is None:
                return
            elapsed = time.monotonic() - self._opened_at
            if elapsed < self._recovery_timeout or self._probe_in_flight:
                request = httpx.Request(method, url)
                raise CircuitOpenError("Circuit Breaker abierto", request=request)
            self._probe_in_flight = True

    async def _record_success(self) -> None:
        async with self._lock:
            self._failures = 0
            self._opened_at = None
            self._probe_in_flight = False

    async def _record_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            if self._probe_in_flight or self._failures >= self._failure_threshold:
                self._opened_at = time.monotonic()
            self._probe_in_flight = False

    async def aclose(self) -> None:
        """Cierra el cliente HTTP subyacente."""
        await self._client.aclose()

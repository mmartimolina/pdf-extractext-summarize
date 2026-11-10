"""Registro opcional del servicio en Consul Agent."""

import asyncio
import json
import logging
import os
import socket
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


class ConsulRegistration:
    """Registra y desregistra una instancia mediante la API HTTP de Consul."""

    def __init__(self, service_name: str, port: int, health_path: str) -> None:
        self.address = os.environ.get("CONSUL_HTTP_ADDR", "").rstrip("/")
        self.service_name = service_name
        self.service_id = os.environ.get(
            "CONSUL_SERVICE_ID", f"{service_name}-{socket.gethostname()}"
        )
        self.service_address = os.environ.get("SERVICE_ADDRESS", service_name)
        self.port = port
        self.health_path = health_path
        self.enabled = bool(self.address)

    async def register(self) -> None:
        if not self.enabled:
            logger.info("consul_registration_disabled service=%s", self.service_name)
            return
        payload = {
            "ID": self.service_id,
            "Name": self.service_name,
            "Address": self.service_address,
            "Port": self.port,
            "Check": {
                "HTTP": f"http://{self.service_address}:{self.port}{self.health_path}",
                "Interval": "10s",
                "Timeout": "3s",
                "DeregisterCriticalServiceAfter": "1m",
            },
        }
        await asyncio.to_thread(self._request, "PUT", "/v1/agent/service/register", payload)
        logger.info("consul_service_registered service=%s id=%s", self.service_name, self.service_id)

    async def deregister(self) -> None:
        if not self.enabled:
            return
        try:
            await asyncio.to_thread(
                self._request, "PUT", f"/v1/agent/service/deregister/{self.service_id}", None
            )
            logger.info("consul_service_deregistered service=%s", self.service_name)
        except Exception:
            logger.exception("consul_service_deregister_failed service=%s", self.service_name)

    def _request(self, method: str, path: str, payload: dict | None) -> None:
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            f"{self.address}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=3):
                return
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Consul no disponible: {exc}") from exc

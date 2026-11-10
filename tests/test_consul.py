"""Pruebas del registro y descubrimiento de servicios en Consul."""

import pytest

from pdf_summarize.infrastructure.consul import ConsulRegistration, ConsulResolver


@pytest.mark.asyncio
async def test_resolver_devuelve_instancia_saludable(monkeypatch) -> None:
    resolver = ConsulResolver("http://consul:8500")

    def lookup(service_name: str):
        assert service_name == "extract"
        return [
            {
                "Service": {"Address": "10.0.0.12", "Port": 8000},
                "Node": {"Address": "10.0.0.2"},
            }
        ]

    monkeypatch.setattr(resolver, "_lookup", lookup)

    assert await resolver.resolve("extract", "http://extract:8000") == "http://10.0.0.12:8000"


@pytest.mark.asyncio
async def test_resolver_usa_fallback_si_no_hay_instancias(monkeypatch) -> None:
    resolver = ConsulResolver("http://consul:8500")
    monkeypatch.setattr(resolver, "_lookup", lambda service_name: [])

    assert await resolver.resolve("extract", "http://extract:8000") == "http://extract:8000"


@pytest.mark.asyncio
async def test_resolver_desactivado_usa_fallback() -> None:
    resolver = ConsulResolver("")

    assert await resolver.resolve("extract", "http://extract:8000") == "http://extract:8000"



@pytest.mark.asyncio
async def test_registration_y_deregistration_en_consul(monkeypatch) -> None:
    monkeypatch.setenv("CONSUL_HTTP_ADDR", "http://consul:8500")
    monkeypatch.setenv("SERVICE_ADDRESS", "127.0.0.1")
    registration = ConsulRegistration("test-service", 8000, "/health/live")
    calls = []

    def fake_request(method, path, payload):
        calls.append((method, path, payload))

    monkeypatch.setattr(registration, "_request", fake_request)

    await registration.register()
    assert registration.registered is True
    assert calls[0][0:2] == ("PUT", "/v1/agent/service/register")
    assert calls[0][2]["Check"]["HTTP"] == "http://127.0.0.1:8000/health/live"

    await registration.deregister()
    assert calls[1][0:2] == ("PUT", f"/v1/agent/service/deregister/{registration.service_id}")


@pytest.mark.asyncio
async def test_registration_falla_sin_interrumpir_el_servicio(monkeypatch) -> None:
    monkeypatch.setenv("CONSUL_HTTP_ADDR", "http://consul:8500")
    registration = ConsulRegistration("test-service", 8000, "/health/live")

    def failed_request(*args, **kwargs):
        raise RuntimeError("Consul no disponible")

    monkeypatch.setattr(registration, "_request", failed_request)

    await registration.register()
    assert registration.registered is False

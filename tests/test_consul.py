"""Pruebas del registro y descubrimiento de servicios en Consul."""

import pytest

from pdf_summarize.infrastructure.consul import ConsulResolver


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

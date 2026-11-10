"""Pruebas del cliente HTTP resiliente."""

import httpx
import pytest

from pdf_summarize.infrastructure.resilient_http import (
    CircuitOpenError,
    ResilientHttpClient,
)


@pytest.mark.asyncio
async def test_reintenta_respuesta_transitoria_y_recupera() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    raw = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ResilientHttpClient(raw, retry_delay=0)

    response = await client.post("http://dependency.test/operation")

    assert response.status_code == 200
    assert calls == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_circuit_breaker_abre_y_permite_sonda_de_recuperacion(monkeypatch) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        status = 503 if calls == 1 else 200
        return httpx.Response(status, request=request)

    clock = [100.0]
    monkeypatch.setattr(
        "pdf_summarize.infrastructure.resilient_http.time.monotonic",
        lambda: clock[0],
    )
    raw = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ResilientHttpClient(
        raw,
        max_attempts=1,
        failure_threshold=1,
        recovery_timeout=20,
    )

    first = await client.post("http://dependency.test/operation")
    assert first.status_code == 503

    with pytest.raises(CircuitOpenError):
        await client.post("http://dependency.test/operation")

    clock[0] += 21
    recovered = await client.post("http://dependency.test/operation")
    assert recovered.status_code == 200
    assert calls == 2
    await client.aclose()



@pytest.mark.asyncio
async def test_admite_put_y_delete_con_la_misma_capa_resiliente() -> None:
    methods = []

    async def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200, request=request)

    raw = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ResilientHttpClient(raw, retry_delay=0)

    put_response = await client.put("http://dependency.test/documents/1", json={"ok": True})
    delete_response = await client.delete("http://dependency.test/documents/1")

    assert put_response.status_code == 200
    assert delete_response.status_code == 200
    assert methods == ["PUT", "DELETE"]
    await client.aclose()

"""Pruebas del middleware de limitación de solicitudes."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pdf_summarize.api.rate_limit import RateLimitMiddleware


def test_rate_limit_rechaza_solicitudes_excedentes(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/resource")
    async def resource():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/resource").status_code == 200
    assert client.get("/resource").status_code == 200

    blocked = client.get("/resource")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert int(blocked.headers["Retry-After"]) >= 1


def test_rate_limit_no_bloquea_healthcheck(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/health/live")
    async def health():
        return {"status": "alive"}

    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/live").status_code == 200

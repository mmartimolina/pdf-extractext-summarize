"""Pruebas de utilidades de la capa de presentación."""

import pytest
from starlette.requests import Request

from pdf_summarize.api.routes import read_body_with_limit
from pdf_summarize.app import create_app
from pdf_summarize.config import Settings
from pdf_summarize.domain.errors import PdfTooLargeError


def make_request(headers: dict[str, str], body: bytes) -> Request:
    """Construye una Request de Starlette con cuerpo finito."""
    encoded = [(key.lower().encode(), value.encode()) for key, value in headers.items()]
    payload = body

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request(
        scope={
            "type": "http",
            "method": "POST",
            "path": "/summarize",
            "headers": encoded,
            "query_string": b"",
        },
        receive=receive,
    )


class TestReadBodyWithLimit:
    async def test_reads_body_under_limit(self):
        request = make_request({}, b"12345678")
        assert await read_body_with_limit(request, limit=100) == b"12345678"

    async def test_rejects_declared_content_length_over_limit(self):
        request = make_request({"Content-Length": "999"}, b"123")
        with pytest.raises(PdfTooLargeError):
            await read_body_with_limit(request, limit=100)

    async def test_invalid_content_length_is_ignored(self):
        request = make_request({"Content-Length": "abc"}, b"contenido")
        assert await read_body_with_limit(request, limit=100) == b"contenido"

    async def test_rejects_stream_larger_than_limit(self):
        request = make_request({}, b"x" * 200)
        with pytest.raises(PdfTooLargeError):
            await read_body_with_limit(request, limit=100)


class TestCreateAppDefaults:
    def test_create_app_without_args_reads_environment(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "env-key")
        monkeypatch.setenv("MAX_PDF_SIZE_MIB", "5")
        monkeypatch.delenv("LLM_MODEL", raising=False)

        app = create_app()

        settings = app.state.settings
        assert isinstance(settings, Settings)
        assert settings.llm_api_key == "env-key"
        assert settings.max_pdf_size_bytes == 5 * 1024 * 1024
        assert app.state.container is not None

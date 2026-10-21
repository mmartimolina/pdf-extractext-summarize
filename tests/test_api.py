"""Pruebas de los endpoints HTTP, middlewares y ciclo de vida."""

import httpx
import pytest
from conftest import FakeContainer, make_settings
from fastapi import FastAPI

from pdf_summarize.app import create_app
from pdf_summarize.domain.errors import (
    EmptyPdfError,
    ExtractUnavailableError,
    InternalError,
    LLMNotConfiguredError,
    PdfTooLargeError,
    PersistenceConflictError,
    PersistenceUnavailableError,
    ValidationRejectedError,
    ValidationUnavailableError,
)
from pdf_summarize.service.summarize_use_case import SummarizeUseCase

PDF_BYTES = b"%PDF-1.4 fake content"


def build_app(container: FakeContainer | None = None, settings=None) -> FastAPI:
    if container is None:
        container = FakeContainer()
        container.use_case = SummarizeUseCase(
            validation_client=container.validation_client,
            extract_client=container.extract_client,
            llm_client=container.llm_client,
            persistence_client=container.persistence_client,
        )
    return create_app(
        settings or make_settings(),
        container=container,
    )


@pytest.fixture
async def client(fake_container):
    """Cliente HTTP contra la app con dependencias falsas y lifespan activo."""
    fake_container.use_case = SummarizeUseCase(
        validation_client=fake_container.validation_client,
        extract_client=fake_container.extract_client,
        llm_client=fake_container.llm_client,
        persistence_client=fake_container.persistence_client,
    )
    app = create_app(make_settings(), container=fake_container)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as http_client:
            yield http_client, app


class TestSummarizeEndpoint:
    async def test_success_returns_summary_json(self, client):
        response, _ = client
        result = await response.post(
            "/summarize", content=PDF_BYTES, headers={"Content-Type": "application/pdf"}
        )
        assert result.status_code == 200
        body = result.json()
        assert body["summary"] == "Resumen del documento."
        assert body["page_count"] == 2
        assert body["file_size_bytes"] == 512
        assert body["checksum"] == "cafebabe"
        assert body["checksum_algorithm"] == "sha256"
        assert body["model"] == "meta/llama-3.1-8b-instruct"
        assert body["request_id"]

    async def test_success_persists_document_via_persistence_client(
        self, client, fake_container
    ):
        response, _ = client
        result = await response.post(
            "/summarize",
            content=PDF_BYTES,
            headers={
                "Content-Type": "application/pdf",
                "X-Request-ID": "req-persist-1",
            },
        )
        assert result.status_code == 200
        calls = fake_container.persistence_client.calls
        assert len(calls) == 1
        record, request_id = calls[0]
        assert record.checksum == "cafebabe"
        assert record.summary == "Resumen del documento."
        assert request_id == "req-persist-1"

    async def test_persistence_unavailable_returns_503_json_error(self, fake_container):
        fake_container.persistence_client.error = PersistenceUnavailableError("down")
        fake_container.use_case = SummarizeUseCase(
            fake_container.validation_client,
            fake_container.extract_client,
            fake_container.llm_client,
            fake_container.persistence_client,
        )
        app = create_app(make_settings(), container=fake_container)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as http_client:
                result = await http_client.post(
                    "/summarize",
                    content=PDF_BYTES,
                    headers={"Content-Type": "application/pdf"},
                )
        assert result.status_code == 503
        assert result.json()["error"]["code"] == "PERSISTENCE_UNAVAILABLE"

    async def test_wrong_content_type_returns_415_json_error(self, client):
        response, _ = client
        result = await response.post(
            "/summarize", content=PDF_BYTES, headers={"Content-Type": "text/plain"}
        )
        assert result.status_code == 415
        body = result.json()
        assert body["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
        assert body["error"]["message"]

    async def test_missing_content_type_returns_415(self, client):
        response, _ = client
        result = await response.post("/summarize", content=PDF_BYTES)
        assert result.status_code == 415

    async def test_empty_body_returns_400_json_error(self, client):
        response, _ = client
        result = await response.post(
            "/summarize", content=b"", headers={"Content-Type": "application/pdf"}
        )
        assert result.status_code == 400
        assert result.json()["error"]["code"] == "EMPTY_PDF"

    async def test_content_length_over_limit_returns_413(self):
        container = FakeContainer()
        container.use_case = SummarizeUseCase(
            container.validation_client,
            container.extract_client,
            container.llm_client,
            container.persistence_client,
        )
        app = create_app(make_settings(max_pdf_size_bytes=10), container=container)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as http_client:
                result = await http_client.post(
                    "/summarize",
                    content=PDF_BYTES,
                    headers={
                        "Content-Type": "application/pdf",
                        "Content-Length": str(len(PDF_BYTES)),
                    },
                )
        assert result.status_code == 413
        assert result.json()["error"]["code"] == "PDF_TOO_LARGE"


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("error", "status", "code"),
        [
            (ValidationRejectedError("INVALID_PDF", "roto"), 422, "INVALID_PDF"),
            (ValidationUnavailableError("down"), 503, "VALIDATION_UNAVAILABLE"),
            (ExtractUnavailableError("down"), 503, "EXTRACT_UNAVAILABLE"),
            (EmptyPdfError(), 400, "EMPTY_PDF"),
            (LLMNotConfiguredError(), 503, "LLM_NOT_CONFIGURED"),
            (
                PersistenceUnavailableError("down"),
                503,
                "PERSISTENCE_UNAVAILABLE",
            ),
            (
                PersistenceConflictError("datos distintos"),
                409,
                "PERSISTENCE_CONFLICT",
            ),
            (PdfTooLargeError(), 413, "PDF_TOO_LARGE"),
            (InternalError("boom"), 500, "INTERNAL_ERROR"),
        ],
    )
    async def test_domain_errors_map_to_json_responses(
        self, fake_container, error, status, code
    ):
        class FailingUseCase:
            async def execute(self, pdf_bytes, request_id):
                raise error

        fake_container.use_case = FailingUseCase()
        app = create_app(make_settings(), container=fake_container)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as http_client:
                result = await http_client.post(
                    "/summarize",
                    content=PDF_BYTES,
                    headers={"Content-Type": "application/pdf"},
                )
        assert result.status_code == status
        assert result.json()["error"]["code"] == code

    async def test_validation_unavailable_returns_503_json(self, fake_container):
        fake_container.validation_client.error = ValidationUnavailableError("x")
        fake_container.use_case = SummarizeUseCase(
            fake_container.validation_client,
            fake_container.extract_client,
            fake_container.llm_client,
            fake_container.persistence_client,
        )
        app = create_app(make_settings(), container=fake_container)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as http_client:
                result = await http_client.post(
                    "/summarize",
                    content=PDF_BYTES,
                    headers={"Content-Type": "application/pdf"},
                )
        assert result.status_code == 503
        assert result.json()["error"]["code"] == "VALIDATION_UNAVAILABLE"

    async def test_llm_not_configured_returns_503_json(self, fake_container):
        fake_container.llm_client.error = LLMNotConfiguredError()
        fake_container.use_case = SummarizeUseCase(
            fake_container.validation_client,
            fake_container.extract_client,
            fake_container.llm_client,
            fake_container.persistence_client,
        )
        app = create_app(make_settings(), container=fake_container)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as http_client:
                result = await http_client.post(
                    "/summarize",
                    content=PDF_BYTES,
                    headers={"Content-Type": "application/pdf"},
                )
        assert result.status_code == 503
        assert result.json()["error"]["code"] == "LLM_NOT_CONFIGURED"

    async def test_unexpected_exception_returns_500_without_traceback(
        self, fake_container
    ):
        class ExplodingUseCase:
            async def execute(self, pdf_bytes, request_id):
                raise RuntimeError("detalle interno con secreto")

        fake_container.use_case = ExplodingUseCase()
        app = create_app(make_settings(), container=fake_container)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as http_client:
                result = await http_client.post(
                    "/summarize",
                    content=PDF_BYTES,
                    headers={"Content-Type": "application/pdf"},
                )
        assert result.status_code == 500
        body = result.json()
        assert body["error"]["code"] == "INTERNAL_ERROR"
        assert "secreto" not in result.text
        assert "Traceback" not in result.text


class TestRequestIdCorrelation:
    async def test_incoming_request_id_is_reused(self, client):
        response, _ = client
        result = await response.post(
            "/summarize",
            content=PDF_BYTES,
            headers={
                "Content-Type": "application/pdf",
                "X-Request-ID": "req-abc-123",
            },
        )
        assert result.status_code == 200
        assert result.headers["X-Request-ID"] == "req-abc-123"
        assert result.json()["request_id"] == "req-abc-123"

    async def test_request_id_generated_when_missing(self, client):
        response, _ = client
        result = await response.post(
            "/summarize", content=PDF_BYTES, headers={"Content-Type": "application/pdf"}
        )
        assert result.headers["X-Request-ID"]
        assert result.json()["request_id"] == result.headers["X-Request-ID"]

    async def test_request_id_propagated_to_dependencies(self, client, fake_container):
        response, _ = client
        await response.post(
            "/summarize",
            content=PDF_BYTES,
            headers={
                "Content-Type": "application/pdf",
                "X-Request-ID": "req-prop-1",
            },
        )
        assert fake_container.validation_client.calls[0][1] == "req-prop-1"
        assert fake_container.extract_client.calls[0][1] == "req-prop-1"


class TestHealthEndpoints:
    async def test_health_live_is_alive_without_dependencies(self, fake_container):
        app = create_app(make_settings(llm_api_key=""), container=fake_container)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as http_client:
            result = await http_client.get("/health/live")
        assert result.status_code == 200
        assert result.json()["status"] == "alive"

    async def test_health_ready_when_llm_configured(self, client):
        response, _ = client
        result = await response.get("/health/ready")
        assert result.status_code == 200
        assert result.json()["status"] == "ready"

    async def test_health_ready_503_when_llm_not_configured(self):
        container = FakeContainer()
        container.use_case = SummarizeUseCase(
            container.validation_client,
            container.extract_client,
            container.llm_client,
            container.persistence_client,
        )
        app = create_app(make_settings(llm_api_key=""), container=container)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as http_client:
            result = await http_client.get("/health/ready")
        assert result.status_code == 503
        body = result.json()
        assert body["status"] == "not_ready"
        assert "LLM_API_KEY" in body["reason"]


class TestMetrics:
    async def test_metrics_exposes_prometheus_format(self, client):
        response, _ = client
        await response.post(
            "/summarize", content=PDF_BYTES, headers={"Content-Type": "application/pdf"}
        )
        result = await response.get("/metrics")
        assert result.status_code == 200
        assert "pdf_summarize_requests_total" in result.text
        assert "pdf_summarize_request_latency_seconds" in result.text

    async def test_requests_counter_increases(self, client):
        response, _ = client
        before = (await response.get("/metrics")).text
        await response.post(
            "/summarize", content=PDF_BYTES, headers={"Content-Type": "application/pdf"}
        )
        after = (await response.get("/metrics")).text

        def total_for(text):
            for line in text.splitlines():
                if line.startswith("pdf_summarize_requests_total{"):
                    return float(line.rsplit(" ", 1)[1])
            return 0.0

        assert total_for(after) > total_for(before)


class TestLifespan:
    async def test_container_closed_on_shutdown(self, fake_container):
        fake_container.use_case = SummarizeUseCase(
            fake_container.validation_client,
            fake_container.extract_client,
            fake_container.llm_client,
            fake_container.persistence_client,
        )
        app = create_app(make_settings(), container=fake_container)
        async with app.router.lifespan_context(app):
            assert not fake_container.closed
        assert fake_container.closed is True

    async def test_real_container_closes_http_clients(self):
        from pdf_summarize.container import Container

        settings = make_settings()
        container = Container.build(settings)
        app = create_app(settings, container=container)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as http_client:
                result = await http_client.get("/health/live")
            assert result.status_code == 200
        assert container.validation_client_closed
        assert container.extract_client_closed
        assert container.llm_client_closed
        assert container.persistence_client_closed

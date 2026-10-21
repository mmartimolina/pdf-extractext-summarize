"""Pruebas de los clientes HTTP de infraestructura con transporte simulado."""

import json
from typing import ClassVar

import httpx
import pytest

from pdf_summarize.domain.errors import (
    EmptyPdfError,
    ExtractionFailedError,
    ExtractUnavailableError,
    LLMAuthError,
    LLMNotConfiguredError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    PdfTooLargeError,
    PersistenceConflictError,
    PersistenceRejectedError,
    PersistenceUnavailableError,
    UnsupportedMediaTypeError,
    ValidationRejectedError,
    ValidationUnavailableError,
)
from pdf_summarize.domain.models import (
    DocumentRecord,
    ExtractionResult,
    ValidationReport,
)
from pdf_summarize.infrastructure.extract_client import ExtractClient
from pdf_summarize.infrastructure.llm_client import LLMClient
from pdf_summarize.infrastructure.persistence_client import PersistenceClient
from pdf_summarize.infrastructure.validation_client import ValidationClient

VALIDATION_SUCCESS = {
    "valid": True,
    "file_size_bytes": 512,
    "checksum": "cafebabe",
    "checksum_algorithm": "sha256",
}


def async_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestValidationClient:
    async def test_success_returns_report_and_propagates_request_id(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["content_type"] = request.headers["content-type"]
            seen["request_id"] = request.headers.get("x-request-id")
            return httpx.Response(200, json=VALIDATION_SUCCESS)

        client = ValidationClient(async_client(handler), "http://validation:8000")
        report = await client.validate(b"%PDF-fake", request_id="req-9")

        assert isinstance(report, ValidationReport)
        assert report.checksum == "cafebabe"
        assert report.file_size_bytes == 512
        assert seen["path"] == "/validate"
        assert seen["content_type"] == "application/pdf"
        assert seen["request_id"] == "req-9"
        await client.aclose()

    @pytest.mark.parametrize(
        ("payload", "status", "expected"),
        [
            ({"error": {"code": "EMPTY_PDF", "message": "vacío"}}, 400, EmptyPdfError),
            (
                {"error": {"code": "PDF_TOO_LARGE", "message": "grande"}},
                413,
                PdfTooLargeError,
            ),
            (
                {"error": {"code": "UNSUPPORTED_MEDIA_TYPE", "message": "ct"}},
                415,
                UnsupportedMediaTypeError,
            ),
            (
                {"error": {"code": "INVALID_PDF", "message": "roto"}},
                422,
                ValidationRejectedError,
            ),
        ],
    )
    async def test_client_errors_map_to_domain(self, payload, status, expected):
        client = ValidationClient(
            async_client(lambda r: httpx.Response(status, json=payload)),
            "http://validation:8000",
        )
        with pytest.raises(expected):
            await client.validate(b"%PDF-fake", request_id="req-1")

    async def test_validation_rejected_preserves_upstream_code(self):
        client = ValidationClient(
            async_client(
                lambda r: httpx.Response(
                    422,
                    json={"error": {"code": "ENCRYPTED_PDF", "message": "cifrado"}},
                )
            ),
            "http://validation:8000",
        )
        with pytest.raises(ValidationRejectedError) as excinfo:
            await client.validate(b"%PDF-fake", request_id="req-1")
        assert excinfo.value.code == "ENCRYPTED_PDF"
        assert "cifrado" in excinfo.value.message

    async def test_server_error_maps_to_unavailable(self):
        client = ValidationClient(
            async_client(
                lambda r: httpx.Response(
                    500, json={"error": {"code": "INTERNAL", "message": "boom"}}
                )
            ),
            "http://validation:8000",
        )
        with pytest.raises(ValidationUnavailableError):
            await client.validate(b"%PDF-fake", request_id="req-1")

    async def test_timeout_maps_to_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("expired")

        client = ValidationClient(async_client(handler), "http://validation:8000")
        with pytest.raises(ValidationUnavailableError):
            await client.validate(b"%PDF-fake", request_id="req-1")

    async def test_connect_error_maps_to_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = ValidationClient(async_client(handler), "http://validation:8000")
        with pytest.raises(ValidationUnavailableError):
            await client.validate(b"%PDF-fake", request_id="req-1")

    async def test_invalid_success_payload_maps_to_unavailable(self):
        client = ValidationClient(
            async_client(lambda r: httpx.Response(200, json={"unexpected": 1})),
            "http://validation:8000",
        )
        with pytest.raises(ValidationUnavailableError):
            await client.validate(b"%PDF-fake", request_id="req-1")

    async def test_malformed_json_maps_to_unavailable(self):
        client = ValidationClient(
            async_client(lambda r: httpx.Response(200, text="not-json")),
            "http://validation:8000",
        )
        with pytest.raises(ValidationUnavailableError):
            await client.validate(b"%PDF-fake", request_id="req-1")

    async def test_malformed_error_body_maps_to_unavailable(self):
        client = ValidationClient(
            async_client(lambda r: httpx.Response(422, text="no-json")),
            "http://validation:8000",
        )
        with pytest.raises(ValidationUnavailableError):
            await client.validate(b"%PDF-fake", request_id="req-1")

    async def test_error_body_without_error_key_maps_to_unavailable(self):
        client = ValidationClient(
            async_client(lambda r: httpx.Response(422, json={"detail": "x"})),
            "http://validation:8000",
        )
        with pytest.raises(ValidationUnavailableError):
            await client.validate(b"%PDF-fake", request_id="req-1")


class TestExtractClient:
    async def test_success_returns_extraction_result(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/extract"
            assert request.headers["x-request-id"] == "req-3"
            return httpx.Response(
                200, json={"content": "texto extraído", "page_count": 7}
            )

        client = ExtractClient(async_client(handler), "http://extract:8000")
        result = await client.extract(b"%PDF-fake", request_id="req-3")
        assert isinstance(result, ExtractionResult)
        assert result.content == "texto extraído"
        assert result.page_count == 7
        await client.aclose()

    @pytest.mark.parametrize(
        ("status", "payload", "expected"),
        [
            (400, {"detail": "PDF inválido"}, ExtractionFailedError),
            (413, {"detail": "demasiado grande"}, PdfTooLargeError),
            (
                415,
                {"detail": "Content-Type must be application/pdf"},
                UnsupportedMediaTypeError,
            ),
        ],
    )
    async def test_client_errors_map_to_domain(self, status, payload, expected):
        client = ExtractClient(
            async_client(lambda r: httpx.Response(status, json=payload)),
            "http://extract:8000",
        )
        with pytest.raises(expected):
            await client.extract(b"%PDF-fake", request_id="req-1")

    async def test_server_error_maps_to_unavailable(self):
        client = ExtractClient(
            async_client(lambda r: httpx.Response(502, json={"detail": "bad"})),
            "http://extract:8000",
        )
        with pytest.raises(ExtractUnavailableError):
            await client.extract(b"%PDF-fake", request_id="req-1")

    async def test_connect_error_maps_to_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = ExtractClient(async_client(handler), "http://extract:8000")
        with pytest.raises(ExtractUnavailableError):
            await client.extract(b"%PDF-fake", request_id="req-1")

    async def test_timeout_maps_to_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("expired")

        client = ExtractClient(async_client(handler), "http://extract:8000")
        with pytest.raises(ExtractUnavailableError):
            await client.extract(b"%PDF-fake", request_id="req-1")

    async def test_malformed_json_maps_to_unavailable(self):
        client = ExtractClient(
            async_client(lambda r: httpx.Response(200, text="nope")),
            "http://extract:8000",
        )
        with pytest.raises(ExtractUnavailableError):
            await client.extract(b"%PDF-fake", request_id="req-1")

    async def test_malformed_error_body_maps_to_unavailable_detail(self):
        client = ExtractClient(
            async_client(lambda r: httpx.Response(400, text="no-json")),
            "http://extract:8000",
        )
        with pytest.raises(ExtractionFailedError):
            await client.extract(b"%PDF-fake", request_id="req-1")


class TestPersistenceClient:
    RECORD: ClassVar[DocumentRecord] = DocumentRecord(
        checksum="ab" * 32,
        checksum_algorithm="sha256",
        text="Texto extraído del documento.",
        summary="Resumen generado.",
        page_count=3,
        file_size_bytes=1024,
        model="meta/llama-3.1-8b-instruct",
    )

    EXPECTED_PAYLOAD: ClassVar[dict] = {
        "checksum": "ab" * 32,
        "checksum_algorithm": "sha256",
        "text": "Texto extraído del documento.",
        "summary": "Resumen generado.",
        "page_count": 3,
        "file_size_bytes": 1024,
        "model": "meta/llama-3.1-8b-instruct",
    }

    def make_client(self, handler):
        return PersistenceClient(async_client(handler), "http://pdf-persistence:8003")

    async def test_created_201_sends_document_payload(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["request_id"] = request.headers.get("x-request-id")
            seen["content_type"] = request.headers.get("content-type")
            seen["payload"] = json.loads(request.content)
            return httpx.Response(
                201, json={"checksum": "ab" * 32, "created_at": "", "updated_at": ""}
            )

        client = self.make_client(handler)
        await client.save(self.RECORD, request_id="req-5")

        assert seen["path"] == "/documents"
        assert seen["request_id"] == "req-5"
        assert seen["content_type"].startswith("application/json")
        assert seen["payload"] == self.EXPECTED_PAYLOAD
        await client.aclose()

    async def test_idempotent_200_is_also_success(self):
        client = self.make_client(lambda r: httpx.Response(200, json={}))
        await client.save(self.RECORD, request_id="req-5")

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    async def test_server_errors_map_to_unavailable(self, status):
        client = self.make_client(
            lambda r: httpx.Response(
                status, json={"error": {"code": "MONGO_UNAVAILABLE", "message": "x"}}
            )
        )
        with pytest.raises(PersistenceUnavailableError):
            await client.save(self.RECORD, request_id="req-5")

    async def test_conflict_409_maps_to_conflict_with_upstream_message(self):
        client = self.make_client(
            lambda r: httpx.Response(
                409,
                json={
                    "error": {
                        "code": "DOCUMENT_ALREADY_EXISTS",
                        "message": "Ya existe un documento con datos distintos.",
                    }
                },
            )
        )
        with pytest.raises(PersistenceConflictError) as excinfo:
            await client.save(self.RECORD, request_id="req-5")
        assert "datos distintos" in excinfo.value.message

    @pytest.mark.parametrize(
        ("status", "payload"),
        [
            (422, {"error": {"code": "VALIDATION", "message": "checksum inválido"}}),
            (400, {"error": {"code": "BAD", "message": "solicitud inválida"}}),
        ],
    )
    async def test_client_rejections_map_to_rejected(self, status, payload):
        client = self.make_client(lambda r: httpx.Response(status, json=payload))
        with pytest.raises(PersistenceRejectedError):
            await client.save(self.RECORD, request_id="req-5")

    async def test_connect_error_maps_to_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = self.make_client(handler)
        with pytest.raises(PersistenceUnavailableError):
            await client.save(self.RECORD, request_id="req-5")

    async def test_timeout_maps_to_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("expired")

        client = self.make_client(handler)
        with pytest.raises(PersistenceUnavailableError):
            await client.save(self.RECORD, request_id="req-5")

    async def test_unexpected_status_maps_to_rejected(self):
        client = self.make_client(lambda r: httpx.Response(418, json={}))
        with pytest.raises(PersistenceRejectedError):
            await client.save(self.RECORD, request_id="req-5")

    async def test_malformed_server_error_maps_to_unavailable(self):
        client = self.make_client(lambda r: httpx.Response(503, text="no-json"))
        with pytest.raises(PersistenceUnavailableError):
            await client.save(self.RECORD, request_id="req-5")

    async def test_malformed_conflict_body_maps_to_conflict(self):
        client = self.make_client(lambda r: httpx.Response(409, text="no-json"))
        with pytest.raises(PersistenceConflictError):
            await client.save(self.RECORD, request_id="req-5")


class TestLLMClient:
    def make_client(
        self, handler, api_key="test-key", model="meta/llama-3.1-8b-instruct"
    ):
        return LLMClient(
            http=async_client(handler),
            base_url="https://llm.example.com/v1",
            api_key=api_key,
            model=model,
            max_tokens=512,
        )

    async def test_not_configured_raises_without_http_call(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no debe realizarse ninguna llamada HTTP")

        client = self.make_client(handler, api_key="")
        with pytest.raises(LLMNotConfiguredError):
            await client.summarize("prompt")

    async def test_success_returns_summary_and_sends_expected_payload(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("authorization")
            seen["path"] = request.url.path
            import json

            seen["payload"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Resumen del texto."}}]},
            )

        client = self.make_client(handler)
        summary = await client.summarize("prompt de prueba")

        assert summary == "Resumen del texto."
        assert seen["auth"] == "Bearer test-key"
        assert seen["path"] == "/v1/chat/completions"
        assert seen["payload"]["model"] == "meta/llama-3.1-8b-instruct"
        assert seen["payload"]["max_tokens"] == 512
        assert seen["payload"]["messages"][0]["content"] == "prompt de prueba"
        await client.aclose()

    async def test_model_name_property(self):
        client = self.make_client(lambda r: httpx.Response(200, json={}))
        assert client.model_name == "meta/llama-3.1-8b-instruct"

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (401, LLMAuthError),
            (403, LLMAuthError),
            (429, LLMRateLimitError),
            (500, LLMProviderError),
            (502, LLMProviderError),
        ],
    )
    async def test_http_errors_map_to_domain(self, status, expected):
        client = self.make_client(
            lambda r: httpx.Response(status, json={"error": {"message": "x"}})
        )
        with pytest.raises(expected):
            await client.summarize("prompt")

    @pytest.mark.parametrize("status", [302, 404, 418])
    async def test_unexpected_status_maps_to_provider_error(self, status):
        client = self.make_client(lambda r: httpx.Response(status, json={}))
        with pytest.raises(LLMProviderError):
            await client.summarize("prompt")

    async def test_timeout_maps_to_domain_timeout(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("expired")

        client = self.make_client(handler)
        with pytest.raises(LLMTimeoutError):
            await client.summarize("prompt")

    async def test_connect_error_maps_to_provider_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = self.make_client(handler)
        with pytest.raises(LLMProviderError):
            await client.summarize("prompt")

    async def test_invalid_json_maps_to_provider_error(self):
        client = self.make_client(lambda r: httpx.Response(200, text="not-json"))
        with pytest.raises(LLMProviderError):
            await client.summarize("prompt")

    async def test_missing_choices_maps_to_provider_error(self):
        client = self.make_client(lambda r: httpx.Response(200, json={"ok": True}))
        with pytest.raises(LLMProviderError):
            await client.summarize("prompt")

    async def test_empty_summary_maps_to_provider_error(self):
        client = self.make_client(
            lambda r: httpx.Response(
                200, json={"choices": [{"message": {"content": ""}}]}
            )
        )
        with pytest.raises(LLMProviderError):
            await client.summarize("prompt")

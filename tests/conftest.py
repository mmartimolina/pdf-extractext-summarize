"""Fixtures y utilidades compartidas de las pruebas."""

from dataclasses import dataclass, field

import pytest

from pdf_summarize.config import Settings
from pdf_summarize.domain.models import ExtractionResult, ValidationReport


def make_settings(**overrides) -> Settings:
    """Construye ``Settings`` con valores por defecto y overrides."""
    defaults = dict(
        max_pdf_size_bytes=20 * 1024 * 1024,
        validation_service_url="http://pdf-validation:8000",
        extract_service_url="http://extract:8000",
        persistence_service_url="http://pdf-persistence:8003",
        llm_base_url="https://integrate.api.nvidia.com/v1",
        llm_api_key="test-key",
        llm_model="meta/llama-3.1-8b-instruct",
        llm_timeout_seconds=60.0,
        llm_max_tokens=1000,
        upstream_timeout_seconds=30.0,
        log_level="INFO",
    )
    defaults.update(overrides)
    return Settings(**defaults)


@dataclass
class FakeValidator:
    report: ValidationReport = field(
        default_factory=lambda: ValidationReport(
            file_size_bytes=512, checksum="cafebabe", checksum_algorithm="sha256"
        )
    )
    error: Exception | None = None
    calls: list = field(default_factory=list)

    async def validate(self, pdf_bytes, request_id):
        self.calls.append((pdf_bytes, request_id))
        if self.error:
            raise self.error
        return self.report

    async def aclose(self):
        self.closed = True


@dataclass
class FakeExtractor:
    result: ExtractionResult = field(
        default_factory=lambda: ExtractionResult(
            content="Texto extraído suficientemente largo. " * 3, page_count=2
        )
    )
    error: Exception | None = None
    calls: list = field(default_factory=list)

    async def extract(self, pdf_bytes, request_id):
        self.calls.append((pdf_bytes, request_id))
        if self.error:
            raise self.error
        return self.result

    async def aclose(self):
        self.closed = True


@dataclass
class FakeSummarizer:
    summary: str = "Resumen del documento."
    error: Exception | None = None
    model_name: str = "meta/llama-3.1-8b-instruct"
    prompts: list = field(default_factory=list)

    async def summarize(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.summary

    async def aclose(self):
        self.closed = True


@dataclass
class FakePersister:
    error: Exception | None = None
    calls: list = field(default_factory=list)

    async def save(self, record, request_id):
        self.calls.append((record, request_id))
        if self.error:
            raise self.error

    async def aclose(self):
        self.closed = True


@dataclass
class FakeContainer:
    """Sustituye al contenedor real de infraestructura en las pruebas."""

    validation_client: FakeValidator = field(default_factory=FakeValidator)
    extract_client: FakeExtractor = field(default_factory=FakeExtractor)
    llm_client: FakeSummarizer = field(default_factory=FakeSummarizer)
    persistence_client: FakePersister = field(default_factory=FakePersister)
    use_case: object | None = None
    closed: bool = False

    async def aclose(self):
        self.closed = True


@pytest.fixture
def fake_container() -> FakeContainer:
    return FakeContainer()

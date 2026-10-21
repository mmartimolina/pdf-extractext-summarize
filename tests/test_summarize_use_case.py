"""Pruebas del caso de uso de sumarización con dependencias falsas."""

import pytest

from pdf_summarize.domain.errors import (
    EmptyPdfError,
    ExtractUnavailableError,
    LLMAuthError,
    LLMNotConfiguredError,
    NoUsefulTextError,
    PersistenceUnavailableError,
    ValidationRejectedError,
    ValidationUnavailableError,
)
from pdf_summarize.domain.models import ExtractionResult, ValidationReport
from pdf_summarize.service.summarize_use_case import SummarizeUseCase

VALIDATION_OK = ValidationReport(
    file_size_bytes=2048, checksum="deadbeef", checksum_algorithm="sha256"
)
EXTRACTION_OK = ExtractionResult(
    content="Texto largo del documento. " * 5, page_count=4
)


class FakeValidationClient:
    def __init__(self, report=None, error=None):
        self._report = report
        self._error = error
        self.calls = []

    async def validate(self, pdf_bytes, request_id):
        self.calls.append((pdf_bytes, request_id))
        if self._error:
            raise self._error
        return self._report


class FakeExtractClient:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls = []

    async def extract(self, pdf_bytes, request_id):
        self.calls.append((pdf_bytes, request_id))
        if self._error:
            raise self._error
        return self._result


class FakeLLMClient:
    model_name = "meta/llama-3.1-8b-instruct"

    def __init__(self, summary="Resumen generado.", error=None):
        self._summary = summary
        self._error = error
        self.prompts = []

    async def summarize(self, prompt):
        self.prompts.append(prompt)
        if self._error:
            raise self._error
        return self._summary


class FakePersistenceClient:
    def __init__(self, error=None):
        self._error = error
        self.calls = []

    async def save(self, record, request_id):
        self.calls.append((record, request_id))
        if self._error:
            raise self._error


def build_use_case(
    validation=None, extract=None, llm=None, persistence=None, min_length=50
):
    return SummarizeUseCase(
        validation_client=validation or FakeValidationClient(VALIDATION_OK),
        extract_client=extract or FakeExtractClient(EXTRACTION_OK),
        llm_client=llm or FakeLLMClient(),
        persistence_client=persistence or FakePersistenceClient(),
        min_text_length=min_length,
    )


class TestHappyPath:
    async def test_returns_summary_with_metadata(self):
        use_case = build_use_case()
        result = await use_case.execute(b"%PDF-fake", request_id="req-1")
        assert result.summary == "Resumen generado."
        assert result.page_count == 4
        assert result.file_size_bytes == 2048
        assert result.checksum == "deadbeef"
        assert result.checksum_algorithm == "sha256"
        assert result.model == "meta/llama-3.1-8b-instruct"

    async def test_receives_the_extracted_text_in_the_prompt(self):
        llm = FakeLLMClient()
        use_case = build_use_case(llm=llm)
        await use_case.execute(b"%PDF-fake", request_id="req-1")
        assert len(llm.prompts) == 1
        assert EXTRACTION_OK.content in llm.prompts[0]

    async def test_propagates_request_id_to_upstream_calls(self):
        validation = FakeValidationClient(VALIDATION_OK)
        extract = FakeExtractClient(EXTRACTION_OK)
        use_case = build_use_case(validation=validation, extract=extract)
        await use_case.execute(b"%PDF-fake", request_id="req-77")
        assert validation.calls[0][1] == "req-77"
        assert extract.calls[0][1] == "req-77"


class TestValidationStep:
    async def test_validation_rejection_propagates(self):
        use_case = build_use_case(
            validation=FakeValidationClient(
                error=ValidationRejectedError("INVALID_PDF", "PDF inválido.")
            )
        )
        with pytest.raises(ValidationRejectedError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")

    async def test_validation_unavailable_propagates(self):
        use_case = build_use_case(
            validation=FakeValidationClient(error=ValidationUnavailableError("timeout"))
        )
        with pytest.raises(ValidationUnavailableError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")

    async def test_validation_not_called_twice(self):
        validation = FakeValidationClient(VALIDATION_OK)
        use_case = build_use_case(validation=validation)
        await use_case.execute(b"%PDF-fake", request_id="req-1")
        assert len(validation.calls) == 1


class TestExtractionStep:
    async def test_extract_failure_propagates(self):
        use_case = build_use_case(
            extract=FakeExtractClient(error=ExtractUnavailableError("down"))
        )
        with pytest.raises(ExtractUnavailableError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")

    async def test_llm_not_called_when_extract_fails(self):
        llm = FakeLLMClient()
        use_case = build_use_case(
            extract=FakeExtractClient(error=ExtractUnavailableError("down")),
            llm=llm,
        )
        with pytest.raises(ExtractUnavailableError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")
        assert llm.prompts == []


class TestUsefulTextCheck:
    async def test_empty_text_raises_no_useful_text(self):
        use_case = build_use_case(
            extract=FakeExtractClient(ExtractionResult(content="", page_count=3))
        )
        with pytest.raises(NoUsefulTextError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")

    async def test_whitespace_only_text_raises_no_useful_text(self):
        use_case = build_use_case(
            extract=FakeExtractClient(
                ExtractionResult(content="   \n\t  ", page_count=3)
            )
        )
        with pytest.raises(NoUsefulTextError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")

    async def test_text_below_minimum_raises_no_useful_text(self):
        use_case = build_use_case(
            extract=FakeExtractClient(
                ExtractionResult(content="texto corto", page_count=1)
            ),
            min_length=50,
        )
        with pytest.raises(NoUsefulTextError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")

    async def test_text_at_minimum_is_accepted(self):
        use_case = build_use_case(
            extract=FakeExtractClient(ExtractionResult(content="x" * 50, page_count=1)),
            min_length=50,
        )
        result = await use_case.execute(b"%PDF-fake", request_id="req-1")
        assert result.summary == "Resumen generado."


class TestPersistenceStep:
    async def test_document_is_persisted_after_successful_summary(self):
        persistence = FakePersistenceClient()
        use_case = build_use_case(persistence=persistence)
        result = await use_case.execute(b"%PDF-fake", request_id="req-1")

        assert len(persistence.calls) == 1
        record, request_id = persistence.calls[0]
        assert record.checksum == "deadbeef"
        assert record.checksum_algorithm == "sha256"
        assert record.text == EXTRACTION_OK.content
        assert record.summary == result.summary
        assert record.page_count == 4
        assert record.file_size_bytes == 2048
        assert record.model == "meta/llama-3.1-8b-instruct"
        assert request_id == "req-1"

    async def test_persistence_unavailable_propagates(self):
        persistence = FakePersistenceClient(
            error=PersistenceUnavailableError("connection refused")
        )
        use_case = build_use_case(persistence=persistence)
        with pytest.raises(PersistenceUnavailableError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")

    async def test_persistence_fails_once_without_retry(self):
        persistence = FakePersistenceClient(
            error=PersistenceUnavailableError("connection refused")
        )
        use_case = build_use_case(persistence=persistence)
        with pytest.raises(PersistenceUnavailableError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")
        assert len(persistence.calls) == 1

    async def test_persistence_not_called_when_llm_fails(self):
        persistence = FakePersistenceClient()
        use_case = build_use_case(
            llm=FakeLLMClient(error=LLMAuthError("401")),
            persistence=persistence,
        )
        with pytest.raises(LLMAuthError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")
        assert persistence.calls == []

    async def test_persistence_not_called_when_validation_fails(self):
        persistence = FakePersistenceClient()
        use_case = build_use_case(
            validation=FakeValidationClient(
                error=ValidationRejectedError("INVALID_PDF", "PDF inválido.")
            ),
            persistence=persistence,
        )
        with pytest.raises(ValidationRejectedError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")
        assert persistence.calls == []

    async def test_persistence_not_called_when_extract_fails(self):
        persistence = FakePersistenceClient()
        use_case = build_use_case(
            extract=FakeExtractClient(error=ExtractUnavailableError("down")),
            persistence=persistence,
        )
        with pytest.raises(ExtractUnavailableError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")
        assert persistence.calls == []

    async def test_persistence_not_called_when_no_useful_text(self):
        persistence = FakePersistenceClient()
        use_case = build_use_case(
            extract=FakeExtractClient(ExtractionResult(content="", page_count=3)),
            persistence=persistence,
        )
        with pytest.raises(NoUsefulTextError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")
        assert persistence.calls == []


class TestLLMStep:
    async def test_llm_auth_error_propagates(self):
        use_case = build_use_case(llm=FakeLLMClient(error=LLMAuthError("401")))
        with pytest.raises(LLMAuthError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")

    async def test_llm_not_configured_propagates(self):
        use_case = build_use_case(llm=FakeLLMClient(error=LLMNotConfiguredError()))
        with pytest.raises(LLMNotConfiguredError):
            await use_case.execute(b"%PDF-fake", request_id="req-1")

    async def test_empty_input_is_rejected_before_upstream_calls(self):
        validation = FakeValidationClient(VALIDATION_OK)
        use_case = build_use_case(validation=validation)
        with pytest.raises(EmptyPdfError):
            await use_case.execute(b"", request_id="req-1")
        assert validation.calls == []

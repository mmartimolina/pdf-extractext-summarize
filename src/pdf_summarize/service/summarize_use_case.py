"""Orquestador SAGA del flujo de sumarización de un PDF."""

import logging

from pdf_summarize.domain.errors import EmptyPdfError, NoUsefulTextError
from pdf_summarize.domain.models import DocumentRecord, SummaryResult
from pdf_summarize.domain.ports import Extractor, Persister, Summarizer, Validator
from pdf_summarize.service.prompts import build_summary_prompt

logger = logging.getLogger("pdf_summarize.summarize")
DEFAULT_MIN_TEXT_LENGTH = 50


class SummarizeUseCase:
    """Coordina pasos y compensaciones de la SAGA.

    SAGA: Validation → reserva PENDING → Extract → LLM → confirmación
    COMPLETED. Si falla cualquier paso posterior a la reserva, se ejecuta
    la compensación mediante eliminación lógica en Persistence.
    """

    def __init__(
        self,
        validation_client: Validator,
        extract_client: Extractor,
        llm_client: Summarizer,
        persistence_client: Persister,
        min_text_length: int = DEFAULT_MIN_TEXT_LENGTH,
    ) -> None:
        self._validation = validation_client
        self._extract = extract_client
        self._llm = llm_client
        self._persistence = persistence_client
        self._min_text_length = min_text_length

    async def execute(self, pdf_bytes: bytes, request_id: str) -> SummaryResult:
        if not pdf_bytes:
            raise EmptyPdfError()

        checksum: str | None = None
        reservation_started = False
        try:
            report = await self._validation.validate(pdf_bytes, request_id)
            checksum = report.checksum

            # Paso con efecto persistente: reserva idempotente PENDING.
            await self._persistence.begin(
                checksum, report.checksum_algorithm, request_id
            )
            reservation_started = True

            extraction = await self._extract.extract(pdf_bytes, request_id)
            if len(extraction.content.strip()) < self._min_text_length:
                raise NoUsefulTextError()

            summary = await self._llm.summarize(
                build_summary_prompt(extraction.content)
            )
            result = SummaryResult(
                summary=summary,
                page_count=extraction.page_count,
                file_size_bytes=report.file_size_bytes,
                checksum=report.checksum,
                checksum_algorithm=report.checksum_algorithm,
                model=self._llm.model_name,
            )
            record = DocumentRecord(
                checksum=result.checksum,
                checksum_algorithm=result.checksum_algorithm,
                text=extraction.content,
                summary=result.summary,
                page_count=result.page_count,
                file_size_bytes=result.file_size_bytes,
                model=result.model,
            )

            # Confirmación: PENDING → COMPLETED.
            await self._persistence.save(record, request_id)
            logger.info(
                "saga_completed request_id=%s checksum=%s", request_id, checksum
            )
            return result
        except Exception:
            if reservation_started and checksum is not None:
                try:
                    await self._persistence.compensate(checksum, request_id)
                    logger.warning(
                        "saga_compensated request_id=%s checksum=%s",
                        request_id, checksum,
                    )
                except Exception:
                    # Se conserva el error original; PENDING queda identificable
                    # para una reconciliación operativa posterior.
                    logger.exception(
                        "saga_compensation_failed request_id=%s checksum=%s",
                        request_id, checksum,
                    )
            raise

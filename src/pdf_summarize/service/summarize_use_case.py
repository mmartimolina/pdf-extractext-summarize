"""Caso de uso: coordina Validation, Extract, el modelo IA y Persistence."""

import logging

from pdf_summarize.domain.errors import EmptyPdfError, NoUsefulTextError
from pdf_summarize.domain.models import DocumentRecord, SummaryResult
from pdf_summarize.domain.ports import Extractor, Persister, Summarizer, Validator
from pdf_summarize.service.prompts import build_summary_prompt

logger = logging.getLogger("pdf_summarize.summarize")

#: Longitud mínima (en caracteres) para considerar el texto útil.
DEFAULT_MIN_TEXT_LENGTH = 50


class SummarizeUseCase:
    """Orquesta el flujo completo de sumarización de un PDF.

    No duplica la lógica de validación, extracción ni persistencia:
    delega en los puertos de infraestructura y aplica únicamente las
    reglas propias (texto útil, construcción del prompt, composición
    del resultado y registro del documento una vez resumido).
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
        """Ejecuta el flujo de sumarización.

        Args:
            pdf_bytes: contenido binario del PDF.
            request_id: identificador correlacionable de la solicitud.

        Returns:
            SummaryResult con el resumen y los metadatos verificados.

        Raises:
            EmptyPdfError: si la entrada está vacía.
            NoUsefulTextError: si la extracción no produjo texto útil.
            Errores de dominio propagados de las dependencias.
        """
        if not pdf_bytes:
            raise EmptyPdfError()

        report = await self._validation.validate(pdf_bytes, request_id)
        extraction = await self._extract.extract(pdf_bytes, request_id)

        if len(extraction.content.strip()) < self._min_text_length:
            raise NoUsefulTextError()

        prompt = build_summary_prompt(extraction.content)
        summary = await self._llm.summarize(prompt)

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
        await self._persistence.save(record, request_id)

        logger.info(
            "summarize_ok request_id=%s pages=%d size=%d checksum=%s",
            request_id,
            extraction.page_count,
            report.file_size_bytes,
            report.checksum,
        )
        return result

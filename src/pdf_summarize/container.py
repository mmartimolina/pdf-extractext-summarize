"""Contenedor de dependencias de infraestructura.

Construye los clientes HTTP reales a partir de la configuración y los
cierra de forma ordenada durante el apagado. Las pruebas sustituyen este
contenedor por dobles con la misma forma.
"""

import httpx

from pdf_summarize.config import Settings
from pdf_summarize.domain.ports import Extractor, Persister, Summarizer, Validator
from pdf_summarize.infrastructure.extract_client import ExtractClient
from pdf_summarize.infrastructure.llm_client import LLMClient
from pdf_summarize.infrastructure.persistence_client import PersistenceClient
from pdf_summarize.infrastructure.validation_client import ValidationClient
from pdf_summarize.service.summarize_use_case import SummarizeUseCase


class Container:
    """Agrupa las dependencias externas del servicio."""

    def __init__(
        self,
        validation_client: Validator,
        extract_client: Extractor,
        llm_client: Summarizer,
        persistence_client: Persister,
        use_case: SummarizeUseCase,
    ) -> None:
        self.validation_client = validation_client
        self.extract_client = extract_client
        self.llm_client = llm_client
        self.persistence_client = persistence_client
        self.use_case = use_case
        self.validation_client_closed = False
        self.extract_client_closed = False
        self.llm_client_closed = False
        self.persistence_client_closed = False

    @classmethod
    def build(cls, settings: Settings) -> "Container":
        """Construye los clientes reales con timeouts explícitos."""
        upstream_timeout = httpx.Timeout(settings.upstream_timeout_seconds)
        llm_timeout = httpx.Timeout(settings.llm_timeout_seconds)

        validation_client = ValidationClient(
            httpx.AsyncClient(timeout=upstream_timeout),
            settings.validation_service_url,
        )
        extract_client = ExtractClient(
            httpx.AsyncClient(timeout=upstream_timeout),
            settings.extract_service_url,
        )
        llm_client = LLMClient(
            httpx.AsyncClient(timeout=llm_timeout),
            settings.llm_base_url,
            settings.llm_api_key,
            settings.llm_model,
            settings.llm_max_tokens,
        )
        persistence_client = PersistenceClient(
            httpx.AsyncClient(timeout=upstream_timeout),
            settings.persistence_service_url,
        )
        return cls(
            validation_client=validation_client,
            extract_client=extract_client,
            llm_client=llm_client,
            persistence_client=persistence_client,
            use_case=SummarizeUseCase(
                validation_client=validation_client,
                extract_client=extract_client,
                llm_client=llm_client,
                persistence_client=persistence_client,
            ),
        )

    async def aclose(self) -> None:
        """Cierra los clientes HTTP de forma ordenada."""
        for name in (
            "validation_client",
            "extract_client",
            "llm_client",
            "persistence_client",
        ):
            client = getattr(self, name)
            closer = getattr(client, "aclose", None)
            if closer is not None:
                await closer()
            setattr(self, f"{name}_closed", True)

"""Cliente del proveedor de modelos de lenguaje (API compatible con OpenAI).

El proveedor concreto (por defecto la API de NVIDIA, usada en el proyecto
original) se configura mediante variables de entorno y es intercambiable
por cualquier API compatible con ``chat/completions``.
"""

import logging

import httpx

from pdf_summarize.domain.errors import (
    LLMAuthError,
    LLMNotConfiguredError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger("pdf_summarize.llm_client")


class LLMClient:
    """Adaptador del puerto ``Summarizer`` sobre una API OpenAI-compatible."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        model: str,
        max_tokens: int,
    ) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens

    @property
    def model_name(self) -> str:
        """Identificador del modelo configurado."""
        return self._model

    async def summarize(self, prompt: str) -> str:
        """Genera el resumen a partir del prompt.

        Raises:
            LLMNotConfiguredError: si no hay credenciales configuradas;
                en ese caso nunca se realiza la llamada HTTP.
        """
        if not self._api_key:
            raise LLMNotConfiguredError()

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": self._max_tokens,
        }
        try:
            response = await self._http.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.TimeoutException as exc:
            logger.warning("llm_timeout model=%s", self._model)
            raise LLMTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            logger.warning("llm_call_failed model=%s", self._model)
            raise LLMProviderError(str(exc)) from exc

        if response.status_code in (401, 403):
            logger.warning("llm_auth_rejected status=%d", response.status_code)
            raise LLMAuthError(f"estado {response.status_code}")
        if response.status_code == 429:
            logger.warning("llm_rate_limited")
            raise LLMRateLimitError("límite de uso alcanzado")
        if response.status_code >= 500:
            logger.warning("llm_provider_error status=%d", response.status_code)
            raise LLMProviderError(f"estado {response.status_code}")
        if response.status_code != 200:
            logger.warning("llm_unexpected_status status=%d", response.status_code)
            raise LLMProviderError(f"estado {response.status_code}")

        return self._parse_summary(response)

    async def aclose(self) -> None:
        """Cierra el cliente HTTP subyacente."""
        await self._http.aclose()

    @staticmethod
    def _parse_summary(response: httpx.Response) -> str:
        """Extrae el texto del resumen de una respuesta 200 válida."""
        try:
            summary = str(response.json()["choices"][0]["message"]["content"])
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            logger.warning("llm_invalid_payload")
            raise LLMProviderError("respuesta sin choices válidos") from exc
        if not summary.strip():
            logger.warning("llm_empty_summary")
            raise LLMProviderError("el modelo devolvió un resumen vacío")
        return summary

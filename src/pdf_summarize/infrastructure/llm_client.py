"""Cliente del proveedor de modelos de lenguaje (API compatible con OpenAI).

El proveedor concreto (por defecto la API de NVIDIA, usada en el proyecto
original) se configura mediante variables de entorno y es intercambiable
por cualquier API compatible con ``chat/completions``.
"""

import hashlib
import logging
import os
import time
from collections import OrderedDict

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
        self._cache_ttl = float(os.environ.get("LLM_CACHE_TTL_SECONDS", "300"))
        self._cache_max_entries = int(os.environ.get("LLM_CACHE_MAX_ENTRIES", "256"))
        if self._cache_ttl < 0 or self._cache_max_entries < 1:
            raise ValueError("La configuración de caché LLM no es válida")
        self._summary_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()

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

        cache_key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        cached = self._summary_cache.get(cache_key)
        now = time.monotonic()
        if cached is not None:
            expires_at, cached_summary = cached
            if expires_at > now:
                self._summary_cache.move_to_end(cache_key)
                logger.info("llm_cache_hit")
                return cached_summary
            self._summary_cache.pop(cache_key, None)

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

        summary = self._parse_summary(response)
        if self._cache_ttl > 0:
            self._summary_cache[cache_key] = (time.monotonic() + self._cache_ttl, summary)
            self._summary_cache.move_to_end(cache_key)
            while len(self._summary_cache) > self._cache_max_entries:
                self._summary_cache.popitem(last=False)
        return summary

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

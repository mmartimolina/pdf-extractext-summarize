"""Pruebas de configuración por variables de entorno."""

import pytest

from pdf_summarize.config import Settings


class TestDefaults:
    def test_settings_defaults_when_env_empty(self, monkeypatch):
        for name in (
            "MAX_PDF_SIZE_MIB",
            "VALIDATION_SERVICE_URL",
            "EXTRACT_SERVICE_URL",
            "PERSISTENCE_SERVICE_URL",
            "LLM_BASE_URL",
            "LLM_API_KEY",
            "LLM_MODEL",
            "LLM_TIMEOUT_SECONDS",
            "LLM_MAX_TOKENS",
            "UPSTREAM_TIMEOUT_SECONDS",
            "LOG_LEVEL",
        ):
            monkeypatch.delenv(name, raising=False)

        settings = Settings.from_env()

        assert settings.max_pdf_size_bytes == 20 * 1024 * 1024
        assert settings.validation_service_url == "http://pdf-validation:8000"
        assert settings.extract_service_url == "http://extract:8000"
        assert settings.persistence_service_url == "http://pdf-persistence:8003"
        assert settings.llm_base_url == "https://integrate.api.nvidia.com/v1"
        assert settings.llm_api_key == ""
        assert settings.llm_model == "meta/llama-3.1-8b-instruct"
        assert settings.llm_timeout_seconds == 60.0
        assert settings.llm_max_tokens == 1000
        assert settings.upstream_timeout_seconds == 30.0
        assert settings.log_level == "INFO"

    def test_reads_all_values_from_environment(self, monkeypatch):
        env = {
            "MAX_PDF_SIZE_MIB": "5",
            "VALIDATION_SERVICE_URL": "http://validation:9000",
            "EXTRACT_SERVICE_URL": "http://extractor:9000",
            "PERSISTENCE_SERVICE_URL": "http://pdf-persistence:9003",
            "LLM_BASE_URL": "https://llm.example.com/v1",
            "LLM_API_KEY": "secret-key",
            "LLM_MODEL": "other/model",
            "LLM_TIMEOUT_SECONDS": "12.5",
            "LLM_MAX_TOKENS": "256",
            "UPSTREAM_TIMEOUT_SECONDS": "7",
            "LOG_LEVEL": "DEBUG",
        }
        for name, value in env.items():
            monkeypatch.setenv(name, value)

        settings = Settings.from_env()

        assert settings.max_pdf_size_bytes == 5 * 1024 * 1024
        assert settings.validation_service_url == "http://validation:9000"
        assert settings.extract_service_url == "http://extractor:9000"
        assert settings.persistence_service_url == "http://pdf-persistence:9003"
        assert settings.llm_base_url == "https://llm.example.com/v1"
        assert settings.llm_api_key == "secret-key"
        assert settings.llm_model == "other/model"
        assert settings.llm_timeout_seconds == 12.5
        assert settings.llm_max_tokens == 256
        assert settings.upstream_timeout_seconds == 7.0
        assert settings.log_level == "DEBUG"

    def test_trims_trailing_slash_from_service_urls(self, monkeypatch):
        monkeypatch.setenv("VALIDATION_SERVICE_URL", "http://validation:8000/")
        monkeypatch.setenv("EXTRACT_SERVICE_URL", "http://extract:8000/")
        monkeypatch.setenv("PERSISTENCE_SERVICE_URL", "http://pdf-persistence:8003/")
        monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com/v1/")
        monkeypatch.delenv("MAX_PDF_SIZE_MIB", raising=False)

        settings = Settings.from_env()

        assert settings.validation_service_url == "http://validation:8000"
        assert settings.extract_service_url == "http://extract:8000"
        assert settings.persistence_service_url == "http://pdf-persistence:8003"
        assert settings.llm_base_url == "https://llm.example.com/v1"


class TestValidation:
    def test_invalid_max_pdf_size_mib(self, monkeypatch):
        monkeypatch.setenv("MAX_PDF_SIZE_MIB", "abc")
        with pytest.raises(ValueError, match="MAX_PDF_SIZE_MIB"):
            Settings.from_env()

    def test_non_positive_max_pdf_size_mib(self, monkeypatch):
        monkeypatch.setenv("MAX_PDF_SIZE_MIB", "0")
        with pytest.raises(ValueError, match="MAX_PDF_SIZE_MIB"):
            Settings.from_env()

    def test_invalid_llm_timeout_seconds(self, monkeypatch):
        monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "not-a-number")
        monkeypatch.delenv("MAX_PDF_SIZE_MIB", raising=False)
        with pytest.raises(ValueError, match="LLM_TIMEOUT_SECONDS"):
            Settings.from_env()

    def test_non_positive_llm_max_tokens(self, monkeypatch):
        monkeypatch.setenv("LLM_MAX_TOKENS", "0")
        monkeypatch.delenv("MAX_PDF_SIZE_MIB", raising=False)
        with pytest.raises(ValueError, match="LLM_MAX_TOKENS"):
            Settings.from_env()

    def test_invalid_upstream_timeout_seconds(self, monkeypatch):
        monkeypatch.setenv("UPSTREAM_TIMEOUT_SECONDS", "-1")
        monkeypatch.delenv("MAX_PDF_SIZE_MIB", raising=False)
        with pytest.raises(ValueError, match="UPSTREAM_TIMEOUT_SECONDS"):
            Settings.from_env()


class TestLlmAvailability:
    def test_llm_configured_false_when_api_key_missing(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "")
        monkeypatch.delenv("MAX_PDF_SIZE_MIB", raising=False)
        settings = Settings.from_env()
        assert settings.llm_configured() is False

    def test_llm_configured_true_when_api_key_present(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "some-key")
        monkeypatch.delenv("MAX_PDF_SIZE_MIB", raising=False)
        settings = Settings.from_env()
        assert settings.llm_configured() is True

"""Pruebas de la configuración de logs y del punto de entrada."""

import importlib
import json
import logging

from pdf_summarize.logging_config import (
    JsonFormatter,
    configure_logging,
    log_level_from_name,
)


class TestJsonFormatter:
    def test_format_produces_single_line_json(self):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="mensaje %s",
            args=("con argumento",),
            exc_info=None,
        )
        line = JsonFormatter().format(record)
        payload = json.loads(line)
        assert payload["level"] == "INFO"
        assert payload["logger"] == "test"
        assert payload["message"] == "mensaje con argumento"
        assert "timestamp" in payload
        assert "\n" not in line

    def test_format_includes_exception_when_present(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="falló",
                args=(),
                exc_info=sys.exc_info(),
            )
        payload = json.loads(JsonFormatter().format(record))
        assert "ValueError" in payload["exception"]


class TestConfigureLogging:
    def test_sets_root_handler_and_level(self):
        configure_logging(logging.WARNING)
        root = logging.getLogger()
        try:
            assert root.level == logging.WARNING
            assert any(isinstance(h.formatter, JsonFormatter) for h in root.handlers)
        finally:
            configure_logging(logging.NOTSET)

    def test_log_level_from_name(self):
        assert log_level_from_name("INFO") == logging.INFO
        assert log_level_from_name("debug") == logging.DEBUG
        assert log_level_from_name("NO_EXISTE") == logging.INFO


class TestMainEntryPoint:
    def test_importing_main_builds_a_fastapi_app(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        import pdf_summarize.main as main_module

        module = importlib.reload(main_module)
        from fastapi import FastAPI

        assert isinstance(module.app, FastAPI)

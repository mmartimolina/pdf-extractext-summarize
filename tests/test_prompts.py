"""Pruebas de la construcción del prompt de sumarización."""

from pdf_summarize.service.prompts import build_summary_prompt


class TestBuildSummaryPrompt:
    def test_prompt_contains_the_document_text(self):
        text = "Este es el texto del documento."
        prompt = build_summary_prompt(text)
        assert text in prompt

    def test_prompt_preserves_source_language_by_default(self):
        prompt = build_summary_prompt("Texto cualquiera.")
        assert "idioma" in prompt.lower()

    def test_prompt_bounds_summary_length(self):
        prompt = build_summary_prompt("Texto.")
        assert "20" in prompt

    def test_prompt_does_not_duplicate_text(self):
        text = "Contenido único del documento."
        prompt = build_summary_prompt(text)
        assert prompt.count(text) == 1

# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.11.3 AS uv

FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=uv /uv /usr/local/bin/uv

# Instalación reproducible de dependencias desde pyproject.toml y uv.lock.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src

RUN groupadd --system app && useradd --system --gid app app \
    && chown -R app:app /app
USER app

EXPOSE 8000

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4)"]

# El mismo artefacto se ejecuta en desarrollo y producción (12-Factor).
CMD ["python", "-m", "uvicorn", "pdf_summarize.main:app", "--host", "0.0.0.0", "--port", "8000"]

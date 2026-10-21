"""Fábrica de la aplicación FastAPI del microservicio de sumarización."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pdf_summarize.api.error_handlers import register_exception_handlers
from pdf_summarize.api.middleware import (
    ObservabilityMiddleware,
    RequestIdMiddleware,
)
from pdf_summarize.api.routes import router
from pdf_summarize.config import Settings
from pdf_summarize.container import Container

logger = logging.getLogger("pdf_summarize.app")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Crea y destruye las dependencias externas de la aplicación."""
    container: Container = app.state.container
    logger.info("startup")
    yield
    await container.aclose()
    logger.info("shutdown")


def create_app(
    settings: Settings | None = None,
    container: Container | None = None,
) -> FastAPI:
    """Construye la aplicación FastAPI.

    Args:
        settings: configuración explícita; si se omite se lee del entorno.
        container: contenedor de dependencias explícito para pruebas;
            si se omite se construye uno real a partir de la configuración.
    """
    if settings is None:
        settings = Settings.from_env()
    if container is None:
        container = Container.build(settings)

    app = FastAPI(
        title="pdf-summarize",
        summary="Microservicio de sumarización de texto extraído de PDF.",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.container = container
    app.include_router(router)
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    return app

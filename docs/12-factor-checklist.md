# Checklist Twelve-Factor App — pdf-summarize

Cada factor indica la implementación concreta y su evidencia verificable.
Nada se marca como cumplido por estar solo mencionado en documentación.

## 1. Codebase — Cumplido

Un repositorio Git con el código versionado y desplegable. El servicio se
despliega como una imagen Docker construida desde el propio repositorio.
Evidencia: repositorio `pdf-extractext-summarize`; `Dockerfile` + `docker
compose build` verificado.

## 2. Dependencies — Cumplido

Dependencias declaradas en `pyproject.toml` y bloqueadas en `uv.lock`.
Instalación reproducible con `uv sync --frozen` (Docker) y `uv sync` (dev).
Sin instalación global ni dependencias sin justificar: runtime =
`fastapi`, `httpx`, `prometheus-client`, `uvicorn`; dev = `pytest`,
`pytest-asyncio`, `pytest-cov`, `ruff`.
Evidencia: `pyproject.toml`, `uv.lock`, `Dockerfile`.

## 3. Config — Cumplido

Toda la configuración vive en variables de entorno
(`src/pdf_summarize/config.py::Settings.from_env`): URLs de Validation,
Extract y Persistence, credenciales y parámetros del proveedor de IA,
tamaño máximo, timeouts y nivel de log. Los secretos (`LLM_API_KEY`)
nunca se escriben en
el repositorio: `.env` está en `.gitignore` y en `.dockerignore`;
`.env.example` documenta cada variable con valores ilustrativos.
Evidencia: `config.py`, `.env.example`, exclusiones verificadas en Git.

## 4. Backing services — Cumplido

Validation, Extract, Persistence y el proveedor de IA se tratan como
recursos adjuntos intercambiables: `domain/ports.py` define los puertos y
`infrastructure/` los adaptadores HTTP; cambiar URLs o proveedor no
requiere tocar lógica de negocio (el modelo se configura con
`LLM_MODEL`/`LLM_BASE_URL`). Sin estado local persistente que acople el
servicio a una base de datos: Persistence se consume por HTTP y nunca se
conecta Summarize directamente a MongoDB.
Evidencia: `ports.py`, `container.py::Container.build`, pruebas con dobles.

## 5. Build, release, run — Cumplido

La imagen se construye a partir del lockfile (`uv sync --frozen --no-dev`)
y el mismo artefacto se ejecuta en desarrollo y producción; la
configuración se inyecta en ejecución mediante entorno, sin cambiar el
binario.
Evidencia: `Dockerfile`, `docker-compose.yml`,
`docker-compose.ecosystem.yml` (misma imagen, distinta configuración).

## 6. Processes — Cumplido

El proceso es sin estado: no almacena datos de negocio en memoria ni en
disco; cada solicitud es autosuficiente y las respuestas se derivan de
las dependencias externas en el momento.
Evidencia: no existe almacenamiento local en `src/`; `POST /summarize`
no reutiliza estado entre solicitudes (cubierto por pruebas).

## 7. Port binding — Cumplido

La API es autocontenida y expone su puerto HTTP mediante uvicorn
(`0.0.0.0:8000`); el enrutamiento la publica (`${PORT:-8000}:8000`).
Evidencia: `main.py`, `Dockerfile` (`EXPOSE 8000`, CMD uvicorn).

## 8. Concurrency — Cumplido

Servidor asíncrono (uvicorn + FastAPI) y cliente HTTP asíncrono (httpx):
varias solicitudes se atienden concurrentemente sin bloquear el event
loop; la extracción de PDF pesada ocurre en el servicio Extract, no aquí.
Evidencia: `async def` en toda la cadena de solicitudes; middlewares no
bloqueantes; sin I/O síncrono en el manejo de solicitudes.

## 9. Disposability — Cumplido

Inicio rápido (solo lee entorno y abre clientes) y apagado ordenado: el
`lifespan` cierra los clientes HTTP al recibir SIGTERM (uvicorn lo
propaga). Timeouts explícitos en todas las dependencias evitan
solicitudes colgadas.
Evidencia: `app.py::_lifespan`, `container.py::aclose`,
`TestLifespan` en `tests/test_api.py`, healthcheck de arranque en compose.

## 10. Dev/prod parity — Cumplido

Mismos Dockerfile e imagen para todos los entornos; diferencias solo en
variables de entorno. La ejecución local con `uv run uvicorn` usa el
mismo código que el contenedor.
Evidencia: un único `Dockerfile`; `.env.example` para reproducir la
configuración local.

## 11. Logs — Cumplido

Logs estructurados en JSON de una línea por stdout (`logging_config.py`),
con nivel configurable (`LOG_LEVEL`). Nunca se registran API keys, bytes
del PDF, texto extraído completo ni prompts: solo códigos, tamaños,
checksums, rutas, estados e `request_id`.
Evidencia: `logging_config.py`, mensajes de log revisados en
`routes.py`, `middleware.py`, clientes; sin `print` ni archivos de log.

## 12. Admin processes — Cumplido

Las tareas operativas son comandos explícitos documentados y se ejecutan
sobre el mismo artefacto:

- Tests, cobertura y lint: `uv run pytest`, `uv run ruff check .`
  (documentados en el README).
- Pruebas de carga: `tests/load/` (k6 Spike y Vegeta), con parámetros
  configurables y ejecución manual consciente.
- Diagnóstico en ejecución: `GET /health/live`, `GET /health/ready`,
  `GET /metrics`, todo sobre la misma imagen.

## Resumen

12/12 factores implementados y con evidencia verificable en el código o
en las comprobaciones ejecutadas (tests, `docker compose config/build`).

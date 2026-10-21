# pdf-extractext-summarize

Microservicio responsable de generar resúmenes de texto extraído de
documentos PDF del ecosistema **pdf-extractext**.

`pdf-summarize` **no** valida PDFs ni extrae texto: coordina los
microservicios existentes y al proveedor de IA para producir el resumen:

```
POST /summarize (PDF binario)
  └─▶ Validation  (POST /validate)  → checksum y tamaño del archivo
  └─▶ Extract     (POST /extract)   → texto y cantidad de páginas
  └─▶ Proveedor IA (OpenAI-compatible, por defecto NVIDIA)
                                     → resumen en el idioma del texto
  └─▶ Persistence (POST /documents) → registro idempotente por checksum
```

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/summarize` | Resume un PDF enviado como binario (`Content-Type: application/pdf`). |
| `GET` | `/health/live` | Liveness: el proceso está vivo. No consulta dependencias. |
| `GET` | `/health/ready` | Readiness: la configuración esencial está disponible (requiere `LLM_API_KEY`). |
| `GET` | `/metrics` | Métricas Prometheus del proceso. |
| `GET` | `/docs`, `/openapi.json` | Documentación OpenAPI generada por FastAPI. |

### Respuesta de éxito (`200`)

```json
{
  "summary": "…resumen…",
  "page_count": 7,
  "file_size_bytes": 2048,
  "checksum": "sha256…",
  "checksum_algorithm": "sha256",
  "model": "meta/llama-3.1-8b-instruct",
  "request_id": "…"
}
```

### Errores (JSON uniforme)

```json
{"error": {"code": "VALIDATION_UNAVAILABLE", "message": "…", "request_id": "…"}}
```

Códigos principales: `UNSUPPORTED_MEDIA_TYPE` (415), `EMPTY_PDF` (400),
`PDF_TOO_LARGE` (413), `INVALID_PDF`/`ENCRYPTED_PDF`/`NO_USEFUL_TEXT`
(422), `VALIDATION_UNAVAILABLE`/`EXTRACT_UNAVAILABLE`/`LLM_NOT_CONFIGURED`/`LLM_RATE_LIMITED`/`PERSISTENCE_UNAVAILABLE`
(503), `LLM_AUTH_ERROR`/`LLM_PROVIDER_ERROR`/`PERSISTENCE_REJECTED`
(502), `LLM_TIMEOUT` (504), `PERSISTENCE_CONFLICT` (409),
`INTERNAL_ERROR` (500). Nunca se devuelven trazas, secretos ni prompts.

Cada solicitud acepta un `X-Request-ID`; si no llega, se genera uno, se
devuelve en la respuesta y se **propaga** a Validation, Extract y
Persistence para correlacionar el flujo completo.

El documento (checksum, texto extraído, resumen, páginas, tamaño,
algoritmo del checksum y modelo de IA) se registra en Persistence
**solo después** de obtener un resumen exitoso. Si Persistence falla, la
solicitud responde con error y el resumen no se pierde de forma
silenciosa; la idempotencia de Persistence por checksum permite
reenviar manualmente la misma solicitud sin duplicados.

## Configuración (variables de entorno)

| Variable | Por defecto | Descripción |
|---|---|---|
| `LLM_API_KEY` | — | Clave del proveedor de IA. **Obligatoria para sumarizar.** |
| `LLM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | API compatible con OpenAI. |
| `LLM_MODEL` | `meta/llama-3.1-8b-instruct` | Modelo utilizado. |
| `LLM_TIMEOUT_SECONDS` | `60` | Timeout de la llamada al proveedor. |
| `LLM_MAX_TOKENS` | `1000` | Longitud máxima de salida. |
| `VALIDATION_SERVICE_URL` | `http://pdf-validation:8000` | URL base de Validation. |
| `EXTRACT_SERVICE_URL` | `http://extract:8000` | URL base de Extract. |
| `PERSISTENCE_SERVICE_URL` | `http://pdf-persistence:8003` | URL base de Persistence. |
| `UPSTREAM_TIMEOUT_SECONDS` | `30` | Timeout hacia los microservicios. |
| `MAX_PDF_SIZE_MIB` | `20` | Tamaño máximo aceptado del PDF. |
| `LOG_LEVEL` | `INFO` | Nivel de logging. |
| `PORT` | `8000` | Puerto publicado por docker compose. |
| `PDF_ECOSYSTEM_NETWORK` | `pdf-ecosystem-net` | Red externa del ecosistema (solo compose de integración). |

Los secretos se configuran en `.env` (copia de `.env.example`); `.env`
nunca se versiona.

## Ejecución local

Requisitos: Python 3.13 y [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env   # completar LLM_API_KEY y URLs reales

uv run uvicorn pdf_summarize.main:app --port 8000
```

Verificaciones:

```bash
uv run pytest                                        # pruebas + cobertura
uv run pytest --cov=src --cov-report=term-missing    # cobertura explícita
uv run ruff check .
uv run ruff format --check .
```

Las pruebas unitarias **no** llaman a los microservicios ni al modelo de
IA: usan dobles (`httpx.MockTransport`, transporte ASGI y fakes).

## Docker

```bash
docker compose up --build
```

- Imagen `python:3.13-slim` con instalación reproducible
  (`uv sync --frozen --no-dev`) y usuario no root.
- Healthcheck sobre `/health/live`.
- El servicio arranca de forma independiente: `/health/live` y
  `/health/ready` funcionan aunque Validation/Extract no existan; las
  llamadas de negocio fallan con respuestas controladas (503).

### Integración con el ecosistema (red Docker)

`docker-compose.ecosystem.yml` une el servicio a la red externa
compartida, configurable con `PDF_ECOSYSTEM_NETWORK`:

```bash
docker network create "${PDF_ECOSYSTEM_NETWORK:-pdf-ecosystem-net}"
docker compose -f docker-compose.ecosystem.yml up -d
```

Los demás servicios deben declarar la misma red externa en su compose.
Los nombres DNS por defecto (`pdf-validation`, `extract`,
`pdf-persistence` en el puerto 8003) derivan de los
`docker-compose.yml` reales de cada repositorio.

## Pruebas de carga

> **Advertencia**: cada solicitud exitosa a `/summarize` consume tokens
> del proveedor de IA y puede generar coste facturable. Ejecutar las
> pruebas de forma consciente, con valores conservadores y sobre el
> entorno elegido. Los scripts no se ejecutan automáticamente.

- **Spike (k6)**: `tests/load/k6-spike.js`. Requiere `PDF_PATH` (p. ej.
  el `sample.pdf` del repositorio Extract) y permite configurar
  `BASE_URL`, `SPIKE_TARGET`, `RAMP_UP`, `HOLD` y `RAMP_DOWN`.

  ```bash
  PDF_PATH=../pdf-extractext-extract/tests/sample.pdf \
  BASE_URL=http://localhost:8000 \
  k6 run tests/load/k6-spike.js
  ```

- **Carga fija (Vegeta)**: `tests/load/vegeta-test.ps1` (PowerShell,
  usa la imagen Docker `peterevans/vegeta`). Parámetros: `-BaseUrl`,
  `-Rate`, `-DurationSec`, `-PdfPath`, `-Report`.

  ```powershell
  .\tests\load\vegeta-test.ps1 -BaseUrl http://localhost:8000 -Rate 5 -DurationSec 15
  ```

Estos scripts **no se han ejecutado** contra el proveedor real; no hay
resultados de carga disponibles todavía.

## Observabilidad

- **Logs**: JSON de una línea por stdout con timestamp, nivel, logger y
  mensaje; nunca contienen claves, bytes del PDF, texto extraído ni
  prompts.
- **Métricas** (`/metrics`): `pdf_summarize_requests_total` (contador por
  ruta y estado) y `pdf_summarize_request_latency_seconds` (histograma
  de latencia por ruta).
- **Trazabilidad**: `X-Request-ID` correlacionable entre servicios. No
  hay trazas distribuidas completas (OpenTelemetry queda como paso
  futuro documentado en `docs/architecture.md`).

## Documentación adicional

- `docs/architecture.md` — arquitectura en capas y decisiones.
- `docs/integration-contracts.md` — contratos verificados de Validation,
  Extract y proveedor de IA; pendientes (Persistence, red compartida).
- `docs/12-factor-checklist.md` — los doce factores con evidencia.

## Limitaciones conocidas

1. **Integración con Persistence verificada solo con dobles**: el cliente
   HTTP, el contrato y la integración del caso de uso están probados con
   transporte simulado. La verificación contra el contenedor Docker real
   (`http://pdf-persistence:8003` en `pdf-ecosystem-net`) es un paso
   manual pendiente.
2. **Pruebas de carga sin ejecutar**: scripts preparados, sin resultados
   reales para evitar consumo facturable.
3. **Sumarización real no verificada aquí**: las pruebas usan mocks; una
   sumarización real requiere `LLM_API_KEY` válida y se distingue de las
   pruebas en todo momento.

## Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| `/summarize` → 503 `LLM_NOT_CONFIGURED` | Falta `LLM_API_KEY`. | Configurarla en `.env` y recrear el contenedor. |
| `/summarize` → 503 `VALIDATION_UNAVAILABLE`, `EXTRACT_UNAVAILABLE` o `PERSISTENCE_UNAVAILABLE` | Dependencias ausentes o inalcanzables. | Verificar URLs (`VALIDATION_SERVICE_URL`, `EXTRACT_SERVICE_URL`, `PERSISTENCE_SERVICE_URL`) y que los servicios estén corriendo. |
| `/summarize` → 409 `PERSISTENCE_CONFLICT` | El checksum ya existe en Persistence con datos distintos. | Revisar el documento con `GET /documents/{checksum}` en Persistence; usar `PUT` para actualizarlo si corresponde. |
| `/summarize` → 502 `PERSISTENCE_REJECTED` | Persistence rechazó el payload (p. ej. checksum inválido). | Verificar la versión/contrato de Persistence y reportar el desajuste. |
| `/health/ready` → 503 | Configuración esencial incompleta. | Revisar `reason` de la respuesta. |
| 502 `LLM_AUTH_ERROR` | Clave rechazada. | Verificar `LLM_API_KEY` y `LLM_BASE_URL`. |
| 504 `LLM_TIMEOUT` | Proveedor lento. | Aumentar `LLM_TIMEOUT_SECONDS`. |
| 413 `PDF_TOO_LARGE` | Archivo mayor a `MAX_PDF_SIZE_MIB`. | Subir el límite o reducir el PDF. |

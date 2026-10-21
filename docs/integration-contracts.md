# Contratos de integración verificados

Fecha de inspección: 2026-10-19 (Validation, Extract y proveedor de IA);
2026-10-21 (Persistence). Repositorios inspeccionados en local:
`D:\pdf-extractext-validation`, `D:\pdf-extractext-extract` y
`D:\pdf-extractext-persistence`.

## Verificado: microservicio Validation

Fuente: `D:\pdf-extractext-validation\src\pdf_validation\{app,schemas}.py`
y su `docker-compose.yml` (servicio `pdf-validation`).

### `POST /validate`

- Entrada: PDF binario con `Content-Type: application/pdf` y `X-Request-ID`.
- Éxito `200`:

```json
{
  "valid": true,
  "file_size_bytes": 2048,
  "checksum": "<sha256 en hexadecimal>",
  "checksum_algorithm": "sha256"
}
```

- Error: `{"error": {"code": "<CÓDIGO>", "message": "<mensaje>"}}` con:

  | code | status |
  |---|---|
  | `EMPTY_PDF` | 400 |
  | `PDF_TOO_LARGE` | 413 |
  | `UNSUPPORTED_MEDIA_TYPE` | 415 |
  | `INVALID_PDF` | 422 |
  | `ENCRYPTED_PDF` | 422 |

### Salud

- `GET /health/live` → `200 {"status": "alive"}`
- `GET /health/ready` → `200 {"status": "ready"}`

### Uso en Summarize

`infrastructure/validation_client.py` consume este contrato y traduce
los errores de Validation a excepciones propias:

- `EMPTY_PDF` → `EmptyPdfError` (400)
- `PDF_TOO_LARGE` → `PdfTooLargeError` (413)
- `UNSUPPORTED_MEDIA_TYPE` → `UnsupportedMediaTypeError` (415)
- Otros 4xx (p. ej. `INVALID_PDF`, `ENCRYPTED_PDF`) → `ValidationRejectedError`
  conservando el código y mensaje de origen (422)
- 5xx, timeout o respuesta malformada → `ValidationUnavailableError` (503)

## Verificado: microservicio Extract

Fuente: `D:\pdf-extractext-extract\src\api\routes.py` y su
`docker-compose.yml` (servicio `extract`, con nginx publicando el 8000).

### `POST /extract`

- Entrada: PDF binario con `Content-Type: application/pdf` y `X-Request-ID`.
- Éxito `200`:

```json
{"content": "<texto extraído>", "page_count": 7}
```

- Error: `{"detail": "<mensaje>"}` con 400 (PDF inválido), 413 (tamaño) y
  415 (Content-Type). Además `GET /health` → `200 {"status": "ok"}`.

### Uso en Summarize

`infrastructure/extract_client.py` traduce los errores de Extract:

- 400 → `ExtractionFailedError` (422)
- 413 → `PdfTooLargeError` (413)
- 415 → `UnsupportedMediaTypeError` (415)
- 5xx, timeout o respuesta malformada → `ExtractUnavailableError` (503)

## Contrato propio: `POST /summarize`

- Entrada: PDF binario con `Content-Type: application/pdf`; opcionalmente
  `X-Request-ID` (si falta se genera y siempre se devuelve en la respuesta).
- Éxito `200`:

```json
{
  "summary": "<resumen>",
  "page_count": 7,
  "file_size_bytes": 2048,
  "checksum": "<sha256>",
  "checksum_algorithm": "sha256",
  "model": "meta/llama-3.1-8b-instruct",
  "request_id": "<id>"
}
```

- Error: `{"error": {"code": "...", "message": "...", "request_id": "..."}}`
  con códigos estables documentados en el OpenAPI (`/docs`) y en el README.

## Verificado: proveedor de IA

Fuente: `D:\pdf-extractext\app\services\ai_service.py` (proyecto original).
API compatible con OpenAI: `POST {LLM_BASE_URL}/chat/completions` con
`Authorization: Bearer <LLM_API_KEY>`, modelo por defecto
`meta/llama-3.1-8b-instruct`, respuesta con
`choices[0].message.content`. `infrastructure/llm_client.py` mapea
401/403 → `LLM_AUTH_ERROR` (502), 429 → `LLM_RATE_LIMITED` (503),
timeout → `LLM_TIMEOUT` (504), resto → `LLM_PROVIDER_ERROR` (502) y
ausencia de clave → `LLM_NOT_CONFIGURED` (503) sin realizar la llamada.

## Verificado: microservicio Persistence

Fuente: `D:\pdf-extractext-persistence\src\pdf_persistence\{schemas,api\routes,service\document_use_case}.py`.
El servicio corre en Docker como `pdf-persistence` en el puerto 8003,
conectado a la red externa `pdf-ecosystem-net` y a MongoDB.

### `POST /documents`

- Entrada: JSON con `checksum` obligatorio (hexadecimal en minúsculas,
  32–128 caracteres) y campos opcionales: `checksum_algorithm`,
  `filename`, `content_type`, `file_size_bytes`, `text`, `summary`,
  `page_count`, `model`, `metadata`; encabezado `X-Request-ID`.
- Éxito `201` (creado) o `200` (repetición idempotente con datos
  idénticos): `DocumentResponse` con el documento registrado.
- Error: `{"error": {"code", "message", "request_id"}}` con:

  | code | status |
  |---|---|
  | `DOCUMENT_ALREADY_EXISTS` | 409 |
  | `INVALID_REQUEST` (payload inválido) | 422 |
  | `MONGO_UNAVAILABLE` | 503 |
  | `MONGO_TIMEOUT` | 504 |

### Otros endpoints (no usados por Summarize)

`GET /documents`, `GET /documents/{checksum}`, `PUT /documents/{checksum}`
y `DELETE /documents/{checksum}` (eliminación lógica). Además
`GET /health/live`, `GET /health/ready` y `GET /metrics`.

### Uso en Summarize

`infrastructure/persistence_client.py` consume únicamente
`POST /documents` (nunca MongoDB directamente) y traduce:

- 200/201 → éxito (sin distinguir creación de repetición idempotente)
- 409 → `PersistenceConflictError` (409) conservando el mensaje
- 422 y otros 4xx → `PersistenceRejectedError` (502)
- 5xx, timeout, error de conexión o cuerpo malformado →
  `PersistenceUnavailableError` (503)

El caso de uso persiste el documento (checksum, texto extraído, resumen,
páginas, tamaño, algoritmo y modelo) solo después de obtener un resumen
exitoso; reutiliza el checksum calculado por Validation y no reintenta
ante fallos (la idempotencia de Persistence por checksum hace seguro un
reenvío manual).

## Red Docker compartida

`docker-compose.ecosystem.yml` une el servicio a la red externa real del
ecosistema, `pdf-ecosystem-net` (configurable con
`PDF_ECOSYSTEM_NETWORK`). Los nombres DNS verificados son
`pdf-validation`, `extract` y `pdf-persistence` (puerto 8003).

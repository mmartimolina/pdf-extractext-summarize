# Arquitectura de pdf-summarize

## Responsabilidad

`pdf-summarize` coordina la sumarización de un documento PDF delegando
en los microservicios existentes del ecosistema:

1. **Validation** verifica el PDF y calcula el checksum del contenido.
2. **Extract** obtiene el texto del documento.
3. Un **proveedor de IA configurable** (API compatible con OpenAI; por
   defecto la API de NVIDIA usada en el proyecto original) genera el resumen.
4. **Persistence** registra el documento procesado (checksum, texto,
   resumen y metadatos) de forma idempotente por checksum.

El servicio no valida PDFs, no extrae texto ni accede a bases de datos:
solo orquesta. Persistence se consume mediante HTTP (`POST /documents`),
sin mezclar lógica de base de datos en este servicio.

## Capas

```
src/pdf_summarize/
├── api/                  # Presentación
│   ├── routes.py         # POST /summarize, /health/*, /metrics
│   ├── middleware.py     # X-Request-ID, observabilidad (logs + métricas)
│   ├── error_handlers.py # Manejo centralizado de excepciones → JSON
│   └── metrics.py        # Contadores e histogramas Prometheus
├── service/              # Aplicación / negocio
│   ├── summarize_use_case.py  # Coordinación del flujo
│   └── prompts.py             # Construcción del prompt (aislada y testeable)
├── domain/               # Núcleo independiente de frameworks
│   ├── errors.py         # Excepciones con código estable y estado HTTP
│   ├── models.py         # ValidationReport, ExtractionResult, SummaryResult,
│   │                     # DocumentRecord
│   └── ports.py          # Protocolos: Validator, Extractor, Summarizer, Persister
├── infrastructure/       # Infraestructura
│   ├── validation_client.py  # Cliente HTTP de Validation
│   ├── extract_client.py     # Cliente HTTP de Extract
│   ├── persistence_client.py # Cliente HTTP de Persistence
│   └── llm_client.py         # Cliente del proveedor de IA
├── container.py          # DI: construcción y cierre ordenado de clientes
├── app.py                # Fábrica de la aplicación FastAPI (lifespan)
├── config.py             # Settings desde variables de entorno
├── logging_config.py     # Logs JSON a stdout
├── schemas.py            # Contrato HTTP (entrada/salida)
└── main.py               # Punto de entrada uvicorn
```

**Presentación → negocio → infraestructura**: los controladores no
contienen lógica de negocio; el caso de uso depende de **puertos**
(`domain/ports.py`) implementados por la infraestructura; las pruebas
sustituyen los clientes por dobles sin tocar HTTP real.

## Flujo de `POST /summarize`

```
Cliente ──PDF binario──▶ /summarize
   │  content-type/size/empty (presentación)
   ├─▶ ValidationClient.validate()  → checksum, tamaño  (HTTP, timeout)
   ├─▶ ExtractClient.extract()      → texto, páginas     (HTTP, timeout)
   │  texto útil ≥ 50 chars (regla de negocio)
   ├─▶ build_summary_prompt()       → prompt             (puro, testeable)
    ├─▶ LLMClient.summarize()        → resumen            (HTTP, timeout)
    ├─▶ PersistenceClient.save()     → registro idempotente (HTTP, timeout)
    └─▶ 200 JSON: summary + metadatos + request_id
```

Cada fallo se traduce a una excepción de dominio con código estable
(`docs/integration-contracts.md` lista los códigos) y el manejador
central la convierte en JSON uniforme.

## Decisiones

- **httpx asíncrono** con timeouts explícitos y cierre en `lifespan`:
  concurrencia sin bloquear (12-Factor, procesos/disposabilidad).
- **prometheus-client** para `/metrics`: integración simple y verificable;
  OpenTelemetry queda como paso futuro cuando se necesite trazas distribuidas.
- **Sin reintentos** en llamadas externas: los errores se responden de
  forma controlada; quien llama decide reintentar (KISS, YAGNI).
- **Pruebas** con dobles (fakes + `httpx.MockTransport` + transporte ASGI):
  nunca se llama al modelo de IA ni a los microservicios reales.

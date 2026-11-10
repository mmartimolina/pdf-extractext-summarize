# Arquitectura de pdf-summarize

## Responsabilidad

`pdf-summarize` coordina la sumarización de un documento PDF:

1. **Validation** verifica el PDF y calcula el checksum.
2. **Persistence** reserva el checksum en estado `PENDING` con el identificador de SAGA.
3. **Extract** obtiene el texto del documento.
4. Un **proveedor de IA configurable** genera el resumen.
5. **Persistence** confirma el registro como `COMPLETED`.

El servicio no valida PDFs, no extrae texto ni accede directamente a bases de datos.
Persistence se consume por HTTP. El caso de uso actúa como orquestador SAGA y
ejecuta una compensación (eliminación lógica) si falla un paso posterior a la
reserva.

## Capas

```
src/pdf_summarize/
├── api/                  # Presentación
├── service/              # Aplicación: orquestador SAGA y prompts
├── domain/               # Modelos, errores y puertos
├── infrastructure/       # Clientes HTTP, Consul y resiliencia
├── container.py          # Inyección y cierre ordenado de dependencias
├── app.py                # Fábrica FastAPI (lifespan)
├── config.py             # Settings desde variables de entorno
└── main.py               # Punto de entrada uvicorn
```

**Presentación → negocio → infraestructura**: los controladores no contienen
lógica de negocio; el caso de uso depende de puertos implementados por la
infraestructura. Las pruebas sustituyen los clientes por dobles.

## Flujo SAGA de `POST /summarize`

```
Cliente ──PDF──▶ SummarizeUseCase
                   │
                   ├─▶ Validation.validate() ──▶ checksum
                   │
                   ├─▶ Persistence.begin() ────▶ reserva PENDING
                   │
                   ├─▶ Extract.extract() ──────▶ texto y páginas
                   │
                   ├─▶ LLM.summarize() ────────▶ resumen
                   │
                   ├─▶ Persistence.save() ─────▶ COMPLETED
                   │
                   └─▶ respuesta 200
                   
Si falla Extract, LLM o la confirmación:
                   └─▶ Persistence.compensate()
                         └─▶ DELETE lógico de la reserva
```

La reserva incluye `metadata.saga_id=request_id` y
`metadata.saga_status=PENDING`. La confirmación cambia el estado a
`COMPLETED`. Si la compensación falla, se conserva el error original, se
registra `saga_compensation_failed` y el registro PENDING queda identificable
para reconciliación operativa.

## Resiliencia y descubrimiento

- Los clientes internos utilizan Retry con backoff y Circuit Breaker.
- Persistence admite POST, PUT y DELETE a través del mismo cliente resiliente.
- Consul descubre instancias saludables; se conserva una URL fallback.
- Rate Limit y caché LRU/TTL son locales a cada proceso, no distribuidos.

## Decisiones

- **httpx asíncrono** con timeouts explícitos y cierre en `lifespan`.
- **prometheus-client** para exponer métricas en `/metrics`.
- **Pruebas** con dobles, `httpx.MockTransport` y transporte ASGI; no llaman
  al proveedor LLM ni a microservicios reales.
- La SAGA no requiere transacción distribuida ni base de datos compartida.

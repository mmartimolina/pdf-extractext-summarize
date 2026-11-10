# Patrones de resiliencia y protección

## Retry

`ResilientHttpClient` realiza hasta tres intentos con espera exponencial ante
errores de transporte y respuestas HTTP 502, 503 o 504. Se utiliza en las
llamadas internas a Validation, Extract y Persistence. Persistence admite
repeticiones idempotentes por checksum. No se reintenta el proveedor LLM para
evitar duplicar operaciones potencialmente facturables.

## Circuit Breaker

Cada cliente HTTP interno mantiene su propio circuito:

- Umbral: cinco fallos consecutivos.
- Estado abierto: veinte segundos.
- Recuperación: una única solicitud de prueba (half-open).
- Un resultado exitoso restablece el contador; un nuevo fallo vuelve a abrir
  el circuito.

## Rate Limit

La API de Summarize limita por IP y ventana móvil. La configuración
predeterminada es 60 solicitudes por 60 segundos. Las rutas de health y
métricas están excluidas. Al exceder el límite responde HTTP 429 y envía
`Retry-After`.

El contador es local al proceso; no representa un límite global entre réplicas.

## Cache

El cliente LLM conserva en memoria los resúmenes exitosos, indexados mediante
SHA-256 del prompt. La configuración predeterminada es TTL de 300 segundos y
un máximo de 256 entradas (LRU). No se guarda el prompt ni el PDF en la caché.
El caché es local a cada instancia y se pierde al reiniciar el proceso.

Variables: `LLM_CACHE_TTL_SECONDS` y `LLM_CACHE_MAX_ENTRIES`.

## Service discovery

Los cuatro servicios se registran y desregistran en Consul durante su ciclo de
vida. Consul ejecuta health checks HTTP. Summarize consulta el catálogo de
instancias saludables antes de invocar Validation, Extract y Persistence; si
Consul no está disponible o no hay instancias saludables, usa la URL fallback.

## SAGA y orquestación

`SummarizeUseCase` es un orquestador del flujo Validation → Extract → LLM →
Persistence. Sin embargo, el flujo actual no implementa una SAGA completa con
acciones compensatorias: Persistence es el único paso con efecto de escritura
y se ejecuta al final. No se debe presentar esta orquestación como una SAGA
completa. Para cumplir ese patrón estrictamente, el flujo debe incorporar
estados persistidos y compensaciones explícitas ante fallos parciales.

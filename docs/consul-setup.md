# Integración del ecosistema con Consul

## Objetivo

Consul mantiene el registro de las instancias saludables. Summarize consulta el
catálogo de Consul antes de invocar Validation, Extract y Persistence. Si Consul
no está configurado o no devuelve instancias saludables, el cliente conserva la
URL configurada como fallback.

Cada servicio se registra al iniciar y se desregistra al detenerse. Los checks
HTTP usan los endpoints de liveness de cada servicio.

## Requisitos

- Docker Compose.
- Los cuatro repositorios clonados en carpetas separadas.
- MongoDB disponible para Persistence.
- La variable `LLM_API_KEY` configurada para Summarize.

## Arranque en PowerShell

Crear la red compartida una sola vez:

```powershell
docker network create pdf-ecosystem-net
```

Iniciar Consul desde el repositorio Summarize:

```powershell
docker compose -f docker-compose.ecosystem.yml up -d consul
```

Iniciar Extract:

```powershell
docker compose up -d --build --scale extract=3
```

Iniciar Validation en el puerto de host 8001 para evitar el conflicto con
Nginx/Extract, que publica el puerto 8000:

```powershell
$env:PORT = "8001"
docker compose up -d --build
```

Iniciar Persistence. Definir antes la URI real de MongoDB:

```powershell
$env:MONGO_URI = "mongodb://host.docker.internal:27017"
docker compose -f docker-compose.ecosystem.yml up -d --build
```

Iniciar Summarize (definir previamente la clave del proveedor de IA):

```powershell
$env:LLM_API_KEY = "TU_CLAVE"
docker compose -f docker-compose.ecosystem.yml up -d --build
```

Los comandos de cada servicio deben ejecutarse desde la carpeta de su
repositorio. Si MongoDB está en otro host o contenedor, reemplazar
`MONGO_URI` por su URI accesible desde la red Docker.

## Verificación

- Interfaz de Consul: http://localhost:8500
- Extract a través de Nginx: http://localhost:8000/health
- Validation: http://localhost:8001/health/ready
- Summarize: http://localhost:8002/health/live

En Consul deben aparecer los servicios `extract`, `pdf-validation`,
`pdf-persistence` y `pdf-summarize` con checks saludables.

## Consideraciones

- La red `pdf-ecosystem-net` es externa y debe existir antes de levantar los
  Compose.
- El limitador de solicitudes actual es local a cada proceso. Para un límite
  global entre réplicas se requiere un backend compartido.
- El resolver consulta Consul en cada llamada interna; si la consulta falla o
  no hay instancias saludables, utiliza la URL fallback configurada.
- La configuración de Consul no reemplaza la autenticación/autorización de las
  APIs ni debe exponer la interfaz administrativa en producción.

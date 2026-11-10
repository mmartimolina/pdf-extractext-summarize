# Prácticas de desarrollo seguro

## Controles presentes en el ecosistema

- Los contenedores de aplicación usan usuarios no privilegiados.
- Las dependencias se instalan desde `uv.lock` con modo frozen en las imágenes.
- Las credenciales se inyectan por variables de entorno; `.env` no debe versionarse.
- Los servicios validan tipo de contenido, tamaño y estructura del PDF.
- Summarize no registra cuerpos, archivos ni prompts; registra identificadores,
  rutas, estados y latencias.
- Las APIs exponen healthchecks separados de la lógica de negocio.
- Rate Limit reduce solicitudes excesivas en la API de Summarize.
- Dependabot revisa semanalmente dependencias Python y GitHub Actions en los
  cuatro repositorios.

## Controles que deben verificarse antes de publicar

1. Confirmar que no existan secretos reales en el historial de Git.
2. Revisar las alertas de Dependabot y corregir vulnerabilidades conocidas.
3. Ejecutar pruebas y análisis estático en los cuatro repositorios.
4. Mantener imágenes base y acciones de GitHub actualizadas.
5. No exponer Consul ni MongoDB públicamente en un despliegue real.
6. Usar TLS y autenticación/autorización si las APIs salen de la red privada.

La configuración de Consul incluida para la demostración usa un agente en modo
desarrollo. No es una configuración de producción ni habilita ACL/TLS.

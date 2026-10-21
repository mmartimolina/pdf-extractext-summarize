# Prueba de carga fija con Vegeta para POST /summarize.
#
# ADVERTENCIA: cada solicitud exitosa a /summarize consume tokens del
# proveedor de IA y puede generar coste facturable. Ejecutar de forma
# consciente y con valores conservadores sobre el entorno elegido.
#
# Uso:
#   .\tests\load\vegeta-test.ps1
#
# Parámetros opcionales (valores por defecto conservadores):
#   .\tests\load\vegeta-test.ps1 -BaseUrl http://localhost:8002 -Rate 5 -DurationSec 15 `
#     -PdfPath ..\pdf-extractext-extract\tests\sample.pdf

param(
    [string]$BaseUrl = "http://localhost:8000",
    [int]$Rate = 5,
    [int]$DurationSec = 15,
    [string]$PdfPath = "../pdf-extractext-extract/tests/sample.pdf",
    [string]$Report = "tests/load/vegeta-report.txt"
)

$ErrorActionPreference = "Stop"

$ResolvedPdf = Resolve-Path $PdfPath -ErrorAction SilentlyContinue
if (-not $ResolvedPdf) {
    Write-Error "No se encontró el PDF en '$PdfPath'. Indique -PdfPath con la ruta a un PDF válido."
    return
}
$ResolvedPdf = $ResolvedPdf.Path

Write-Host "Ejecutando prueba de carga con Vegeta..."
Write-Host "URL:      $BaseUrl/summarize"
Write-Host "Carga:    $Rate requests/s durante $DurationSec segundos"
Write-Host "ADVERTENCIA: las solicitudes exitosas consumen tokens del proveedor de IA."

# Targets enviados por stdin; el PDF se monta en el contenedor como /pdf.
$targets = "POST $BaseUrl/summarize`nContent-Type: application/pdf`n@/pdf`n"

$targets | docker run --rm -i `
  -v "${ResolvedPdf}:/pdf:ro" `
  peterevans/vegeta sh -c `
  "vegeta attack -rate=$Rate/s -duration=$($DurationSec)s | vegeta report" |
  Tee-Object -FilePath $Report

Write-Host ""
Write-Host "Reporte guardado en $Report"

// Prueba de carga tipo Spike para POST /summarize (k6).
//
// ADVERTENCIA: cada solicitud exitosa a /summarize consume tokens del
// proveedor de IA y puede generar coste facturable. Ejecutar de forma
// consciente y con valores conservadores sobre el entorno elegido.
//
// Requisitos:
//   - k6 instalado (https://k6.io).
//   - Un PDF válido accesible localmente (PDF_PATH).
//
// Ejemplo de ejecución (por defecto apunta al puerto local del compose):
//   k6 run tests/load/k6-spike.js
//
// Con parámetros personalizados:
//   PDF_PATH=../pdf-extractext-extract/tests/sample.pdf \
//   BASE_URL=http://localhost:8002 \
//   SPIKE_TARGET=5 RAMP_UP=10s HOLD=20s RAMP_DOWN=10s \
//   k6 run tests/load/k6-spike.js

import http from "k6/http";
import { check } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const PDF_PATH = __ENV.PDF_PATH;

if (!PDF_PATH) {
  throw new Error(
    "Debe indicarse PDF_PATH con la ruta a un PDF válido, p. ej. " +
      "PDF_PATH=../pdf-extractext-extract/tests/sample.pdf"
  );
}

const pdf = open(PDF_PATH, "b");

// Picos conservadores: valor por defecto bajo para limitar el consumo
// de tokens si se ejecuta contra un proveedor real.
const SPIKE_TARGET = parseInt(__ENV.SPIKE_TARGET || "10", 10);
const RAMP_UP = __ENV.RAMP_UP || "10s";
const HOLD = __ENV.HOLD || "20s";
const RAMP_DOWN = __ENV.RAMP_DOWN || "10s";

export const options = {
  stages: [
    { duration: RAMP_UP, target: SPIKE_TARGET },
    { duration: HOLD, target: SPIKE_TARGET },
    { duration: RAMP_DOWN, target: 0 },
  ],
};

export default function () {
  const response = http.post(`${BASE_URL}/summarize`, pdf, {
    headers: { "Content-Type": "application/pdf" },
  });

  check(response, {
    "status is 200": (r) => r.status === 200,
  });
}

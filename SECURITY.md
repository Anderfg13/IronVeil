# Política de seguridad

## Qué es (y qué no es) este proyecto

IronVeil es un **laboratorio académico** de defensa de LLMs. Contiene, **a propósito**:

- **Credenciales ficticias** (canarios `SPT-DEMO-8841`, `RRHH-DEMO-2291`) que son el objeto de estudio del experimento.
- **Payloads de ataque** (`ataques/variantes_ataque.md`) y los resultados de ejecutarlos contra el stack propio.

Nada de eso es una vulnerabilidad del software. No reportes los canarios ni los payloads como secretos filtrados.

## Qué sí queremos que nos reportes

Una falla en el código de infraestructura (`proxy/`, `ataques/`, `analisis/`, `scripts/`, flujos de CI) que permita,
por ejemplo: saltarse un mecanismo defensivo sin que quede en el log, ejecutar comandos o escribir fuera del proyecto
a través de un argumento, fugar una credencial real, o desactivar la verificación TLS.

## Cómo reportarlo

Usa **«Report a vulnerability»** en la pestaña *Security* del repositorio (aviso privado), o escribe directamente a
Anderson Fabian Garcia Nieto. **No abras un *issue* público** con el detalle. Incluye versión o commit, pasos para
reproducirlo y el impacto que crees que tiene. Respondemos en un plazo razonable; es un proyecto de seminario, no un
producto con soporte.

## Reglas para quien pruebe el proyecto

- **Solo contra tu propio stack** (`localhost`/Docker). No apuntes los ataques, escaneos ni pruebas de carga contra
  servidores de terceros.
- Ollama nunca se expone al host: solo el proxy publica el puerto 8000.
- Las extensiones que envían texto a un tercero (Jev, APIs de frontera) están **apagadas por defecto** y exigen un
  permiso explícito en `.env`; no las actives con datos reales.

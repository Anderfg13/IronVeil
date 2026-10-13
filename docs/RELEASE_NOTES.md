# IronVeil — entrega final (2026-10-31)

Framework académico de defensa en profundidad para LLMs autoalojados (Ollama): un proxy FastAPI con
cinco mecanismos defensivos activables por bandera y siete configuraciones experimentales (C0–C6).

## Qué incluye

- **Proxy** (`proxy/`): filtrado, delimitación, clasificación (Prompt Guard 2 + Llama Guard 3, falla cerrada),
  mínimo privilegio y aprobación humana + rate limit, con la cadena como lista recorrida en bucle.
- **Un solo comando para levantarlo:** `cp .env.example .env && docker compose up --build`.
- **Las 7 configuraciones** cambian solo `config.yaml` (`python scripts/seleccionar_config.py C0..C6`).
- **Ataques** (`ataques/`): vectores V1–V6, extensión V7 (herramientas simuladas), carga, medición de costo
  y validación externa con Garak.
- **Análisis reproducible** (`analisis/`): consolidación, estadística (Fisher), tabla maestra, matriz real vs. hipótesis,
  costo por mecanismo y gráficas finales.
- **Extensiones opcionales** (apagadas por defecto): consola de revisión humana en vivo, exportación a SIEM
  (Wazuh, CEF, LEEF, ECS, Splunk, Elastic, Azure, CloudWatch), memoria de decisiones, normalización de entrada,
  modelo protegido remoto y clasificador alternativo (Jev).
- **Documentación visual:** diagrama de arquitectura y de clases animados (`docs/assets/`) y un visor interactivo
  (`docs/diagramas/index.html`).
- **Autenticación opcional del proxy:** `CHAT_REQUIERE_AUTENTICACION=1` (Basic o sesión, falla cerrada) con usuario de
  demo de clave aleatoria (`python -m proxy.auth --demo`).
- **Sitio público** (GitHub Pages) y **paquete `ironveil`** instalable con `pip` (comando `ironveil`).
- **CI** (ruff, black, pytest) y publicación de la imagen del proxy en GitHub Packages al subir una etiqueta.

## Resultados (resumen; detalle y límites en `analisis/resultados_finales.md`)

- ASR promedio V1–V4: **31,2 % (C0) → 15,0 % (C1 y C6)**.
- Sobrecosto propio de latencia: despreciable salvo la clasificación (**≈ 75 ms**, p95 ≈ 95 ms).
- Ninguna combinación llega a 0 % de ASR; las diferencias de uno o dos eventos no se distinguen del ruido del LLM.
- Limitaciones declaradas: el LLM no es determinista, modelo base `llama3.2:1b`, V5 no se re-corrió en el último hardware.

## Reglas respetadas

Laboratorio aislado (nunca contra terceros) · Ollama nunca se publica al host · credenciales ficticias solo en
`.env`/Modelfiles · datos crudos no editados a mano (descartes en `resultados/descartados.csv`).

## Cómo reproducir

Ver el [README](../README.md): inicio rápido, las 7 configuraciones y la sección *Reproducir los resultados*.

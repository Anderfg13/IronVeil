# Validación del formato exportado por `exportar_a_siem()` frente a Wazuh

> **Extensión opcional (integración SIEM), no parte del núcleo de 7
> configuraciones.** Esta nota valida un entregable de la extensión; no aporta a
> la pregunta de investigación principal (qué combinación de mecanismos protege
> mejor), solo evidencia de aplicabilidad.

Fecha: 2026-10-03 · Wazuh 4.14.8 (single-node, Docker) · Función validada:
`proxy/siem.py::exportar_a_siem()`.

## Conclusión

**El formato JSON exportado es compatible con Wazuh**: las 5 muestras reales se
decodificaron con el decodificador `json` nativo y activaron la regla de
IronVeil esperada, sin escribir ningún decodificador propio. **El formato CEF
no se ingiere en un Wazuh recién instalado** (no existe decodificador CEF por
defecto): hoy es solo un formato de salida para otros SIEM. Se encontraron 3
matices (no son errores de formato) que deben conocerse al usar los datos; ver
«Hallazgos».

## Método

1. **Muestra.** 5 eventos *reales* del log del proxy
   (`resultados/<fecha>/eventos.jsonl`, 13 102 eventos), elegidos para cubrir los
   casos distintos del esquema: bloqueo por `filtrado`, ataque exitoso con
   `latencia_clasificador_ms`, bloqueo por `minimo_privilegio` *sin* vector,
   `aprobacion_humana` con `tiempo_revision_humana_ms`, y tráfico normal con
   `mecanismos_activos` vacío y `mecanismo_que_bloqueo` nulo.
2. **Conversión** con `exportar_a_siem(evento)` (JSON) y
   `exportar_a_siem(evento, "cef")`.
3. **Comparación contra la documentación oficial** (abajo).
4. **Validación empírica manual** pasando cada línea por `wazuh-logtest` dentro
   del manager (el motor real de decodificación y reglas), no solo por tests.
5. **Validación estructural repetible:** `python analisis/validar_formato_siem.py`
   repite en cualquier máquina las comprobaciones de la sección siguiente sobre
   la misma muestra (+ `tests/test_validar_formato_siem.py`).

## Qué exige la documentación oficial y cómo lo cumple la salida

| Requisito (fuente) | Cumplimiento |
|---|---|
| Un archivo de log JSON se declara con `<localfile>` y `log_format` `json`, descrito como archivos JSON «de una sola línea» ([referencia de `localfile`](https://documentation.wazuh.com/current/user-manual/reference/ossec-conf/localfile.html)) | Cada evento sale en **una línea** con **un objeto JSON** (`json_valido`, `una_sola_linea`, `objeto_en_la_raiz`). Configurado en `localfile_ironveil.xml`. |
| El decodificador JSON extrae números, cadenas, booleanos, nulos, arreglos y objetos; **no soporta arreglos de objetos**; aplana objetos anidados con punto; ignora lo que haya tras el primer objeto válido ([decodificador JSON](https://documentation.wazuh.com/current/user-manual/ruleset/decoders/json-decoder.html)) | Todos los valores son **escalares** (`solo_escalares`): no hay anidamiento ni arreglos de objetos. |
| Los campos extraídos quedan como campos dinámicos que las reglas pueden referenciar (misma página) | Las reglas de `ironveil_rules.xml` usan `integration`, `resultado`, `mecanismo_que_bloqueo`, `es_extension`, `vector_probado`; todas dispararon (abajo). |
| Las reglas propias van en el rango de IDs de usuario (100000+) (guía de reglas de Wazuh) | 100100–100104. Verificado por `tests/test_siem.py`. |

Nota sobre la fuente: el enlace `.../log-data-collection/log-formats.html` del
enunciado devuelve **404** en la documentación actual; la información
equivalente está en la referencia de `localfile` y en la página del
decodificador JSON (enlazadas arriba). Las comprobaciones de esta nota se basan
en esas páginas y en el comportamiento observado en el propio Wazuh.

## Resultado de la prueba manual (`wazuh-logtest`)

| # | Evento real (archivo:línea) | Decodificador | Regla | Nivel | Campos decodificados |
|---|---|---|---|---|---|
| 1 | 2026-09-05:17 · C1 · bloqueado por `filtrado` | `json` | 100101 | 5 | todos, incl. `mecanismo_que_bloqueo` |
| 2 | 2026-09-07:2 · C3 · exitoso, con `latencia_clasificador_ms` | `json` | 100102 | 12 | todos, incl. `latencia_clasificador_ms` |
| 3 | 2026-09-13:6 · C4 · bloqueado por `minimo_privilegio`, sin vector | `json` | 100101 | 5 | todos (sin `vector_probado`) |
| 4 | 2026-09-25:22 · C6 · `aprobacion_humana` con `tiempo_revision_humana_ms` | `json` | 100101 | 5 | todos, incl. `tiempo_revision_humana_ms` |
| 5 | 2026-09-05:1 · C0 · permitido normal, `mecanismos_activos` vacío | `json` | 100100 | 3 | todos (sin `mecanismo_que_bloqueo`) |

Los 5 generan alerta. Además, en una prueba aparte con el proxy real y la
extensión V7 se activó la regla 100103 (herramienta simulada en la cola de
aprobación) y la 100104 (ráfaga); ver `LEEME.md`.

## Hallazgos

1. **Todos los valores llegan como cadenas en la alerta.** En el `alerts.json`
   del manager `latencia_ms` es `"15622"` y `es_extension` es `"true"`, no
   número ni booleano. No impide ingerir ni crear reglas (las comparaciones de
   Wazuh son de texto/regex), pero **una agregación numérica (p. ej. la latencia
   media) en el dashboard puede requerir convertir el tipo**; no se comprobó el
   mapeo del índice del dashboard. Para analizar latencias, usar el CSV/JSONL.
2. **`null` se decodifica como la cadena `"null"`** (comprobado con
   `wazuh-logtest`) y **un arreglo nativo llega como texto estilo Python**
   (`['filtrado', 'clasificacion']`). Por eso el exportador *omite* los campos
   nulos y *aplana* `mecanismos_activos` a `filtrado,clasificacion`; ambos
   cambios están verificados y cubiertos por tests. Efecto secundario
   documentado: en un evento sin `vector_probado` la descripción de la regla
   muestra «vector , config C4» (campo vacío); es cosmético.
3. **La hora de la alerta es la de ingesta, no la del evento.** El `timestamp`
   de la alerta es cuando Wazuh leyó la línea; la hora original viaja en
   `data.timestamp`. En ingesta en vivo coinciden; con un lote histórico la
   alerta aparecerá con la hora actual. Para análisis temporal usar
   `data.timestamp`.
4. **CEF: «No decoder matched».** Una línea CEF (`CEF:0|IronVeil|...`) pasada por
   `wazuh-logtest` no encuentra decodificador: Wazuh no trae uno por defecto. Su
   estructura (cabecera de 7 campos, severidad 0–10, una línea) sí es válida
   según la especificación CEF y se comprueba en los tests, pero **para Wazuh el
   formato a usar es el JSON**; CEF serviría para otro SIEM o requeriría un
   decodificador propio, que no se escribió.

## Qué no se validó

- Entrega por agente remoto o por syslog (solo lectura de archivo local desde
  el manager).
- La vista de eventos con los campos `data.*` en el dashboard y el mapeo de tipos
  del índice (el Overview sí muestra las alertas; ver `LEEME.md`).
- CEF contra un colector que sí lo entienda.
- El resto de los eventos del log (solo 5 de 13 102, elegidos para cubrir
  casos distintos; la validación estructural es automatizable sobre todos con
  `analisis/validar_formato_siem.py <archivo:línea> ...`).

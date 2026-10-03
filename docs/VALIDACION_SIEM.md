# Validación del formato de exportación SIEM (Wazuh)

> **Extensión opcional, fuera del núcleo de 7 configuraciones.** Es evidencia
> de que el log de IronVeil se puede integrar en un SOC real, no parte de la
> respuesta a la pregunta de investigación.

Tarea de la semana del 17 de octubre de 2026 (Fiquitiva): validar que la
salida de `exportar_a_siem()` (`proxy/siem.py`) sea compatible con lo que
Wazuh espera, usando 3-5 eventos **reales** del log del proyecto, y
contrastándola con la documentación oficial de Wazuh.

Validación hecha el 2026-10-02.

## 1. Qué exige Wazuh (documentación oficial, consultada el 2026-10-02)

| # | Requisito | Fuente |
|---|-----------|--------|
| R1 | El `log_format` `json` de `<localfile>` es para *"single-line JSON files"*: un objeto JSON por línea. | [localfile — log_format](https://documentation.wazuh.com/current/user-manual/reference/ossec-conf/localfile.html) |
| R2 | El decodificador JSON extrae cada campo para compararlo con las reglas. Soporta números, strings, booleanos, `null`, arrays y objetos; los campos anidados quedan con notación de punto (p. ej. `alert.signature_id` en el ejemplo de Suricata). | [JSON decoder](https://documentation.wazuh.com/current/user-manual/ruleset/decoders/json-decoder.html) |
| R3 | Se recomienda identificar el origen con una etiqueta (`<label key="@source">myapp</label>` en el ejemplo oficial). | [localfile — label](https://documentation.wazuh.com/current/user-manual/reference/ossec-conf/localfile.html) |
| R5 | *"An array of objects is not supported."* | [JSON decoder](https://documentation.wazuh.com/current/user-manual/ruleset/decoders/json-decoder.html) |
| — | `cef` **no** aparece entre los valores permitidos de `log_format`. | [localfile — log_format](https://documentation.wazuh.com/current/user-manual/reference/ossec-conf/localfile.html) |

La URL que cita el PDF de la semana para formatos de log
(`.../log-data-collection/log-formats.html`) devuelve 404 a la fecha de esta
validación; los requisitos se tomaron de las dos páginas de arriba.

## 2. Formato elegido

Por el último punto de la tabla, el formato **por defecto** de
`exportar_a_siem()` es JSON, no CEF:

```json
{"@source": "ironveil", "timestamp": "<ISO 8601>", "ironveil": { <evento completo del log> }}
```

- El evento va **anidado** bajo `ironveil`: en Wazuh sus campos quedan como
  `ironveil.resultado`, `ironveil.configuracion`, etc., sin chocar con
  campos propios de Wazuh como `timestamp` o `agent`.
- `@source` cumple la misma función que la etiqueta del ejemplo oficial
  (R3), y además viene dentro del propio evento, así que no depende de
  configurar `<label>` en el agente.
- `FormateadorCEF` existe para SIEM que sí ingieren CEF de forma nativa
  (ArcSight, Microsoft Sentinel vía syslog), no para Wazuh.

## 3. Resultado sobre eventos reales

Script reproducible: `python analisis/validar_formato_siem.py --n 5 --salida analisis/muestra_siem_wazuh.jsonl`.
Toma la muestra de `resultados/*/eventos.jsonl` (el log que escribe el
proxy, no los JSONL de los scripts de ataque) y garantiza que cubra los 3
valores de `resultado`. Las líneas exportadas quedan en
`analisis/muestra_siem_wazuh.jsonl`.

| Configuración | Vector | `resultado` | R1 | R2 | R3 | R4 (8 campos intactos) | R5 | CEF |
|---|---|---|---|---|---|---|---|---|
| C1 | V2-E | bloqueado | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| C0 | V2-B | exitoso_para_atacante | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| C0 | — (legítimo) | permitido_normal | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| C2 | V2-B | exitoso_para_atacante | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| C3 | V2-B | bloqueado (con `latencia_clasificador_ms`) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

**5/5 eventos válidos.** Ejemplo real (C1, bloqueado por filtrado):

```json
{"@source": "ironveil", "timestamp": "2026-09-05T17:47:43.650494+00:00", "ironveil": {"timestamp": "2026-09-05T17:47:43.650494+00:00", "configuracion": "C1", "mecanismos_activos": ["filtrado"], "vector_probado": "V2-E", "modelo_destino": "rrhh", "resultado": "bloqueado", "mecanismo_que_bloqueo": "filtrado", "latencia_ms": 3}}
```

Su versión CEF:

```
CEF:0|IronVeil|Proxy|0.1.0|bloqueado|IronVeil bloqueado|5|rt=1788630463650 cs1Label=configuracion cs1=C1 cs2Label=mecanismos_activos cs2=filtrado cs3Label=vector_probado cs3=V2-E cs4Label=modelo_destino cs4=rrhh cs5Label=mecanismo_que_bloqueo cs5=filtrado cn1Label=latencia_ms cn1=3
```

## 4. Problemas identificados y decisiones

1. **Arrays de objetos (R5).** El esquema actual solo tiene arrays de
   strings (`mecanismos_activos` y, en la extensión, `herramientas_invocadas`).
   Por eso `herramientas_invocadas` se diseñó como una **lista de nombres**
   y no como una lista de objetos `{nombre, estado}`. `exportar_a_siem()`
   rechaza con `ValueError` cualquier evento futuro que traiga un array de
   objetos, en vez de exportar algo que Wazuh no decodificaría.
2. **`null` y listas vacías.** C0 produce `mecanismos_activos: []` y
   `mecanismo_que_bloqueo: null`. Ambos son tipos soportados (R2); no se
   transforman.
3. **Saltos de línea dentro de valores** (p. ej. un `vector_probado`
   manipulado): `json.dumps` los escapa como `\n`, así que la línea sigue
   siendo una sola (R1). Hay una prueba unitaria para esto.

## 5. Lo que NO se validó

- **No se desplegó Wazuh.** El ítem "si el tiempo alcanza" de la tarea
  de Piedrahita (Wazuh en Docker recibiendo un lote real) no se hizo: el
  stack de Wazuh necesita varios GB de RAM extra y el laboratorio no lo
  tiene levantado. La validación es contra la documentación, no contra una
  ingesta real. Pendiente si el equipo lo decide; los pasos serían: monitorear
  un archivo escrito con `ConectorArchivoLocal` + `exportar_a_siem()` usando
  `<localfile><log_format>json</log_format>`, y probar con `wazuh-logtest`
  que los campos aparecen como `ironveil.*`.
- **El proxy no exporta en vivo.** `exportar_a_siem()` todavía no se llama
  desde `/chat` (ver docstring de `proxy/siem.py`); hoy la exportación es
  por lotes desde los JSONL ya escritos.

---
name: esquema-log
description: Valida y construye eventos de log y filas de resultados de IronVeil contra el esquema canónico de 8 campos. Úsala SIEMPRE que se escriba, modifique o lea un evento de log, se agregue una fila a resultados_template.csv, se cree un campo nuevo, o se escriba un script que consuma esos datos — aunque el usuario no mencione el esquema. También úsala antes de agregar cualquier columna o campo nuevo al log.
---

# Esquema de log de IronVeil

El esquema de log es el contrato más frágil del proyecto: lo escriben cuatro personas durante tres meses y todo el análisis de octubre depende de que sea consistente desde agosto. Un `"c1"` en minúscula en la semana 3 se paga en la limpieza de datos del 10 de octubre.

## Los 8 campos base

Formato: **JSON Lines** — un objeto JSON por línea, sin comas ni corchetes envolventes.

| Campo | Tipo | Valores permitidos | Ejemplo |
|---|---|---|---|
| `timestamp` | string | ISO 8601 **con offset de zona** | `"2026-09-05T14:32:11-05:00"` |
| `configuracion` | string | `C0`..`C6` exactamente, mayúscula, sin espacios | `"C1"` |
| `mecanismos_activos` | lista[string] | subconjunto de los 5 nombres canónicos | `["filtrado"]` |
| `vector_probado` | string | ID de `variantes_ataque.md` (`V<n>-<letra>`) | `"V3-A"` |
| `modelo_destino` | string | `soporte` \| `rrhh` | `"soporte"` |
| `resultado` | string | `bloqueado` \| `exitoso_para_atacante` \| `permitido_normal` | `"bloqueado"` |
| `mecanismo_que_bloqueo` | string \| null | uno de los 5 nombres, o `null` | `"filtrado"` |
| `latencia_ms` | int | milisegundos, entero | `812` |

**Nombres canónicos de mecanismo** (idénticos a las claves de `config.yaml`, sin tildes, en minúscula):
`filtrado`, `delimitacion`, `clasificacion`, `minimo_privilegio`, `aprobacion_humana`.

## Invariantes

Estas se verifican siempre, en el código que escribe y en el que valida:

1. `resultado == "bloqueado"` ⟺ `mecanismo_que_bloqueo != null`. Nunca uno sin el otro.
2. `mecanismo_que_bloqueo`, si no es `null`, está en `mecanismos_activos`. Un mecanismo apagado no puede haber bloqueado.
3. `mecanismos_activos` refleja `config.yaml` en el momento de la petición, no lo que se supone que debería estar activo.
4. `configuracion` es coherente con `mecanismos_activos`: `C0` ⇒ lista vacía; `C6` ⇒ los 5.
5. `latencia_ms` es el tiempo **total** de la petición. Las latencias parciales van en campos extendidos, nunca reemplazando esta.

## Campos extendidos

Se pueden agregar campos nuevos. **Nunca se renombran ni se eliminan los 8 base.** Los ya acordados:

| Campo | Tipo | Cuándo |
|---|---|---|
| `latencia_clasificador_ms` | int | mecanismo 3 activo |
| `tiempo_revision_humana_ms` | int | petición que pasó por la cola |
| `tipo_variante` | `original` \| `nueva` | V3 desde la semana del 12 de septiembre |
| `paso_bloqueado` | `1` \| `2` \| null | V4 (movimiento lateral) |
| `nivel_carga` | int | V5 (peticiones concurrentes) |
| `es_extension` | bool | resultados fuera del núcleo de 7 configuraciones |

**Antes de inventar un campo nuevo:** revisa si uno de estos ya cubre el caso, y avisa al equipo. Un campo que solo entiende quien lo escribió es ruido en el dataset.

## Al escribir un evento

- El log lo escribe **el endpoint**, nunca la función del mecanismo. Los mecanismos deciden; el endpoint registra. Esto mantiene los mecanismos puros y testeables.
- Un evento por intento individual, no un resumen por configuración. La granularidad se pierde para siempre si no se registra en el momento.
- `timestamp` con `datetime.now(timezone.utc).astimezone().isoformat()` o equivalente con zona explícita. Nunca un datetime naive ni `time.time()` crudo.
- Serializar con `json.dumps(evento, ensure_ascii=False)` + `"\n"`, un `write` por línea.

## Al validar

Cuando escribas o modifiques `validar_dataset.py`, o cualquier lector del CSV, cubre como mínimo:

- Campos faltantes o vacíos entre los 8 base.
- `configuracion` fuera del conjunto permitido, o con variantes de caso/espacios (`"c1"`, `"C1 "`, `"C 1"`).
- `resultado` con un valor fuera de los tres permitidos.
- Las invariantes 1 y 2 de arriba.
- `timestamp` no parseable o sin offset.
- Filas duplicadas exactas.

El validador **reporta, no corrige**. Cada corrección la decide un humano y queda en `LIMPIEZA_DATOS.md`. Ninguna fila se borra: se mueve a `descartados.csv` con la razón.

## Checklist antes de dar por terminado

- [ ] El evento tiene los 8 campos base, con los tipos exactos.
- [ ] Las 5 invariantes se cumplen.
- [ ] Los nombres de mecanismo coinciden con las claves de `config.yaml`.
- [ ] Si se agregó un campo nuevo: está documentado en `CLAUDE.md` y avisado al equipo.
- [ ] Hay un test que verifica el evento generado contra el esquema.
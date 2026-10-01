# Limpieza de datos — `resultados_template.csv`

> Revisión de calidad de datos del dataset acumulado desde el 2026-09-05
> hasta el 2026-09-30 (29 135 filas antes de esta tarea, 7 configuraciones,
> datos de 5 personas-semana de ejecución). Objetivo: dejar el dataset
> limpio y documentado antes de que Fiquitiva construya las tablas y
> gráficas finales (ya construidas en una primera versión la semana
> pasada, ver `analisis/tabla_maestra.md`; esta limpieza las deja
> consistentes, no las rehace).
>
> Herramientas nuevas de esta tarea:
> - `analisis/validar_dataset.py` — **reporta**, nunca corrige. Reutilizable
>   sin cambios cuando se agreguen los resultados de la extensión opcional
>   del 17 de octubre (no asume un tamaño ni un conjunto de configuraciones
>   fijo).
> - `analisis/limpiar_dataset.py` — aplica, de forma reproducible, **solo**
>   las dos correcciones que no requieren una decisión humana caso por
>   caso (ver sección 2). Todo lo demás se deja intacto a propósito.

## 1. Metodología

1. Se corrió `python analisis/validar_dataset.py` contra el dataset
   completo (antes de cualquier cambio) y se inspeccionó cada hallazgo a
   mano contra el CSV crudo y, cuando hizo falta, contra los JSONL de
   `resultados/<fecha>/` para entender su origen real — no se asumió
   ninguna causa sin verificarla.
2. Cada hallazgo se clasificó en una de tres categorías:
   - **Corregible sin ambigüedad**: la corrección es la única lectura
     posible de los datos (sección 2) — se corrigió con
     `analisis/limpiar_dataset.py`.
   - **Hallazgo real, pero no corregible esta semana sin una decisión del
     equipo o sin rehacer trabajo de otra tarea** (sección 3) — se
     documenta, no se inventa una corrección.
   - **Esperado por diseño, no es un error** (sección 4) — se documenta
     para que `validar_dataset.py` no lo vuelva a reportar como ruido.
3. Ninguna fila se borró sin dejar rastro (regla 4 de `CLAUDE.md`): las
   únicas filas que salieron de `resultados_template.csv` se movieron a
   `resultados/descartados.csv` con razón y fecha.

## 2. Corregido esta semana (`analisis/limpiar_dataset.py`)

### 2.1. `mecanismo_que_bloqueo` con placeholder no canónico

7 filas, todas con `configuracion=C3` y `mecanismos_activos=clasificacion`
(semana del 2026-09-18, ver `docs/FUENTE_DE_VERDAD.md`), traían
`mecanismo_que_bloqueo = "desconocido (ver eventos.jsonl del proxy para
el mecanismo exacto)"` en vez de un nombre canónico — el script de ataque
de esa semana no estaba seguro de a qué mecanismo atribuir el bloqueo.

**No es ambiguo**: en C3 el único mecanismo activo es `clasificacion`
(invariante 4 del esquema de log — ver `MECANISMOS_ESPERADOS_POR_CONFIG`
en `analisis/validar_dataset.py`). Con un solo mecanismo activo y
`resultado=bloqueado`, ese mecanismo es necesariamente el que bloqueó; no
hace falta mirar `eventos.jsonl` para saberlo. `corregir_mecanismo_desconocido()`
aplica esta regla exactamente — y **solo** cuando `mecanismos_activos`
tiene un único elemento; si alguna vez aparece el mismo placeholder con 2+
mecanismos activos, la función lo deja intacto y lo reporta aparte (no
hay forma de adivinar cuál de los dos bloqueó sin el log del proxy).

Filas corregidas (`clasificacion` en las 7): `V2-B`, `V3-A`, `V3-D`,
`V3-G`, `V3-C`, `V4-A-paso1`, `V4-B-paso1`, todas del 2026-09-18.

### 2.2. Filas duplicadas exactas

13 filas (de 29 135) eran idénticas carácter por carácter a otra fila del
mismo CSV — las 14 columnas coinciden, incluida `latencia_ms` al
milisegundo — todas `configuracion=C0`, `vector_probado=V5-D`, del
2026-09-22. Dos eventos de V5 (ráfaga de carga) con exactamente el mismo
timestamp con microsegundos y exactamente la misma latencia no son un
resultado plausible de dos peticiones reales distintas; es mucho más
probable que `analisis/agregar_resultados_desde_jsonl.py` haya leído el
mismo archivo `.jsonl` dos veces en alguna sesión de esa semana (dos
invocaciones del script sobre el mismo archivo, o el mismo archivo
presente en dos rutas).

`mover_duplicados_exactos()` conserva la primera aparición de cada evento
y mueve las 13 copias restantes a `resultados/descartados.csv` con
`razon_descarte="duplicado exacto (probable reingesta del mismo evento
jsonl)"` y `fecha_descarte` con la fecha de esta limpieza.

### Resultado

`resultados_template.csv`: 29 135 → **29 122 filas** (13 movidas a
`descartados.csv`, 0 borradas). Downstream regenerado para que no quede
desactualizado: `analisis/consolidar.py` y `analisis/tabla_maestra.py`
corridos de nuevo (el único número que cambió de forma visible es el ASR
promedio de C0, 64.4% → **64.3%**, un movimiento de 0.1 puntos porcentuales
nada más — las 13 filas eran todas del mismo vector/configuración y el
resultado `exitoso_para_atacante` ya estaba representado por su original;
actualizado también en `analisis/conclusion_borrador.md`).

Reproducible con:

```bash
python analisis/validar_dataset.py   # confirma los hallazgos antes de corregir
python analisis/limpiar_dataset.py   # aplica las 2 correcciones de esta sección
python analisis/validar_dataset.py   # confirma que ya no aparecen (exit code 0)
python analisis/consolidar.py
python analisis/tabla_maestra.py
```

## 3. Hallazgos reales, pendientes de decisión (NO corregidos)

### 3.1. `latencia_clasificador_ms` vacío en el 100% de las filas con `clasificacion` activa

**10 304 filas** (todo C3 + todo C6, es decir, cada fila donde
`clasificacion` está activa) tienen `latencia_clasificador_ms` vacío —
incluido C3, donde `clasificacion` es el único mecanismo y prácticamente
siempre se ejecuta. Esto contradice lo documentado en
`docs/FUENTE_DE_VERDAD.md` (entrada del 2026-09-06): el proxy sí mide y
loggea este campo.

**Causa real, verificada, no solo sospechada:** el dataset consolidado se
construye con `analisis/agregar_resultados_desde_jsonl.py` a partir de los
JSONL que escriben los **scripts de ataque** (`ataques/vectores_1_2_3.py`,
`vector4_movimiento_lateral.py`, `vector5_carga.py`) — estos son
clientes HTTP que solo pueden medir el tiempo de ida y vuelta de su propia
petición (`latencia_ms`). El desglose interno `latencia_clasificador_ms`
solo existe en el log que escribe **el proxio mismo**
(`resultados/<fecha>/eventos.jsonl`, vía `_registrar_evento()`), que nunca
se fusionó con el dataset consolidado. Verificado directamente:

```bash
grep -c "latencia_clasificador_ms" resultados/2026-09-07/eventos.jsonl
# 30 — el proxy sí lo registró, con valores reales (992, 1538, 1560...)
grep -c "latencia_clasificador_ms" resultados/2026-09-07/vectores_1_2_3_C3_195114.jsonl
# 0 — el script de ataque de esa misma sesión nunca lo tuvo
```

**No se corrige esta semana.** Cruzar ambos streams de eventos (atacante
y proxy) por timestamp más cercano + `configuracion`/`vector_probado` es
una tarea con riesgo real de emparejar mal dos filas (dos peticiones
con timestamps muy cercanos durante V5), y no es una decisión que
corresponda tomar unilateralmente en una tarea de limpieza de datos. Se
deja como hallazgo documentado; si el equipo decide que vale la pena,
es una tarea aparte de ingeniería de datos (posiblemente de Fiquitiva,
dueña de la consolidación), no una "corrección" de esta semana. No
bloquea `analisis/tabla_maestra.py` (esa tabla nunca usó esta columna,
solo `latencia_ms` total).

### 3.2. `paso_bloqueado` ambiguo en eventos de V4 "paso 2 omitido"

**Ya documentado en `docs/FUENTE_DE_VERDAD.md` (entrada 2026-09-13)**,
confirmado todavía abierto esta semana: cuando el paso 1 de V4 (movimiento
lateral) bloquea y el paso 2 se omite (nunca se envía una credencial
vacía o inventada — regla ya establecida), el evento del paso 2 hereda el
mismo `paso_bloqueado` que el paso 1 en vez de quedar vacío o marcar
explícitamente la omisión. Afecta **4 filas** actualmente (`V4-A-paso2`
y `V4-B-paso2` en C3 y C6).

Ejemplo concreto (fila con índice 113 del CSV actual):

| vector_probado | resultado | mecanismo_que_bloqueo | paso_bloqueado |
|---|---|---|---|
| V4-A-paso1 | bloqueado | (variable según config) | 1 |
| V4-A-paso2 | permitido_normal | (vacío — paso omitido) | **1** ← ambiguo |

**Pendiente de confirmar con Sabogal** (autor de los scripts de V4) cómo
debería representarse: ¿`paso_bloqueado` vacío en el evento de "paso 2
omitido", o un tercer valor explícito tipo `"omitido"` en vez de reusar
`1`/`2`? Cualquiera de las dos es una decisión de esquema de log (afecta
el contrato de 4 personas), no algo que se deba decidir en esta tarea de
limpieza sin avisar al equipo (sección 8 de `CLAUDE.md`).

## 4. Esperado por diseño (no son errores)

Estos valores parecían "raros" en la primera pasada de
`analisis/validar_dataset.py`, pero tienen una explicación documentada y
`validar_dataset.py` ya los trata como tal (no los reporta como error):

- **`modelo_destino = "proxy"` o `"noexiste"`** (28 y 7 filas): solo en
  vectores `V1-*` (reconocimiento) — V1 no llama a un modelo real: prueba
  el proxy en sí (`"proxy"`) o un nombre de modelo deliberadamente
  inexistente para verificar el manejo de error (`"noexiste"`,
  `V1-D`). `validar_dataset.verificar_modelo_destino_dominio()` excluye
  explícitamente los vectores V1 de esta verificación.
- **`tiempo_revision_humana_ms` vacío en el 100% de filas con
  `aprobacion_humana` activa** (28 613 filas): ya documentado en
  `docs/FUENTE_DE_VERDAD.md` (entrada 2026-09-13) — los scripts de ataque
  nunca esperan a que un humano revise antes de responder
  (`enviar_a_revision()` no es bloqueante), así que esta métrica es
  genuinamente no medible con la batería automatizada actual. No es un
  dato faltante por accidente.
- **`es_extension` vacío en el 100% de las filas**: correcto — este campo
  es para resultados de la extensión opcional, que empieza el 17 de
  octubre y todavía no se ha ejecutado.
- **Ningún nombre de `configuracion` ni de mecanismo con variantes de
  mayúscula o espacios** (`"c1"`, `"C1 "`, etc.): se revisó explícitamente
  y el dataset actual no tiene ninguna — a diferencia de lo que advertía
  la tarea como riesgo típico, en este caso las 4 personas fueron
  consistentes desde la semana 1. Documentado porque es un resultado
  honesto (negativo), no para rellenar espacio (regla 5 de `CLAUDE.md`:
  no se fuerza un hallazgo que no está).
- **Timestamps**: los 29 135 parsean como ISO 8601 con offset explícito,
  dentro del rango agosto-noviembre 2026, y en orden no decreciente a lo
  largo de todo el archivo. Sin hallazgos aquí tampoco.

## 5. Cómo volver a correr esta validación

```bash
python analisis/validar_dataset.py
```

Exit code `0` si no hay hallazgos de severidad `error` (los de severidad
`advertencia`/`info` de la sección 3 de este documento son esperados y no
hacen fallar el comando — son decisiones pendientes del equipo, no bugs).
Reutilizable sin cambios para la extensión del 17 de octubre: no asume
qué configuraciones o cuántas filas trae el CSV.

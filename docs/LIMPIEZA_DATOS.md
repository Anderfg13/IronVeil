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

### 3.1. `latencia_clasificador_ms` — recuperado parcialmente con `analisis/fusionar_latencia_clasificador.py`

**Actualizado tras una segunda pasada** (el usuario pidió explícitamente
ver si el dato se podía medir de verdad, en vez de dejarlo solo
documentado). Como se sospechaba: el proxy **sí** mide y loggea este
campo — solo nunca se había fusionado con el dataset consolidado, porque
`resultados_template.csv` se construye con
`analisis/agregar_resultados_desde_jsonl.py` a partir de los JSONL que
escriben los **scripts de ataque** (clientes HTTP, que solo pueden medir
el tiempo de ida y vuelta de su propia petición), mientras que el
desglose interno `latencia_clasificador_ms` solo existe en el log que
escribe **el proxy mismo** (`resultados/<fecha>/eventos.jsonl`, vía
`_registrar_evento()`). Verificado directamente antes de tocar nada:

```bash
grep -c "latencia_clasificador_ms" resultados/2026-09-07/eventos.jsonl
# 30 — el proxy sí lo registró, con valores reales (992, 1538, 1560...)
grep -c "latencia_clasificador_ms" resultados/2026-09-07/vectores_1_2_3_C3_195114.jsonl
# 0 — el script de ataque de esa misma sesión nunca lo tuvo
```

**`analisis/fusionar_latencia_clasificador.py`** (nuevo, reproducible)
cruza ambos logs por `(fecha UTC, configuracion, vector_probado,
modelo_destino)`, empareja por orden de timestamp dentro de cada grupo, y
**solo fusiona un grupo si el conteo coincide exacto Y
`mecanismo_que_bloqueo` coincide en cada posición emparejada** — dos
capas de verificación antes de confiar en el cruce, no solo una.
Resultado real sobre el dataset completo:

| Categoría | Filas |
|---|---|
| Fusionadas con éxito | **39** |
| Sin evento del proxy para cruzar (semanas sin `eventos.jsonl` preservado, p. ej. 2026-09-18) | 153 |
| Conteo de grupo no coincide (no se adivina) | 2 |
| `mecanismo_que_bloqueo` no coincide — sospechoso, NO fusionado (ver 3.3) | 13 |

**V5-D sigue irrecuperable, y no es un problema de cruce**: revisando
`eventos.jsonl` directamente, el proxy **nunca** registró
`latencia_clasificador_ms` en ningún evento de V5 (0 de miles) — la
medición simplemente no se capturó del lado del servidor durante las
ráfagas de carga concurrente. De las 10 304 filas con `clasificacion`
activa, 10 265 siguen vacías (casi todas V5-D); no hay ningún dato oculto
por recuperar ahí.

Reproducible con:

```bash
python analisis/fusionar_latencia_clasificador.py
```

No bloquea `analisis/tabla_maestra.py` (esa tabla nunca usó esta columna,
solo `latencia_ms` total) y no se regeneraron sus salidas por este cambio.

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

### 3.3. `mecanismo_que_bloqueo` no coincide con el log del proxio para 13 filas de la semana del 2026-09-18/19

**Hallazgo nuevo, descubierto al validar el cruce de la sección 3.1**, no
una sospecha previa. Al comparar `mecanismo_que_bloqueo` entre
`resultados_template.csv` y el `eventos.jsonl` del proxy para la misma
petición física (mismo `vector_probado`/`configuracion`/`modelo_destino`,
timestamps a menos de 1.5 segundos de distancia — confirmado que es la
misma petición, no un cruce casual), **13 filas** (índices CSV `[97, 98,
99, 101, 104, 106, 108, 109, 110, 111, 149, 152, 164]`, todas de la sesión
del 2026-09-18 noche / 2026-09-19 madrugada UTC) muestran un desacuerdo:
el CSV dice que nada bloqueó la petición (`resultado=permitido_normal`,
`mecanismo_que_bloqueo` vacío) pero el log del proxio para esa misma
petición dice `mecanismo_que_bloqueo="clasificacion"`.

**No se corrigió.** `analisis/fusionar_latencia_clasificador.py` detecta
este desacuerdo automáticamente y **se abstiene** de fusionar
`latencia_clasificador_ms` en esas 13 filas (quedó documentado en la
tabla de la sección 3.1) — exactamente el comportamiento diseñado: ante
un desacuerdo en un campo que debería ser objetivo, no confiar en el
cruce para ningún campo, ni siquiera para el que se estaba buscando.

**Posible relación con un bug ya documentado y corregido, sin confirmar
que sea la misma causa:** `docs/FUENTE_DE_VERDAD.md` (entrada
2026-09-18, "Re-ejecución de V1-V5...") documenta que esa misma noche se
encontró y corrigió un bug real en `ataques/vectores_1_2_3.py` y
`vector4_movimiento_lateral.py`: no reconocían el status `429`
(aprobación humana encolando) y lo contaban como `permitido_normal` por
caer en la rama de "respuesta inesperada". Es plausible que una variante
del mismo patrón de bug (una rama de "respuesta inesperada" que no
reconocía correctamente el status de un bloqueo por `clasificacion`)
afectara también a estas 13 peticiones — pero **esto no está confirmado,
solo es una hipótesis razonable** basada en la cercanía temporal y el
patrón de síntoma idéntico (el CSV subestima bloqueos como
`permitido_normal`). Confirmarlo requeriría revisar el código de
`ataques/vectores_1_2_3.py` tal como estaba esa noche específica (antes o
después del fix documentado), que no es el alcance de esta tarea.

**Pendiente de confirmar con Sabogal:** si la hipótesis de arriba es
correcta, estas 13 filas de `resultados_template.csv` tendrían
`resultado`/`mecanismo_que_bloqueo` incorrectos (no solo
`latencia_clasificador_ms` faltante) y habría que decidir si se corrigen
con el mismo criterio que la sección 2.1 (un único mecanismo activo que
pudo haber bloqueado) o si se re-verifican contra `eventos.jsonl` una por
una antes de tocarlas — no se tomó esa decisión unilateralmente aquí.

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

Si se agregan más `eventos.jsonl` nuevos (semanas futuras) y se quiere
intentar recuperar más `latencia_clasificador_ms`, se puede volver a
correr:

```bash
python analisis/fusionar_latencia_clasificador.py
```

Es seguro correrlo las veces que haga falta: solo toca filas con
`latencia_clasificador_ms` vacío y nunca sobrescribe un valor que ya esté
poblado.

## 6. Re-corrida GPU del 2026-10-02 (C0-C5, V1-V4) y cambio de criterio de ASR

**Qué se hizo.** Se re-corrieron V1-V4 en C0-C5 en Colab (GPU T4, proxy con
calentamiento + `keep_alive` + conexión reutilizada). Las 146 filas viejas
de V1-V4 de C0-C5 (CPU) se movieron a `descartados.csv` con
`analisis/mover_a_descartados.py --vector-base V1 V2 V3 V4` (opción nueva:
descarta por configuración *y* vector; V5 no se tocó). Se ingestaron 163
filas nuevas (`resultados/2026-10-02/`), se aplicó `limpiar_dataset.py` (9
`mecanismo_que_bloqueo` "desconocido" corregidos, config de un solo
mecanismo) y `fusionar_latencia_clasificador.py` (20 filas con
`latencia_clasificador_ms`, ahora sí con `eventos.jsonl` del proxy de esa
corrida).

**Hallazgo: las filas viejas de C0-C2 no eran comparables con las de C3-C6.**
La primera semana (2026-09-05/07) el ASR de C0-C2 salió del `resultado` que
escribe el proxy ("nada lo bloqueó"), mientras que los scripts de ataque
posteriores puntúan por fuga *verificada por contenido*
(`_resultado_desde_chat`). Al reemplazar C0-C2 con filas del criterio
vigente, V3 en C0 pasa de 100% a 0%: `llama3.2:1b` no revela el secreto ante
esas inyecciones, así que no hay ASR que un mecanismo pueda reducir (efecto
suelo). Varias celdas de la matriz de hipótesis que parecían "Sí (directo)"
(p. ej. V3 × Clasificación) eran artefacto de comparar 100% (criterio viejo)
contra 0% (criterio nuevo).

**Otros hechos de la corrida:**
- V1 da 40% idéntico en las 7 configuraciones: son `V1-A`/`V1-C` (Ollama
  alcanzable directo en la VM), una propiedad del entorno, no de ningún
  mecanismo — confirma lo que ya se sospechaba.
- n por celda es muy chico (V2: 5, V4: 6, V3: 9-12): una diferencia de un
  evento mueve el ASR 8-20 puntos. Por eso la segunda corrida repite 3 veces.
- La latencia mediana de C0-C5 baja a 53-238 ms (antes 0.5-12.7 s en CPU).
  C6 (683 ms) viene de la corrida anterior, con otra versión del código, y no
  es comparable hasta repetirla.
- La latencia por configuración mezcla peticiones bloqueadas (rápidas) con
  las que llegan al modelo; C5 sale la más "rápida" porque bloquea más.
- La tabla maestra ahora promedia el ASR solo sobre V1-V4 (los únicos
  presentes en las 7 configuraciones) y muestra V5 en columna aparte.
- `timestamp_desordenado` (advertencia de `validar_dataset.py`): las filas
  nuevas se agregaron por archivo, V4 después de V1-V3; no es un error de
  reloj.

### 6.1. Segunda corrida (2026-10-03): C0-C6 × 3 repeticiones

`resultados/RECORRIDA_GPU_C0_C6.ipynb` (mismo código del proxy que la
primera). 567 filas nuevas (`resultados/2026-10-03/`); las 53 filas viejas de
C6 V1-V4 (Podman/CPU del 2026-09-18 y GPU con el proxy anterior del
2026-09-30) se movieron a `descartados.csv`; V5 y V6 de C6 intactos. Se
**conservaron** las filas de la primera corrida de C0-C5 (mismo hardware y
código): quedan C0-C5 con 4 repeticiones y C6 con 3. `limpiar_dataset.py`
corrigió 30 `mecanismo_que_bloqueo` "desconocido" (configuraciones de un solo
mecanismo); `fusionar_latencia_clasificador.py` recuperó 99 `latencia_clasificador_ms`
en total.

**Cambios de análisis derivados** (detalle en `analisis/resultados_finales.md`):
- Latencia mediana: ahora solo de peticiones de chat V2-V4 que llegan al
  modelo. La versión anterior incluía sondeos de V1 (0-20 ms) y eventos de
  "paso 2 omitido" de V4 (`latencia_ms=0`, nunca se envió nada), que hacían
  parecer muy rápidas a C5/C6.
- Matriz real: celdas con k/n y valor p de Fisher; guarda de significancia
  (solo baja etiquetas). V4 se reporta también por pasos
  (`analisis/v4_ataque_completo.md`).
- Los bloqueos en *salida* (el proxy responde 200 con texto retenido) no los
  ve el script de ataque; por eso 6 filas de C6 no cruzan contra el log del
  proxy (`fusionar_latencia_clasificador.py` se abstiene).

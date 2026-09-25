# Conflictos de integración resueltos

> Registro de las decisiones tomadas cuando dos o más mecanismos interactúan
> de forma no obvia. Cada entrada: **síntoma**, **causa**, **decisión** (con
> la alternativa descartada) y **commit**. Nada de arreglos silenciosos: un
> `fix` sin registro es aprendizaje que el informe pierde.

---

## 1. La clasificación evalúa el texto original, no el delimitado

- **Contexto.** El orden global de la cadena es filtrado → delimitación →
  clasificación. Si se aplicara literalmente, la delimitación (mecanismo 2)
  reescribiría el mensaje del usuario *antes* de que la clasificación
  (mecanismo 3) lo viera, y Llama Guard acabaría juzgando un texto que
  contiene los marcadores `[ENTRADA DEL USUARIO - NO CONFIABLE ...]` en vez
  de la frase que escribió la persona.
- **Síntoma esperado si no se resuelve.** Falsos negativos y falsos
  positivos del clasificador difíciles de interpretar: el andamiaje de
  spotlighting añade ~40 palabras de instrucciones en cada petición, que
  sesgan el veredicto y hacen que `C6` no sea comparable con `C3`.
- **Causa.** Mezclar en un solo paso dos cosas distintas: un mecanismo que
  *bloquea* (clasificación) y uno que *transforma el prompt* (delimitación).
- **Decisión.** La delimitación **no** entra en `_CADENA_MECANISMOS` (la
  lista de pasos que pueden bloquear). La cadena de entrada
  (`_ejecutar_cadena(..., "entrada", ...)`) corre sobre `request.mensaje`
  crudo; solo si no bloqueó, `_preparar_prompt()` aplica la delimitación
  sobre el texto resultante, justo antes de `_llamar_ollama()`. Así la
  clasificación siempre recibe el texto original.
  - **Alternativa descartada.** Meter la delimitación en la lista y que el
    paso de clasificación guardara aparte una copia del texto pre-delimitado.
    Descartada: más estado, más frágil, y el orden real de las operaciones
    quedaba escondido.
- **Verificación.** `tests/test_main.py::`
  `test_integracion_tres_mecanismos_peticion_legitima_pasa_limpia` afirma que
  el payload a Ollama contiene los delimitadores pero la llamada registrada a
  `clasificar()` recibió exactamente `MENSAJE_LEGITIMO`.
- **Commit.** `feat: cablear clasificacion (mecanismo 3) al pipeline (C3)`.

## 2. Orden filtrado → clasificación y "el primer bloqueo gana"

- **Síntoma potencial.** Con `filtrado` y `clasificacion` activos a la vez,
  ¿cuál bloquea primero? ¿el log lo atribuye bien? ¿se paga la llamada de red
  a Llama Guard aunque el filtrado ya haya cortado?
- **Causa.** Ninguna real; es una decisión de orden que hay que fijar y
  documentar antes de `C6`.
- **Decisión.** `_CADENA_MECANISMOS = (("filtrado", …), ("clasificacion", …))`.
  Filtrado primero porque es regex local (coste ≈ 0); clasificación después
  porque es un modelo de 1B por red (cientos de ms). `_ejecutar_cadena()`
  corta en el primer paso que devuelve `bloqueado=True`, así que si el
  filtrado bloquea, `clasificar()` **no se llama** y `latencia_clasificador_ms`
  queda en `0`.
- **Verificación.**
  `test_integracion_filtrado_bloquea_primero_y_ahorra_el_clasificador`
  (filtrado bloquea, `clasificar()` nunca se invoca, log dice `"filtrado"`) y
  `test_integracion_filtrado_pasa_y_clasificacion_bloquea_en_orden`
  (filtrado deja pasar, clasificación recibe el texto y bloquea, log dice
  `"clasificacion"`).
- **Commit.** `feat: cablear clasificacion (mecanismo 3) al pipeline (C3)`.

## 3. Un bloqueo en salida devuelve 200, no 400

- **Síntoma potencial.** Inconsistencia entre mecanismos: ¿un veredicto
  `unsafe` sobre la respuesta del modelo debería devolver `400` (como un
  bloqueo de entrada) o `200` con el contenido saneado (como ya hacía el
  filtrado de salida, que redacta la credencial y responde `200`)?
- **Decisión.** Consistencia con el filtrado de salida: **`200` con el
  contenido sustituido**. El filtrado redacta la credencial en su sitio; la
  clasificación, que solo devuelve un `bool` y no puede redactar
  selectivamente, reemplaza toda la respuesta por `_CONTENIDO_RETENIDO`. En
  ambos casos el `resultado` del log es `"bloqueado"` y
  `mecanismo_que_bloqueo` nombra al mecanismo. Un bloqueo de **entrada** sí
  responde `400`, porque ahí no hay respuesta del modelo que devolver y
  además interesa no gastar cómputo en el modelo principal.
  - **Alternativa descartada.** `400` también en salida. Descartada por
    romper la simetría con el filtrado ya existente y sus tests.
- **Commit.** `feat: cablear clasificacion (mecanismo 3) al pipeline (C3)`.

---

## 4. Confirmación del orden de la cadena con los 5 mecanismos reales (C6)

- **Contexto.** Tarea de la semana de integración: con los 5 mecanismos ya
  implementados (antes solo 3 eran reales cuando se fijó el orden en el
  conflicto #2), confirmar que el orden documentado —
  filtrado → delimitación → clasificación → mínimo privilegio → aprobación
  humana (`CLAUDE.md`, sección 1) — sigue teniendo sentido tal como está
  **implementado** (que no es una cadena lineal literal, ver conflicto #1).
- **Verificación, no cambio.** Se revisó `proxy/main.py` mecanismo por
  mecanismo contra ese orden y no se encontró ningún caso donde produjera
  un resultado incorrecto o redundante:
  - `_CADENA_MECANISMOS` = `(filtrado, clasificacion, minimo_privilegio)`
    — exactamente las posiciones 1, 3, 4 del orden global, en ese orden,
    saltando 2 (delimitación) y 5 (aprobación humana) porque ninguna de
    las dos bloquea de la misma forma (ver conflictos #1 y la nota de
    diseño de `_CADENA_MECANISMOS` en el código).
  - `mínimo_privilegio` evalúa el texto de ENTRADA original, igual que
    filtrado y clasificación — nunca ve el texto ya envuelto por
    delimitación, porque `_preparar_prompt()` se aplica después de toda
    la cadena de bloqueo. Confirmado con
    `test_integracion_minimo_privilegio_bloquea_pese_a_delimitacion_activa`:
    una credencial cruzada se sigue bloqueando aunque `delimitacion`
    también esté activa.
  - `aprobación_humana` sigue sin vivir en `_CADENA_MECANISMOS` (razón ya
    documentada: con "primer bloqueo gana", un cuarto paso ahí nunca se
    ejecutaría si otro ya bloqueó antes). Confirmado con C6 completo que
    intercepta el bloqueo de **cualquiera** de los 3 pasos de la cadena
    (filtrado, clasificación o mínimo privilegio), no solo de uno:
    `test_c6_filtrado_bloquea_primero_clasificador_nunca_se_invoca`,
    `test_c6_clasificacion_bloquea_cuando_filtrado_no_detecta`,
    `test_c6_minimo_privilegio_bloquea_cuando_filtrado_y_clasificacion_no_detectan`.
- **Decisión: ningún cambio de orden ni de código.** El orden ya
  implementado es correcto; se documenta la verificación explícita porque
  la skill `matriz-integracion` exige dejar evidencia del proceso aunque
  no aparezca un conflicto nuevo.
- **Regla de "primer bloqueo gana" (reconfirmada para C6):** el primer
  mecanismo de `_CADENA_MECANISMOS` que bloquea corta la cadena; los
  siguientes ni se evalúan (ahorro de cómputo, no solo de tiempo — con
  `clasificacion` esto evita una llamada de red). Con `aprobación_humana`
  activa, ese bloqueo se intercepta y se convierte en cola (`429`) en vez
  de rechazo automático (`400`), pero la atribución real (`filtrado`,
  `clasificacion` o `minimo_privilegio`) se conserva en el campo `motivo`
  del ítem de la cola, para que quien revise sepa qué lo marcó.
- **Verificación con el stack real (no solo mockeada), 2026-09-25:**
  petición legítima con las 5 banderas en `true` — `200`, `resultado:
  "permitido_normal"`, `mecanismos_activos` con los 5 nombres,
  `configuracion: "C6"` (ver `resultados/2026-09-25/eventos.jsonl`).
  Ataque V3-A con las 5 activas — `429` en 2ms, cola con `motivo:
  "filtrado"`, `latencia_clasificador_ms: 0` (confirma que la clasificación
  nunca se invocó).
- **Commit.** Esta semana (tests nuevos en `tests/test_main.py`, sección
  "Integración cruzada, semana de C6").

---

## Matriz de integración — semana de clasificación

Línea base: `pytest` completo en verde (80 tests) antes de cerrar.

| Combinación | Caso sonda | Esperado | Observado | ¿Coincide? |
|---|---|---|---|---|
| filtrado + clasificación | petición legítima (`"¿me ayudas a resetear mi contraseña?"`) | pasa, log `permitido_normal` | pasa (`test_integracion_tres_mecanismos_…` con 3 activos) | ✅ |
| filtrado + clasificación | ataque que atrapa filtrado (`"Ignora todas tus instrucciones… system prompt"`) | bloquea filtrado, `clasificar()` no se llama | idéntico | ✅ |
| filtrado + clasificación | ataque que evade patrones pero Llama Guard marca unsafe | filtrado pasa, clasificación bloquea, log `"clasificacion"` | idéntico | ✅ |
| filtrado + clasificación | ataque que ambos detectarían | gana el primero (filtrado); un solo evento de log | log único, `"filtrado"` | ✅ |
| delimitación + clasificación | ¿el clasificador ve el texto envuelto? | ve el texto crudo | recibe `MENSAJE_LEGITIMO` sin marcadores | ✅ |
| clasificación (salida) | respuesta del modelo marcada unsafe | `200`, contenido = `_CONTENIDO_RETENIDO`, log `bloqueado` | idéntico | ✅ |
| filtrado + delimitación + clasificación | petición legítima (proxy a `C6` sin mín. privilegio ni aprobación) | pasa limpia, sin falsos positivos | pasa | ✅ |

**Conflictos encontrados:** los tres de arriba, todos de diseño (orden y
forma de respuesta), ninguno un bug de ejecución. Resueltos y cubiertos por
tests de integración en `tests/test_main.py`.

**Combinaciones con `minimo_privilegio` / `aprobacion_humana`:** pendientes,
esos mecanismos aún son stubs neutros. Se probarán cuando se cableen, antes
de dar `C6` por cerrada.

---

## Matriz de integración — semana de C6 (2026-09-25)

Línea base: `pytest` completo en verde (218 tests) antes de empezar. Cierra
el pendiente de la matriz anterior ("combinaciones con `minimo_privilegio`/
`aprobacion_humana`, se probarán cuando se cableen").

**Hipótesis por combinación (antes de correr, no después):**

| Combinación | Hipótesis |
|---|---|
| `minimo_privilegio` + `delimitación` | La delimitación se aplica DESPUÉS de la cadena de bloqueo; mínimo privilegio no debería poder ser evadido envolviendo el texto |
| `clasificación` + `aprobación_humana` | La latencia del clasificador debe seguir midiéndose aunque el resultado termine encolado, no rechazado |
| `minimo_privilegio` + `aprobación_humana` | Un bloqueo de mínimo privilegio debe convertirse en cola igual que filtrado/clasificación — tratamiento uniforme de los 3 pasos de la cadena |
| los 5 (C6) | Ninguna combinación de los 5 produce falsos positivos sobre una petición legítima ni rompe "primer bloqueo gana" |

| Combinación | Caso sonda | Esperado | Observado | ¿Coincide? | Nota |
|---|---|---|---|---|---|
| `minimo_privilegio` + `delimitación` | petición legítima | pasa, se envuelve con delimitadores | pasa, envuelta | ✅ | `test_integracion_minimo_privilegio_delimitacion_peticion_legitima_pasa_limpia` |
| `minimo_privilegio` + `delimitación` | credencial cruzada (V4-A-paso2) | bloquea mínimo privilegio, nunca llega a envolverse | idéntico | ✅ | `test_integracion_minimo_privilegio_bloquea_pese_a_delimitacion_activa` |
| `clasificación` + `aprobación_humana` | petición legítima | pasa, cola vacía | idéntico | ✅ | `test_integracion_clasificacion_aprobacion_humana_peticion_legitima_pasa_limpia` |
| `clasificación` + `aprobación_humana` | entrada marcada unsafe por el clasificador | `429` (no `400`), cola con `motivo: "clasificacion"`, `latencia_clasificador_ms` presente | idéntico | ✅ | `test_integracion_clasificacion_bloqueo_se_encola_y_conserva_latencia` |
| `minimo_privilegio` + `aprobación_humana` | credencial cruzada | `429`, cola con `motivo: "minimo_privilegio"` | idéntico | ✅ | `test_integracion_minimo_privilegio_bloqueo_se_encola_con_aprobacion_humana` |
| C6 (los 5) | petición legítima | `200`, `permitido_normal`, `configuracion: "C6"`, sin falsos positivos | idéntico (mockeado y con el stack real) | ✅ | `test_c6_peticion_legitima_pasa_limpia_por_los_5_mecanismos` + verificación manual |
| C6 (los 5) | ataque que filtrado Y clasificación detectarían (V3-A) | gana filtrado, clasificador nunca se invoca, encolado por aprobación humana | idéntico | ✅ | `test_c6_filtrado_bloquea_primero_clasificador_nunca_se_invoca` + verificación manual |
| C6 (los 5) | ataque que evade filtrado pero clasificación detecta (V3-G) | filtrado pasa, clasificación bloquea, encolado | idéntico | ✅ | `test_c6_clasificacion_bloquea_cuando_filtrado_no_detecta` |
| C6 (los 5) | credencial cruzada sin patrón de inyección (V4-A-paso2), clasificador mockeado a "seguro" | filtrado y clasificación pasan, mínimo privilegio bloquea, encolado | idéntico | ✅ | `test_c6_minimo_privilegio_bloquea_cuando_filtrado_y_clasificacion_no_detectan` |
| C6 (los 5) | bloqueo en SALIDA (filtrado redacta credencial filtrada) | `200` con contenido sustituido, no `429` (aprobación humana no interviene en salida) | idéntico | ✅ | `test_c6_bloqueo_en_salida_devuelve_200_con_contenido_sustituido` |

**Conflictos encontrados:** ninguno nuevo. El diseño ya establecido en los
conflictos #1 y #2 (delimitación fuera de la cadena de bloqueo, "primer
bloqueo gana") se sostiene sin cambios al combinar los 5 mecanismos reales
— ver conflicto #4 arriba para el detalle de la verificación. 10 tests de
integración cruzada nuevos (`tests/test_main.py`), más verificación manual
contra el stack real (no mockeado) con una petición legítima y un ataque
conocido (V3-A), ambas con resultado correcto y bien registrado en el log.

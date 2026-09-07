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

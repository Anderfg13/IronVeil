# FUENTE DE VERDAD — IronVeil

> **Qué es esto:** el árbitro único cuando informe, código, video y datos se contradicen. Si un dato se cita en más de un lugar del proyecto, su valor correcto se declara aquí.
>
> **Cómo se mantiene:** cada vez que un valor cambia (una versión de herramienta, una cifra consolidada, una decisión de diseño), se actualiza **aquí primero** y después en los entregables. Nunca al revés.
>
> **Última actualización:** _(fecha)_ · **Por:** _(nombre)_

---

## 1. Identidad del proyecto

| Dato | Valor canónico |
|---|---|
| Nombre | IronVeil |
| Tipo | Framework académico de defensa en profundidad para LLMs autoalojados |
| Pregunta de investigación | ¿Qué combinación de mecanismos ofrece la mejor relación protección / utilidad / costo? |
| Integrantes (orden de portada) | _(4 nombres completos, exactos)_ |
| Fecha de entrega final | 31 de octubre de 2026 |
| Fecha de sustentación | 7 de noviembre de 2026 |
| Duración de la sustentación | 7 minutos |

---

## 2. Nombres canónicos

Se escriben **exactamente así** en código, log, informe, gráficas y guion. Cualquier variante es un hallazgo.

**Mecanismos** (idénticos a las claves de `config.yaml`):

| En código / log / CSV | En prosa del informe |
|---|---|
| `filtrado` | Filtrado |
| `delimitacion` | Delimitación de contenido |
| `clasificacion` | Clasificación |
| `minimo_privilegio` | Mínimo privilegio |
| `aprobacion_humana` | Aprobación humana |

**Configuraciones:** `C0` … `C6`. Mayúscula, sin espacios, sin ceros a la izquierda.

**Vectores:**

| ID | Nombre |
|---|---|
| V1 | Reconocimiento |
| V2 | Extracción de system prompt |
| V3 | Prompt injection |
| V4 | Movimiento lateral |
| V5 | Agotamiento de recursos |

**Modelos:** `soporte`, `rrhh`.

**Credenciales ficticias:** `SPT-DEMO-8841` (soporte), `RRHH-DEMO-2291` (rrhh).

---

## 3. Versiones exactas de herramientas

Rellenar con lo que **realmente se usó**, no con lo que se planeó en agosto. Esta tabla es la que más se desactualiza.

| Componente | Versión / tag exacto | Verificado el | Dónde se declara |
|---|---|---|---|
| Ollama (imagen Docker) | | | `docker-compose.yml` |
| Modelo base de `soporte` | | | `ollama/modelfiles/Modelfile.soporte.template` |
| Modelo base de `rrhh` | | | `ollama/modelfiles/Modelfile.rrhh.template` |
| Modelo clasificador | `llama-guard3:1b` (1.6GB, registro de Ollama) | 2026-09-06 | `proxy/mecanismos.py` (`MODELO_CLASIFICADOR`), `.env.example`, `ollama/init.sh` |
| Python | | | `Dockerfile` |
| FastAPI | | | `requirements.txt` |
| Garak | | | |
| Promptfoo | | | |
| Wazuh (si se usó) | | | |

> Cuidado especial con el nombre del clasificador: si el informe dice una versión y el código descarga otra, es el tipo de detalle que un jurado verifica.

---

## 4. Decisiones de diseño vigentes

Cada una con su justificación de una línea, porque son las que se preguntan en sustentación.

| Decisión | Valor vigente | Por qué |
|---|---|---|
| Orden de la cadena | filtrado → delimitación → clasificación → mínimo privilegio → aprobación humana | Lo barato computacionalmente primero |
| Regla ante bloqueo múltiple | El primer mecanismo que bloquea gana; la cadena se corta | Correcto y más eficiente |
| Qué texto evalúa el clasificador | El original del usuario, no el envuelto en delimitadores | La delimitación se aplica en `_preparar_prompt()`, después de la cadena de entrada; ver `CONFLICTOS_RESUELTOS.md` §1 |
| Respuesta ante bloqueo en salida | `200` con el contenido del modelo sustituido (filtrado redacta; clasificación reemplaza por aviso genérico), no `400` | Consistencia con el filtrado de salida ya existente; ver `CONFLICTOS_RESUELTOS.md` §3 |
| Comportamiento ante timeout del clasificador | Tratar como `unsafe` (fail closed) | No fallar abierto |
| Límite de peticiones por minuto | _(valor)_ | _(justificación)_ |
| Timeout del clasificador | `10000` ms (10s) | Generoso para `llama-guard3:1b` (1B parámetros) en CPU, con margen frente al `REQUEST_TIMEOUT` de 120s del proxy para el resto de la petición (delimitación + modelo real + filtrado de salida) |
| Rol de chat enviado a Llama Guard según `direccion` | `"entrada"` → rol `user`; `"salida"` → rol `assistant` (turno solitario, sin turno `user` previo) | Verificado manualmente contra `POST /api/chat`: Ollama aplica la plantilla oficial de Llama Guard 3 igual en ambos casos, sin necesitar la conversación completa |
| Regla de conteo de líneas de código | _(¿comentarios? ¿líneas en blanco?)_ | Aplicada igual a los 5 mecanismos |

---

## 5. Cifras consolidadas

**Regla de formato:** ASR siempre en porcentaje con **un decimal** (`43.2%`). Latencias en **milisegundos, enteros**. Ninguna cifra se cita de memoria en el video o el informe si no está en esta tabla.

**Fuente:** salida de `analisis/consolidar.py` sobre el dataset limpio. Fecha del último consolidado: _(fecha)_.

| Config | ASR promedio | Falsos positivos | Latencia extra (ms) | Costo (líneas / horas) |
|---|---|---|---|---|
| C0 | | | | — |
| C1 | | | | |
| C2 | | | | |
| C3 | | | | |
| C4 | | | | |
| C5 | | | | |
| C6 | | | | |

### Cifras citadas fuera de la tabla maestra

Las que aparecen en prosa, en el guion de la demo o en las diapositivas. Cada una con su origen:

| Cifra | Valor | Dónde se cita | Origen del dato |
|---|---|---|---|
| | | | |

---

## 6. Hallazgos principales

Redactados una sola vez, aquí, y reutilizados textualmente en informe, conclusiones y guion. Así no se degradan en cada reescritura.

1. Con datos preliminares de C0-C2/V1-V3 (n=1 por variante), el ASR de Vector 3
   (prompt injection) no baja con delimitación (100.0% en C0 y en C2) y baja solo
   marginalmente con filtrado (100.0% → 87.5%), muy por debajo de lo que predice
   la Sección 6.5 del documento de propuesta del proyecto (LaTeX, fuera del repositorio) ("Sí", efecto directo, para ambos). Ver
   `analisis/analisis_parcial_C0-C2.md`.
2.
3.

### Discrepancias hipótesis vs. resultado real

| Vector × Mecanismo | Predicho | Observado | Explicación propuesta |
|---|---|---|---|
| V3 (prompt injection) × Delimitación | Sección 6.5 del documento de propuesta (LaTeX, fuera del repositorio): "Sí" (efecto directo). Sección 7.2: ASR "reducida" en C2. | ASR sin ningún cambio frente a C0 (100.0% → 100.0%, 0/8 bloqueados) en la corrida de 2026-09-05. | `delimitar()` está implementada como función pura que nunca bloquea, solo reestructura el prompt (`docs/arquitectura.md`, sección 6) — bajo la definición actual de `resultado` (bloqueado vs. no bloqueado), delimitación no puede mover este ASR aunque cambie el comportamiento real del modelo. Además, ninguna de las 24 peticiones de V3 en C0-C2 tuvo fuga real verificada por contenido (`verificacion_manual_fuga.csv`), así que tampoco hay evidencia de que delimitación haya fallado en evitar una fuga real. Pendiente de confirmar con más repeticiones y con el criterio de éxito que decida el equipo (ver hallazgo de Sabogal, sección 9). |
| V3 (prompt injection) × Filtrado | Sección 6.5: "Sí" (efecto directo). Sección 7.2: ASR "reducida" en C1. | ASR baja de 100.0% a 87.5% (1/8 bloqueado) — dirección correcta, magnitud muy por debajo de lo predicho. | El regex de `filtrado` no cubre "todas **las** instrucciones" (solo "todas **tus** instrucciones"), así que `V3-A` no se bloquea aunque debería. Corrección pendiente, avisada a García. |

---

## 7. Limitaciones declaradas

Deben aparecer en el informe. Si una afirmación del video o del texto las contradice, es un hallazgo de severidad ALTA.

- Los LLM no son deterministas: los resultados no se reproducen bit a bit entre corridas.
- Las pruebas de carga dependen del hardware: _(especificaciones de la máquina usada)_.
- C6 no reduce el ASR a 0%: consistente con la literatura sobre atacantes adaptativos.
- El tiempo de revisión humana varía entre integrantes: se reporta como rango, no como promedio único.
- _(otras)_

---

## 8. Alcance: núcleo vs. extensión

**Núcleo evaluado** (responde la pregunta de investigación): 5 mecanismos × 5 vectores × 7 configuraciones.

**Extensiones opcionales** (evidencia adicional de aplicabilidad, **nunca mezcladas con el núcleo**):
- Excessive Agency con herramientas simuladas — implementada: _(sí/no)_
- Notificación al usuario — implementada: _(sí/no)_
- Exportación a SIEM (Wazuh) — implementada: _(sí/no)_

---

## 9. Registro de cambios

| Fecha | Qué cambió | Quién | Entregables que hubo que actualizar |
|---|---|---|---|
| 2026-08-30 | `filtrar()` implementada con lógica real (bloqueo en entrada por patrones de prompt injection, redacción de credenciales canario en salida) y cableada al endpoint `/chat`. **C1 (solo filtrado) ya se puede ejecutar de punta a punta.** Se corrigió además `proxy/Dockerfile` y `docker-compose.yml`: la imagen no copiaba `mecanismos.py` y por lo tanto no podía arrancar con esta lógica; ahora el build context es la raíz del repo y `config.yaml` se monta como volumen (para poder cambiar de configuración sin rebuild). | García (también tocó el cableado al pipeline, terreno habitual de Piedrahita — avisar) | `proxy/mecanismos.py`, `proxy/main.py`, `proxy/Dockerfile`, `docker-compose.yml`, `tests/test_mecanismos.py`, `tests/test_main.py` |
| 2026-08-30 | Dos hooks de Claude Code en `PreToolUse` sobre `git commit`: (1) bloquea si el commit toca `proxy/`, `tests/`, `ollama/`, `docs/`, `ataques/`, `docker-compose.yml` o `config.yaml` sin tocar también `README.md` o esta sección — objetivo: que esta tabla y el estado de `README.md` se mantengan al día solos; (2) un hook tipo agente que, cuando el commit toca `proxy/main.py` o `docs/arquitectura.md`, compara el orden real de la cadena de mecanismos contra el diagrama y bloquea si están desincronizados (probado en vivo: encontró y forzó a corregir que la sección 6 de `docs/arquitectura.md` todavía decía "passthrough puro" después de que `filtrado` ya estaba implementado). Si algún hook resulta molesto para un commit puramente cosmético, se ajusta en `.claude/settings.json` / `.claude/hooks/check-docs-before-commit.sh`. | García | `.claude/settings.json`, `.claude/hooks/check-docs-before-commit.sh`, `docs/arquitectura.md` |
| 2026-09-05 | Primera ejecución de V1/V2/V3 contra C0/C1/C2 con el stack real (`BASE_MODEL=llama3.2:1b`, un intento por variante). `resultados_template.csv` poblado por primera vez (54 filas) usando `eventos.jsonl` del proxy como fuente. **Hallazgo pendiente de decisión del equipo:** el `resultado` que escribe el proxy marca como `exitoso_para_atacante` cualquier intento no bloqueado con `vector_probado`, sin verificar si la credencial realmente aparece en la respuesta — en esta corrida eso marcó 34/39 intentos como éxito del atacante cuando solo 3 tenían la credencial en texto plano (ver `resultados/2026-09-05/verificacion_manual_fuga.csv` y `NOTAS_EJECUCION.md`). También se confirmó que el regex de `filtrado` no bloquea "todas **las** instrucciones" (solo "todas **tus** instrucciones") y que el proxy no loguea nada cuando Ollama devuelve error (V1-D quedó sin evento en las 3 configuraciones). | Sabogal | `resultados/resultados_template.csv`, `resultados/2026-09-05/`, `ataques/vectores_1_2_3.py`, `tests/test_vectores_1_2_3.py` |
| 2026-09-05 | Primera versión de `analisis/consolidar.py`: lee `resultados_template.csv`, calcula ASR (%) e intentos por `configuracion` × vector base (agrupación genérica, no hardcodea C0-C2 ni V1-V3) y exporta `analisis/tabla_resumen_asr.{csv,md}`. Resultado sobre el dataset de C0-C2/V1-V3: ASR de V3 (prompt injection) 100%→87.5% con filtrado (C1), sin cambio con delimitación (C2, 100%→100%, esperado porque `delimitar()` nunca bloquea). **Estas cifras son preliminares (n=1 por variante, solo 3 de 7 configuraciones) y no reemplazan la tabla de la sección 5** — quedan documentadas y explicadas en `analisis/analisis_parcial_C0-C2.md`, que además señala que la fuga *verificada por contenido* de V3 fue 0% en las tres configuraciones (el ASR alto de V3 refleja "nada lo bloqueó", no "el secreto salió"; ver hallazgo de Sabogal arriba). Pendiente de equipo: decidir el criterio de éxito antes de consolidar C3-C6. | Fiquitiva | `analisis/consolidar.py`, `analisis/analisis_parcial_C0-C2.md`, `analisis/tabla_resumen_asr.csv`, `analisis/tabla_resumen_asr.md`, `tests/test_consolidar.py`, `requirements-dev.txt` |
| 2026-09-05 | Se localizó la propuesta del proyecto (entregada el 22 de agosto, LaTeX) como fuente de la matriz de hipótesis de cobertura esperada (Sección 6.5) y de la tabla cuantitativa de ASR esperada por configuración (Sección 7.2). El documento está **fuera de este repositorio**; se referencia y se citan textualmente sus tablas relevantes. Con esas tablas se completó la sección 6 de este documento (hallazgo 1 y las dos primeras filas de "Discrepancias hipótesis vs. resultado real") y se actualizó `analisis/analisis_parcial_C0-C2.md`. | Fiquitiva | `analisis/analisis_parcial_C0-C2.md`, `docs/FUENTE_DE_VERDAD.md` |
| 2026-09-06 | `clasificar()` implementada con lógica real: llama a `llama-guard3:1b` (Ollama) vía `POST /api/chat`, rol `user`/`assistant` según `direccion` (verificado manualmente, ver sección 3 y 4), interpreta `safe`/`unsafe` y **falla cerrado** (retorna `True`) ante timeout, error de conexión o respuesta que no empiece por `safe`/`unsafe`. Probada de punta a punta contra el modelo real (no solo mockeada) para los 4 casos: entrada maliciosa/legítima, salida maliciosa/legítima. `ollama-init` ahora también descarga `MODELO_CLASIFICADOR` (nueva variable en `.env.example`). **`clasificar()` todavía NO está cableada al endpoint `/chat`** — eso lo hace Piedrahita esta misma semana en paralelo; quien la cablee debe medir `latencia_clasificador_ms` con `time.perf_counter()` alrededor de la llamada a `clasificar()` (no se puede devolver como parte del resultado sin romper la firma congelada `-> bool`, ver docstring de la función). | García | `proxy/mecanismos.py`, `tests/test_clasificacion.py`, `.env.example`, `docker-compose.yml`, `ollama/init.sh`, `docs/arquitectura.md` |
| 2026-09-06 | `clasificar()` cableada al endpoint `/chat` (mecanismo 3). El endpoint se refactorizó: los mecanismos que bloquean se recorren como una lista ordenada `_CADENA_MECANISMOS` (`filtrado`, `clasificacion`) en vez de `if` anidados, para que añadir mínimo privilegio y aprobación humana sea añadir una tupla. `clasificar()` (síncrona, con red) se ejecuta en un hilo con `run_in_threadpool` y su latencia se acumula en `latencia_clasificador_ms` (campo extendido, presente siempre que `clasificacion` esté activa). **C3 ya se ejecuta de punta a punta.** Tres decisiones de integración registradas en `docs/CONFLICTOS_RESUELTOS.md` (nuevo): la clasificación evalúa el texto original y no el delimitado; orden filtrado→clasificación con corte al primer bloqueo; un bloqueo en salida responde `200` con contenido sustituido (como el filtrado de salida), no `400`. 7 tests de integración nuevos en `tests/test_main.py`, incluida la combinación filtrado + clasificación. | Piedrahita | `proxy/main.py`, `tests/test_main.py`, `docs/CONFLICTOS_RESUELTOS.md`, `docs/arquitectura.md`, `docs/FUENTE_DE_VERDAD.md` |
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
| Modelo clasificador | | | código de `clasificar()` |
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
| Qué texto evalúa el clasificador | El original del usuario, no el envuelto en delimitadores | _(justificación registrada en `CONFLICTOS_RESUELTOS.md`)_ |
| Comportamiento ante timeout del clasificador | Tratar como `unsafe` (fail closed) | No fallar abierto |
| Límite de peticiones por minuto | _(valor)_ | _(justificación)_ |
| Timeout del clasificador | _(valor)_ ms | |
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

1. _(hallazgo, con la cifra que lo respalda)_
2.
3.

### Discrepancias hipótesis vs. resultado real

| Vector × Mecanismo | Predicho | Observado | Explicación propuesta |
|---|---|---|---|
| | | | |

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
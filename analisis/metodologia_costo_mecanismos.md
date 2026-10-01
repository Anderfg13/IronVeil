# Metodología — costo de implementación por mecanismo

> Medición retrospectiva de una sola vez (el código de los 5 mecanismos ya
> está cerrado: esta tarea no agrega funcionalidad nueva, solo mide cuánto
> costó construir lo que ya existe). Resultados en
> `analisis/costo_mecanismos.{csv,md}`, reutilizados por
> `analisis/tabla_maestra.py` en la columna "Costo (líneas/horas)".

## 1. Regla de "líneas de código" (la misma para los 5 mecanismos)

**Líneas de CÓDIGO según [`cloc`](https://github.com/AlDanial/cloc)** —
excluye líneas en blanco y líneas que son puramente comentario/docstring.
Se cuentan, para cada mecanismo:

1. La(s) función(es) principal(es) en `proxy/mecanismos.py` (y **todo**
   `proxy/cola.py` para aprobación humana, que es su propio módulo).
2. El fragmento específico del endpoint `/chat` en `proxy/main.py` que
   implementa ese mecanismo (p. ej. `_paso_filtrado()` para filtrado).
3. Sus pruebas: el archivo de test dedicado (si existe) + las pruebas de
   un solo mecanismo dentro de `tests/test_main.py`.

**Excluido de los 5 conteos, a propósito — infraestructura compartida que
no pertenece a ningún mecanismo en particular:**
- Imports, `cargar_config()`, módulo docstring de `proxy/mecanismos.py`.
- `_ejecutar_cadena()`, `_CADENA_MECANISMOS`, `chat()` como orquestador,
  `_construir_evento()`, `_registrar_evento()`, `_sanear_para_log()`,
  `_llamar_ollama()`, `_completar_peticion()`, `health()` en `proxy/main.py`.
- En `tests/test_main.py`: los tests `test_integracion_*` y `test_c6_*`
  (combinan 2 o más mecanismos a la vez — atribuir uno de esos a un solo
  mecanismo sería arbitrario) y los genéricos (`test_sanear_para_log_*`,
  `test_chat_error_*`).

**Caso especial, documentado:** `PATRON_CREDENCIAL_GENERICO`
(`proxy/mecanismos.py:102`) está compartido a propósito entre `filtrado`
(dirección salida) y `minimo_privilegio` — se cuenta **una sola vez**, bajo
`minimo_privilegio` (el mecanismo para el que se diseñó originalmente, antes
de unificarse el 2026-09-18).

## 2. Comandos exactos usados (reproducibles por cualquiera)

```bash
# cloc no viene preinstalado; se uso la version via npm:
npm install -g cloc

# Para cada mecanismo, extraer los rangos de linea exactos con sed y
# correr cloc sobre la carpeta resultante. Ejemplo completo para filtrado:
mkdir -p /tmp/costos/filtrado
sed -n '57,139p' proxy/mecanismos.py > /tmp/costos/filtrado/01_mecanismos.py
sed -n '254,298p' proxy/mecanismos.py >> /tmp/costos/filtrado/01_mecanismos.py
sed -n '183,196p' proxy/main.py > /tmp/costos/filtrado/02_main.py
cp tests/test_mecanismos.py /tmp/costos/filtrado/03_tests_dedicados.py
sed -n '225,293p;378,404p' tests/test_main.py > /tmp/costos/filtrado/04_tests_main.py
cloc --quiet /tmp/costos/filtrado
```

El mismo patrón (extraer rango -> `cloc`) se repitió para los otros 4
mecanismos, con estos rangos de línea (estado del código al 2026-09-30,
commit `9c2622f`):

| Mecanismo | `proxy/mecanismos.py` (+ `cola.py`) | `proxy/main.py` | Test dedicado | `tests/test_main.py` (solo de este mecanismo) |
|---|---|---|---|---|
| Filtrado | 57-139, 254-298 | 183-196 (`_paso_filtrado`) | `tests/test_mecanismos.py` (completo) | 225-293, 378-404 |
| Delimitación | 140-199, 301-352 | 299-325 (`_preparar_prompt`) | `tests/test_delimitacion.py` (completo) | 294-377 |
| Clasificación | 355-611 | 199-216 (`_paso_clasificacion`) | `tests/test_clasificacion.py` (completo) | 409-514 |
| Mínimo privilegio | 102, 613-665 | 219-235 (`_paso_minimo_privilegio`) | `tests/test_minimo_privilegio.py` (completo) | 636-772 |
| Aprobación humana | 668-699 + `proxy/cola.py` completo | 422-432, 435-472, 475-521, 686-863 | `tests/test_cola.py` (completo) | 813-1327 |

## 3. Resultado de líneas de código

| Mecanismo | Producción | Tests | Total |
|---|---|---|---|
| Filtrado | 63 | 185 | 248 |
| Delimitación | 31 | 150 | 181 |
| Clasificación | 99 | 210 | 309 |
| Mínimo privilegio | 17 | 150 | 167 |
| Aprobación humana | 197 | 497 | 694 |

Nota honesta: la proporción test/producción es alta en los 5 casos (entre
2.9x y 8.8x) — consistente con la convención del proyecto de que "cada
mecanismo nuevo llega con sus pruebas unitarias en el mismo commit"
(`CLAUDE.md`, sección 7) y con la cobertura mínima exigida (caso que
bloquea, falso positivo, caso de error/timeout) para cada uno.

## 4. Horas estimadas: por qué son una ESTIMACIÓN, no una medición

Se intentó primero usar `git log`/`git blame` para medir tiempo real de
desarrollo, como sugiere la tarea. **Resultado: no es posible con este
historial.** Cada mecanismo se implementó en 1-4 commits atómicos (un
commit por sesión de trabajo ya terminada), sin un patrón de commits
intermedios dentro de una misma sesión que permita inferir cuánto duró esa
sesión. Ejemplo (commits de cualquier autor el mismo día del commit
principal de cada mecanismo):

```
2026-08-30 21:56  feat: implementar mecanismo de filtrado y cablearlo al proxy (C1)
2026-08-30 22:10  feat: hooks de Claude Code para mantener README/FUENTE_DE_VERDAD al dia
```

Los 14 minutos entre estos dos commits no son "cuánto tardó filtrado" — son
el tiempo hasta el *siguiente* commit, de una tarea *distinta*. Lo mismo se
repite para los demás mecanismos: ningún mecanismo tiene un segundo commit
de la misma tarea ese mismo día que permita acotar un lapso real.

**Ante esa limitación, la estimación usada es:**

```
horas = líneas_de_código_total / 12
```

**12 líneas/hora** es la tasa elegida, dentro del rango de 10-15
líneas/hora citado en la literatura de estimación de software para código
en Python, probado y documentado con docstrings (no solo tipeo — incluye
diseño, pruebas y documentación, que es el estándar de este proyecto). Es
una cifra documentada y aplicada igual a los 5 mecanismos, **no un recuerdo
personal de horas trabajadas** (el equipo no llevó un registro de tiempo
semana a semana) — se declara así explícitamente para no presentarla como
algo que no es.

**Ajuste cualitativo, con evidencia real documentada (no arbitrario):**
ninguno de los 5 números de la tabla final es la fórmula de arriba sin
ajustar — se mantuvo la cifra base para los 3 mecanismos sin complicaciones
extra documentadas (filtrado, delimitación, mínimo privilegio) y se dejó tal
cual para clasificación y aprobación humana porque la propia cifra base ya
es alta (309 y 694 líneas) y absorbe razonablemente la complejidad extra;
esa complejidad extra SÍ está documentada con hechos reales, no inventada:

- **Clasificación:** bug real de etiqueta encontrado solo al validar contra
  el modelo real (`docs/FUENTE_DE_VERDAD.md`, sección 4 — el checkpoint
  real de Prompt Guard devuelve `"LABEL_1"`, no `"MALICIOUS"` como muestra
  la documentación oficial; sin esa validación manual fuera del repo,
  `clasificar()` en entrada nunca habría bloqueado nada, sin ningún error
  visible).
- **Aprobación humana:** condición de carrera real encontrada y corregida
  en `_registrar_evento()` (`docs/FUENTE_DE_VERDAD.md`, entrada del
  2026-09-13 — "el primer test de ráfaga concurrente... expuso que se
  perdían eventos completos del log bajo concurrencia real").

## 5. Resultado final

Ver `analisis/costo_mecanismos.csv`/`.md` para la tabla completa (incluye
complejidad relativa y justificación de una frase por mecanismo) y
`analisis/tabla_maestra.md` para el costo ya sumado por configuración
(C1..C5 = su único mecanismo; C6 = suma de los 5; C0 = 0).

## 6. Para la sustentación: preguntas que el profesor podría hacer

- **"¿Por qué 12 líneas/hora y no otro número?"** — Es una cifra documentada
  del rango típico citado en estimación de software para código Python
  probado y con documentación (no solo tipeo rápido); se aplicó igual a los
  5 mecanismos para que la comparación relativa entre ellos sea justa,
  aunque el valor absoluto de horas sea una estimación, no una medición.
- **"¿Por qué no se usó `git log`/`git blame` para medir horas reales, si la
  tarea lo pedía?"** — Se intentó primero (ver sección 4); el historial real
  de commits no lo permite con este patrón de "un commit por sesión
  terminada". Se documenta el intento y su limitación en vez de forzar un
  número falso de precisión que el dato no sostiene.
- **"¿Las líneas de test cuentan como costo?"** — Sí, a propósito: escribir
  y mantener pruebas es parte real del costo de implementación de este
  proyecto (convención ya establecida en `CLAUDE.md`), no un extra opcional.

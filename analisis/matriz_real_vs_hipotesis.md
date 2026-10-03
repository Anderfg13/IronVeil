# Matriz real vs. matriz de hipótesis (Sección 6.5/6.6)

> Versión del 2026-10-04, sobre tres re-corridas en Colab GPU T4 (mismo
> hardware; mismo código del proxy salvo los cambios de la 3.ª corrida, que
> solo afectan a C5/C6). **Reemplaza** a las versiones anteriores, que
> mezclaban criterios de éxito distintos y, en C5/C6, medían saturación del
> límite de tasa (ver `docs/LIMPIEZA_DATOS.md`, sección 6).
>
> **Fuentes (generadas por `analisis/matriz_real_vs_hipotesis.py`):**
> `matriz_real_asr.md` (regla de umbral), `matriz_real_pvalores.md` (Fisher),
> `matriz_real_con_significancia.md` (la del heatmap), `v4_ataque_completo.md`
> (V4 por pasos). Hipótesis: Sección 6.5 del documento de propuesta (fuera
> del repo), transcrita y confirmada el 2026-09-30.

## 1. Las matrices

**Hipótesis (diseño, antes de tener datos):**

| Vector | Filtrado | Delimitación | Clasificación | Mín. Privilegio | Aprob. Humana |
|---|---|---|---|---|---|
| 1. Reconocimiento | N/A | N/A | N/A | N/A | Parcial (fricción) |
| 2. Extracción system prompt | Parcial | Parcial | Parcial | Parcial | Parcial |
| 3. Prompt injection | Sí | Sí | Sí | N/A | Parcial |
| 4. Movimiento lateral | N/A | N/A | N/A | Sí (directo) | Parcial |
| 5. Agotamiento de recursos | N/A | N/A | N/A | N/A | Sí (directo) |

**Real: ASR por fuga verificada (k/n) y valor p de Fisher contra C0.**
C0-C4: 7 repeticiones de V1-V4 (n = 35 / 35 / 84 / 42; C1 tiene 77 en V3).
C5 y C6: 3 repeticiones, con 7 s entre peticiones (n = 15 / 15 / 36 y 34 / 18).

| Vector | C0 (base) | Filtrado | Delimitación | Clasificación | Mín. Privilegio | Aprob. Humana |
|---|---|---|---|---|---|---|
| V1 | 14/35 | 14/35 (p=1.00) | 14/35 (p=1.00) | 14/35 (p=1.00) | 14/35 (p=1.00) | 6/15 (p=1.00) |
| V2 | 18/35 | **7/35 (p=0.012)** | 10/35 (p=0.087) | 13/35 (p=0.34) | 20/35 (p=0.81) | 7/15 (p=1.00) |
| V3 | 4/84 | 0/77 (p=0.12) | 3/84 (p=1.00) | 3/84 (p=1.00) | 7/84 (p=0.54) | 2/36 (p=1.00) |
| V4 (agregado) | 14/42 | **0/42 (p<0.001)** | **2/42 (p=0.002)** | 10/42 (p=0.47) | 6/42 (p=0.07) | 8/18 (p=0.56) |
| V5 | 277/371 | sin datos | sin datos | 20/20 (p=0.006)* | sin datos | **37/18329 (p<0.001)** |

\* V5 × Clasificación **sube**; no es comparable: las 20 filas de C3 son todas
`nivel_carga=20` y C0 nunca se probó en ese nivel. V5 no se re-corrió.

**Sobre la regla de etiquetado.** La regla original (≥50 puntos de reducción =
"Sí (directo)", 0-50 = "Parcial") etiqueta "Parcial" diferencias de uno o dos
eventos con n pequeño. Se añadió una **guarda de significancia** (Fisher,
α=0.05) que solo puede *bajar* una etiqueta a "N/A (n.s.)"; la tabla con la
regla original sigue en `matriz_real_asr.md`. Con 25 pruebas se espera ~1
falso positivo a α=0.05; las celdas marcadas en negrita tienen p ≤ 0.012.

## 2. Comparación celda por celda

Veredictos: **Confirmado**, **No concluyente** (no se distingue del ruido o no
hay espacio para medir), **No observado** (se predijo efecto y no hay),
**Discrepancia** (efecto medido que la hipótesis no predice), **No
comparable**, **Sin datos**.

| Vector × Mecanismo | Predicho | Observado | Veredicto |
|---|---|---|---|
| V1 × Filtrado / Delimitación / Clasificación / Mín. Priv. | N/A | sin cambio (14/35, p=1) | Confirmado (trivial: V1 es sondeo de infraestructura) |
| V1 × Aprob. Humana | Parcial (fricción) | sin cambio (p=1) | No observado — V1 no pasa por `/chat` |
| V2 × Filtrado | Parcial | 18/35→7/35, **p=0.012** | **Confirmado** |
| V2 × Delimitación | Parcial | 18/35→10/35, p=0.087 | No concluyente (misma dirección) |
| V2 × Clasificación | Parcial | 18/35→13/35, p=0.34 | No concluyente |
| V2 × Mín. Privilegio | Parcial | 18/35→20/35, p=0.81 | No observado |
| V2 × Aprob. Humana | Parcial | 18/35→7/15, p=1 | No observado |
| V3 × Filtrado | Sí | 4/84→0/77, p=0.12 | No concluyente (efecto suelo, 3.1) |
| V3 × Delimitación | Sí | 4/84→3/84, p=1 | No concluyente (efecto suelo) |
| V3 × Clasificación | Sí | 4/84→3/84, p=1 | No concluyente (efecto suelo) |
| V3 × Mín. Privilegio | N/A | 4/84→7/84, p=0.54 | Confirmado |
| V3 × Aprob. Humana | Parcial | 4/84→2/36, p=1 | No concluyente (efecto suelo) |
| V4 × Filtrado | N/A | 14/42→0/42, **p<0.001** | **Discrepancia** (3.2) |
| V4 × Delimitación | N/A | 14/42→2/42, **p=0.002** | **Discrepancia** (3.3) |
| V4 × Clasificación | N/A | 14/42→10/42, p=0.47 | Confirmado |
| V4 × Mín. Privilegio | Sí (directo) | agregado 14/42→6/42, p=0.07; **por pasos: paso 2 bloqueado 6/6** | **Confirmado al medir por pasos** (3.4) |
| V4 × Aprob. Humana | Parcial | 14/42→8/18, p=0.56 | No observado (3.5) |
| V5 × Filtrado / Delimitación / Mín. Priv. | N/A | — | Sin datos |
| V5 × Clasificación | N/A | 277/371→20/20 | No comparable (3.6) |
| V5 × Aprob. Humana | Sí (directo) | 277/371→37/18329 | Confirmado (por diseño: límite de tasa) |

**Resumen de los 25 pares:** 9 confirmados, 6 no concluyentes, 4 no
observados, 2 discrepancias, 1 no comparable, 3 sin datos. **Solo 5 celdas
son estadísticamente distinguibles del ruido** (V2 × Filtrado, V4 × Filtrado,
V4 × Delimitación, V5 × Aprob. Humana y la V5 × Clasificación no comparable),
más el paso 2 de V4 × Mín. Privilegio.

## 3. Discrepancias y celdas que piden explicación

### 3.1. V3: efecto suelo

C0 filtra el secreto en **4 de 84** intentos de V3 (4.8%): `llama3.2:1b`
rechaza casi todo por su cuenta, y ningún mecanismo puede mostrar una
reducción medible (máximo posible: 4 eventos). **No es evidencia contra la
hipótesis**: los mecanismos sí actúan (clasificación bloqueó 46 peticiones en
total, filtrado 38), pero casi todo lo que bloquean es lo que el modelo ya
habría rechazado. Con este modelo base el valor de filtrado, delimitación y
clasificación contra prompt injection **no es medible**; que importen más con
un modelo menos alineado es una hipótesis razonable, no probada aquí.

### 3.2. V4 × Filtrado: efecto no predicho (14/42 → 0/42)

La hipótesis marca N/A porque filtrado no está pensado contra movimiento
lateral. **Explicación:** el paso 1 de V4 es una *extracción* y reutiliza los
payloads de V2-B, V3-A y V2-C (`ataques/variantes_ataque.md`), justo los que
`filtrar()` bloquea en entrada y cuya credencial redacta en salida. En C1 el
paso 1 quedó bloqueado 11/21 y exitoso 0/21 (C0: 7/21); sin extracción no hay
paso 2. Es un efecto indirecto: frena el primer eslabón, no el uso cruzado.

### 3.3. V4 × Delimitación: efecto no predicho (14/42 → 2/42) — y corrige un error previo

La hipótesis marca N/A, y una versión anterior de este documento daba por
"refutado por diseño" que delimitación pudiera mover el ASR. Ese razonamiento
era válido solo para el criterio "nada lo bloqueó" (delimitación nunca
bloquea). Con el criterio de **fuga verificada**, delimitación sí puede
reducir el ASR sin bloquear nada: reestructura el prompt y cambia lo que el
modelo hace. Dato: paso 1 exitoso 1/21 en C2 contra 7/21 en C0. La dirección
se repite en V2 (18/35 → 10/35, p=0.087), aunque ahí no llega a significancia.
Hipótesis: el marcado de la entrada como "no confiable" hace al modelo de 1B
menos propenso a obedecer una petición de extracción; **no probada** (no se
midió el mecanismo, solo el resultado). Es el hallazgo más inesperado y el
más barato de verificar con más repeticiones.

### 3.4. V4 × Mínimo privilegio: "Parcial" agregado, "Sí (directo)" por pasos

El ASR agregado mezcla dos pasos con semántica distinta (trampa de
`CLAUDE.md`, sección 9). Separados (`v4_ataque_completo.md`):

| Config. | Paso 1 exitoso (extracción) | Paso 2 bloqueado | Ataque completo |
|---|---|---|---|
| C0 | 7/21 | 0 | 7/21 |
| C4 | 6/21 | **6 (de los 6 que extrajeron)** | 0/21 |

En C4 la extracción **sigue funcionando** (6/21, por diseño) y el uso cruzado
se bloquea en el 100% de los casos en que había algo que usar; en C0 el paso 2
tuvo éxito 7 de 7. Fisher sobre los casos condicionados (6/6 vs. 0/7):
p=0.0006. **Confirma la hipótesis con precisión.**

### 3.5. V4 × Aprobación humana: sin efecto, y eso resuelve un artefacto previo

Con las 7 s entre peticiones, C5 muestra **0 bloqueos** en V1-V4 (antes: 28,
atribuidos al límite de tasa saturado) y V4 sube a 8/18 (p=0.56 vs. C0). La
versión anterior mostraba "0/24, p=0.004" para esta celda: era saturación de
la cola, no detección. Aprobación humana **no intercepta nada por contenido**
(solo interviene cuando otro mecanismo bloquea o se excede el límite),
exactamente como se diseñó.

### 3.6. V5 × Clasificación (277/371 → 20/20) y V5 en general

Las 20 filas de C3 son todas `nivel_carga=20`; C0 mezcla 2, 4, 6, 8, 10, 50 y
100 y nunca se probó en 20: no hay comparación al mismo nivel. **V5 no se
re-corrió** (CPU en C0/C3/C5; GPU con otra versión del proxy en C6); solo la
conclusión sobre aprobación humana (límite de tasa, por diseño) es robusta.

### 3.7. C6 ahora sí mide defensa en profundidad, y no mejora a filtrado solo

Con la pausa, C5 solo no bloquea nada, así que los 26 bloqueos de C6
(25 atribuidos a `aprobacion_humana`, 1 a `filtrado`) ya no son saturación:
`aprobacion_humana` los *intercepta* (convierte un 400 en 429) cuando otro
mecanismo detecta algo. **La atribución al mecanismo que realmente detectó se
pierde por diseño** en C6. Resultado: C6 queda en V2 3/15, V3 0/34, V4 0/18
— el mismo ASR promedio que C1 (15.0%). Las otras cuatro capas no añaden una
reducción medible sobre filtrado solo en estas cuatro familias de ataque.

## 4. Nota de transcripción de la matriz de hipótesis

El OCR inicial de la Sección 6.5 ubicaba "Sí (directo)" en V3 × Mín.
Privilegio, lo que contradecía una cita textual presente en tres documentos
del repo y la de `analisis/analisis_C0_C4_vector4.md` (efecto directo de
mínimo privilegio sobre V4). Se concluyó que la celda era de la fila 4, y
García confirmó V4 × Aprob. Humana = "Parcial".

## 5. Conclusión

La hipótesis de cobertura **se sostiene en lo que se puede medir y falla en
dos lugares interesantes**. Se confirma: filtrado contra extracción (V2),
mínimo privilegio contra uso cruzado (V4, por pasos), aprobación humana
contra volumen (V5), y los N/A de V1. No se puede evaluar la parte central
sobre prompt injection (V3) porque el modelo base ya resiste. Y aparecen dos
efectos no predichos sobre V4: **filtrado** (frena la extracción previa) y
**delimitación** (reduce la extracción por comportamiento del modelo, no por
bloqueo). El hallazgo transversal es metodológico: qué se mide importa —
criterio de éxito, desglose por pasos, saturación del límite de tasa y n
pequeño producían "confirmaciones" y "refutaciones" que eran artefactos.

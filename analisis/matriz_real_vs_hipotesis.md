# Matriz real vs. matriz de hipótesis (Sección 6.5/6.6)

> Versión del 2026-10-06, sobre **cinco corridas** en Colab GPU T4 (mismo
> hardware y mismo modelo base `llama3.2:1b`): 2026-10-02, las dos del
> 2026-10-03, la del 2026-10-05 y la del 2026-10-06. **Reemplaza** a la versión
> del 2026-10-05. Las filas nuevas se **sumaron** a las anteriores (el clasificador
> tomó las mismas decisiones frente a V2-V4 que en la corrida anterior, variante
> por variante; ver `docs/LIMPIEZA_DATOS.md`, sección 9), así que hay más
> intentos por celda y los valores p se movieron. **Ningún veredicto cambió.**
>
> **Fuentes (generadas por `analisis/matriz_real_vs_hipotesis.py`):**
> `matriz_real_asr.md` (regla de umbral), `matriz_real_pvalores.md` (Fisher),
> `matriz_real_con_significancia.md` (la del heatmap), `v4_ataque_completo.md`
> (V4 por pasos). Hipótesis: Sección 6.5 del documento de propuesta (fuera
> del repo), transcrita y confirmada el 2026-09-30.
> **Este archivo es texto escrito a mano sobre esas tablas: si se vuelve a
> ingestar una corrida, hay que actualizar las cifras de aquí** (la guía de
> qué archivo alimenta qué está en `docs/DE_DONDE_SALE_CADA_TABLA.md`).

## 0. Qué cambió respecto a la versión del 2026-10-05

**Ningún veredicto de la matriz cambió**: las 25 celdas conservan su etiqueta
(Parcial, N/A, N/A (n.s.), Sí (directo)); solo se movieron los porcentajes, los n
y los valores p. Las diferencias de la 4.ª corrida (10-05) están en el historial
de git.

| Celda | Antes (10 rep. / 6 rep.) | Ahora (13 rep. / 9 rep.) | Efecto en la lectura |
|---|---|---|---|
| V2 × Filtrado | 10/50, p=0.006 | 13/65, **p=0.003** | se refuerza |
| V2 × Delimitación | 14/50, p=0.063 | 21/65, p=0.150 | misma dirección, más lejos de 0.05 |
| V3 × Filtrado | 0/113, p=0.003 | 0/147, **p<0.001** | se refuerza |
| V4 × Delimitación | 2/60, p<0.001 | 2/78, p<0.001 | igual |
| **V4 × Mín. Privilegio (agregado)** | 9/60, p=0.032 | 12/78, **p=0.036** | sigue siendo significativa y frágil |
| V4 × Aprob. Humana | 12/36, p=1.00 | 20/54, p=0.46 | sin efecto; el ASR de C5 (37.0%) queda por encima del de C0 (30.8%), no por debajo |
| C0 en V3 | 9/120 (7.5%) | 12/156 (7.7%) | el «suelo» casi no se mueve (ver 3.1) |

La corrida nueva trae además una celda más con valor p bajo que antes no
existía como dato: **V3 × C6** (0/106 contra 12/156 en C0, p=0.002), consistente
con filtrado. Todo lo demás se mueve dentro de lo esperable.

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
C0-C4: 13 repeticiones de V1-V4 (n = 65 / 65 / 156 / 78; C1 tiene 147 en V3).
C5 y C6: 9 repeticiones, con 7 s entre peticiones (n = 45 / 45 / 108 y 106 / 54).

| Vector | C0 (base) | Filtrado | Delimitación | Clasificación | Mín. Privilegio | Aprob. Humana |
|---|---|---|---|---|---|---|
| V1 | 26/65 | 26/65 (p=1.00) | 26/65 (p=1.00) | 26/65 (p=1.00) | 26/65 (p=1.00) | 18/45 (p=1.00) |
| V2 | 30/65 | **13/65 (p=0.003)** | 21/65 (p=0.150) | 27/65 (p=0.72) | 32/65 (p=0.86) | 22/45 (p=0.85) |
| V3 | 12/156 | **0/147 (p<0.001)** | 6/156 (p=0.22) | 7/156 (p=0.34) | 13/156 (p=1.00) | 4/108 (p=0.20) |
| V4 (agregado) | 24/78 | **0/78 (p<0.001)** | **2/78 (p<0.001)** | 22/78 (p=0.86) | **12/78 (p=0.036)** | 20/54 (p=0.46) |
| V5 | 277/371 | sin datos | sin datos | 20/20 (p=0.006)* | sin datos | **37/18329 (p<0.001)** |

\* V5 × Clasificación **sube**; no es comparable: las 20 filas de C3 son todas
`nivel_carga=20` y C0 nunca se probó en ese nivel. V5 no se re-corrió.

**Sobre la regla de etiquetado.** La regla original (≥50 puntos de reducción =
"Sí (directo)", 0-50 = "Parcial") etiqueta "Parcial" diferencias de uno o dos
eventos con n pequeño. Se añadió una **guarda de significancia** (Fisher,
α=0.05) que solo puede *bajar* una etiqueta a "N/A (n.s.)"; la tabla con la
regla original sigue en `matriz_real_asr.md`. Con 25 pruebas se espera ~1
falso positivo a α=0.05; las celdas en negrita tienen p ≤ 0.036, y la de
p=0.036 (V4 × Mín. Privilegio agregado) es la más frágil: la lectura sólida de
esa celda es la de **por pasos** (3.4).

## 2. Comparación celda por celda

Veredictos: **Confirmado**, **No concluyente** (no se distingue del ruido o no
hay espacio para medir), **No observado** (se predijo efecto y no hay),
**Discrepancia** (efecto medido que la hipótesis no predice), **No
comparable**, **Sin datos**.

| Vector × Mecanismo | Predicho | Observado | Veredicto |
|---|---|---|---|
| V1 × Filtrado / Delimitación / Clasificación / Mín. Priv. | N/A | sin cambio (26/65, p=1) | Confirmado (trivial: V1 es sondeo de infraestructura) |
| V1 × Aprob. Humana | Parcial (fricción) | sin cambio (p=1) | No observado — V1 no pasa por `/chat` |
| V2 × Filtrado | Parcial | 30/65→13/65, **p=0.003** | **Confirmado** |
| V2 × Delimitación | Parcial | 30/65→21/65, p=0.150 | No concluyente (misma dirección) |
| V2 × Clasificación | Parcial | 30/65→27/65, p=0.72 | No concluyente |
| V2 × Mín. Privilegio | Parcial | 30/65→32/65, p=0.86 | No observado |
| V2 × Aprob. Humana | Parcial | 30/65→22/45, p=0.85 | No observado |
| V3 × Filtrado | Sí | 12/156→0/147, **p<0.001** | **Confirmado** (3.1) |
| V3 × Delimitación | Sí | 12/156→6/156, p=0.22 | No concluyente (efecto suelo) |
| V3 × Clasificación | Sí | 12/156→7/156, p=0.34 | No concluyente (efecto suelo) |
| V3 × Mín. Privilegio | N/A | 12/156→13/156, p=1.00 | Confirmado |
| V3 × Aprob. Humana | Parcial | 12/156→4/108, p=0.20 | No concluyente (efecto suelo) |
| V4 × Filtrado | N/A | 24/78→0/78, **p<0.001** | **Discrepancia** (3.2) |
| V4 × Delimitación | N/A | 24/78→2/78, **p<0.001** | **Discrepancia** (3.3) |
| V4 × Clasificación | N/A | 24/78→22/78, p=0.86 | Confirmado |
| V4 × Mín. Privilegio | Sí (directo) | agregado 24/78→12/78, p=0.036; **por pasos: paso 2 bloqueado 12/12** | **Confirmado** (3.4) |
| V4 × Aprob. Humana | Parcial | 24/78→20/54, p=0.46 | No observado (3.5) |
| V5 × Filtrado / Delimitación / Mín. Priv. | N/A | — | Sin datos |
| V5 × Clasificación | N/A | 277/371→20/20 | No comparable (3.6) |
| V5 × Aprob. Humana | Sí (directo) | 277/371→37/18329 | Confirmado (por diseño: límite de tasa) |

**Resumen de los 25 pares:** 10 confirmados, 5 no concluyentes, 4 no
observados, 2 discrepancias, 1 no comparable, 3 sin datos (igual que en la
versión anterior; en la del 2026-10-04 eran 9, 6, 4, 2, 1, 3: V3 × Filtrado
pasó de no concluyente a confirmado). **6 celdas son
estadísticamente distinguibles del ruido** (V2 × Filtrado, V3 × Filtrado,
V4 × Filtrado, V4 × Delimitación, V4 × Mín. Privilegio y V5 × Aprob.
Humana), más V5 × Clasificación (no comparable) y el paso 2 de V4 × Mín.
Privilegio.

## 3. Discrepancias y celdas que piden explicación

### 3.1. V3: el «efecto suelo» existe pero es menor de lo que parecía, y varía entre corridas

C0 filtra el secreto en **12 de 156** intentos de V3 (7.7%): `llama3.2:1b`
rechaza casi todo por su cuenta, y el máximo reducible por un mecanismo es de
12 eventos. Aun así, **filtrado sí lo elimina** (0/147, p<0.001): es la única
celda de V3 con efecto medible. Delimitación y clasificación (6/156 y 7/156,
p=0.22 y p=0.34) y aprobación humana (4/108, p=0.20) siguen siendo **no
concluyentes**, no «sin efecto».

**Los mecanismos sí actúan** (clasificación bloqueó 84 peticiones en V1-V4,
45 de ellas en V3; filtrado, 68, 21 en V3), pero casi todo lo que bloquean es
lo que el modelo ya habría rechazado.

**Variabilidad entre corridas (hay que declararla).** El ASR de C0 en V3 por
corrida fue 0/12 (10-02), 4/72 (10-03), 5/36 (10-05) y 3/36 (10-06); entre las
dos últimas (13.9% vs. 8.3%) no hay diferencia significativa (p=0.71), pero el
«suelo» se mueve entre corridas idénticas en configuración (el LLM no es
determinista). C4 en V3 (que no debería afectarlo) muestra el mismo patrón:
0/12, 7/72, 5/36 y 1/36. V3 × Filtrado pasó de p=0.12 a p=0.003 al sumar la
4.ª corrida (parte es el mayor n y parte, que esa corrida tuvo más fugas en
C0) y a p<0.001 con la 5.ª. La conclusión se sostiene (C1 tuvo 0 fugas en las
cuatro corridas), pero con un modelo más alineado o menos ruido el valor de
delimitación y clasificación contra prompt injection sigue **sin ser medible**.

### 3.2. V4 × Filtrado: efecto no predicho (24/78 → 0/78)

La hipótesis marca N/A porque filtrado no está pensado contra movimiento
lateral. **Explicación:** el paso 1 de V4 es una *extracción* y reutiliza los
payloads de V2-B, V3-A y V2-C (`ataques/variantes_ataque.md`), justo los que
`filtrar()` bloquea en entrada y cuya credencial redacta en salida. En C1 el
paso 1 quedó bloqueado 16/39 y exitoso 0/39 (C0: 12/39, p<0.001); sin
extracción no hay paso 2. Es un efecto indirecto: frena el primer eslabón, no
el uso cruzado.

### 3.3. V4 × Delimitación: efecto no predicho (24/78 → 2/78) — y corrige un error previo

La hipótesis marca N/A, y una versión anterior de este documento daba por
"refutado por diseño" que delimitación pudiera mover el ASR. Ese razonamiento
era válido solo para el criterio "nada lo bloqueó" (delimitación nunca
bloquea). Con el criterio de **fuga verificada**, delimitación sí puede
reducir el ASR sin bloquear nada: reestructura el prompt y cambia lo que el
modelo hace. Dato: paso 1 exitoso 1/39 en C2 contra 12/39 en C0 (p=0.001). La
dirección se repite en V2 (30/65 → 21/65, p=0.150), aunque ahí no llega a
significancia. Hipótesis: el marcado de la entrada como "no confiable" hace
al modelo de 1B menos propenso a obedecer una petición de extracción; **no
probada** (no se midió el mecanismo, solo el resultado). Es el hallazgo más
inesperado y el más barato de verificar con más repeticiones.

### 3.4. V4 × Mínimo privilegio: "Parcial" agregado, "Sí (directo)" por pasos

El ASR agregado mezcla dos pasos con semántica distinta (trampa de
`CLAUDE.md`, sección 9). Separados (`v4_ataque_completo.md`):

| Config. | Paso 1 exitoso (extracción) | Paso 2 bloqueado | Ataque completo |
|---|---|---|---|
| C0 | 12/39 | 0 | 12/39 |
| C4 | 12/39 | **12 (de los 12 que extrajeron)** | 0/39 |

En C4 la extracción **sigue funcionando** (12/39, por diseño; C0 12/39, p=1) y
el uso cruzado se bloquea en el 100% de los casos en que había algo que usar;
en C0 el paso 2 tuvo éxito 12 de 12. Fisher sobre los casos condicionados
(12/12 vs. 0/12): p≈7×10⁻⁷; sobre el ataque completo sin condicionar (12/39 vs.
0/39): p=0.0002. **Confirma la hipótesis con precisión**, y el agregado también
llega a significancia (p=0.036), aunque frágil.

### 3.5. V4 × Aprobación humana: sin efecto, y eso resuelve un artefacto previo

Con las 7 s entre peticiones, C5 muestra **0 bloqueos** en V1-V4 (antes de la
pausa: 28, atribuidos al límite de tasa saturado) y V4 queda en 20/54 (p=0.46
vs. C0; ASR 37.0% contra 30.8%, sin diferencia distinguible del ruido). La versión anterior a la pausa mostraba
"0/24, p=0.004" para esta celda: era saturación de la cola, no detección.
Aprobación humana **no intercepta nada por contenido** (solo interviene cuando
otro mecanismo bloquea o se excede el límite), exactamente como se diseñó.

### 3.6. V5 × Clasificación (277/371 → 20/20) y V5 en general

Las 20 filas de C3 son todas `nivel_carga=20`; C0 mezcla 2, 4, 6, 8, 10, 50 y
100 y nunca se probó en 20: no hay comparación al mismo nivel. **V5 no se
re-corrió** (CPU en C0/C3/C5; GPU con otra versión del proxy en C6); solo la
conclusión sobre aprobación humana (límite de tasa, por diseño) es robusta.

### 3.7. C6 mide defensa en profundidad, y no mejora a filtrado solo

Con la pausa, C5 solo no bloquea nada, así que los 77 bloqueos de C6
(73 atribuidos a `aprobacion_humana`, 4 a `filtrado`) no son saturación:
`aprobacion_humana` los *intercepta* (convierte un 400 en 429) cuando otro
mecanismo detecta algo. **La atribución al mecanismo que realmente detectó se
pierde por diseño** en C6. Resultado: C6 queda en V2 9/45, V3 0/106, V4 0/54
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
dos lugares interesantes**. Se confirma: filtrado contra extracción (V2) y,
con más datos, contra prompt injection (V3); mínimo privilegio contra uso
cruzado (V4, por pasos y ya también agregado); aprobación humana contra
volumen (V5); y los N/A de V1. Delimitación y clasificación contra prompt
injection (V3) siguen sin poder evaluarse porque el modelo base ya resiste.
Aparecen dos efectos no predichos sobre V4: **filtrado** (frena la extracción
previa) y **delimitación** (reduce la extracción por comportamiento del
modelo, no por bloqueo). El hallazgo transversal es metodológico: qué se mide
importa — criterio de éxito, desglose por pasos, saturación del límite de tasa,
n pequeño y **variabilidad entre corridas** producían "confirmaciones" y
"refutaciones" que eran artefactos.

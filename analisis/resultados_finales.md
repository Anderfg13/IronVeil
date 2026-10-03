# Resultados finales — IronVeil

> Versión del 2026-10-03. **Reemplaza** a la del 2026-09-30, que mezclaba dos
> criterios de éxito distintos entre configuraciones y mezclaba hardware en
> la latencia (ver `docs/LIMPIEZA_DATOS.md`, sección 6). Todo lo de V1-V4
> viene ahora de una re-corrida homogénea en Colab GPU T4: mismas 7
> configuraciones, mismo hardware, mismo código del proxy, fuga verificada
> por contenido.
>
> **Material de apoyo (generado por script):** `analisis/tabla_maestra.{csv,md,tex}`,
> `analisis/matriz_real_vs_hipotesis.md` (+ `matriz_real_pvalores.md`,
> `v4_ataque_completo.md`), `analisis/latencia_peticiones_permitidas.md`,
> `analisis/costo_mecanismos.md`, gráficas en `resultados/graficas_finales/`.

## 1. Pregunta de investigación

> ¿Qué combinación de mecanismos ofrece la mejor relación protección /
> utilidad / costo?

## 2. Qué se midió y con qué incertidumbre

Cinco mecanismos (filtrado, delimitación, clasificación, mínimo privilegio,
aprobación humana + límite de tasa) en 7 configuraciones (C0 baseline … C6
los cinco) contra 5 vectores originales. **ASR = intentos en que la
credencial realmente apareció en la respuesta**, no "nada lo bloqueó".

- V1-V4: C0-C5 con 4 repeticiones, C6 con 3 (n por celda: 20 / 20 / 48 / 24
  para V1 / V2 / V3 / V4; C6: 15 / 15 / 27 / 18). Con n así, **una diferencia
  de uno o dos eventos no se distingue del ruido del LLM**: cada comparación
  lleva su valor p (test exacto de Fisher contra C0).
- V5: no se re-corrió; sus filas vienen de corridas anteriores (otro
  hardware y otras versiones del proxy). Solo se usa donde es robusto por
  diseño.
- Modelo base `llama3.2:1b`, que ya rechaza casi todo por su cuenta (sección 5).

## 3. Tabla maestra (Sección 7.3)

| Config. | Filt. | Del. | Clas. | M.P. | A.H. | ASR prom. V1-V4 (%) | ASR V5 (%) | Falsos positivos | Latencia mediana (ms) | Costo (líneas/horas) |
|---|---|---|---|---|---|---|---|---|---|---|
| C0 | — | — | — | — | — | 32.4 | 74.7 | N/A (baseline) | 382.5 (baseline) | 0 / 0h |
| C1 | ✓ | — | — | — | — | 15.0 | Sin datos | 0/1 — `test_chat_filtrado_no_bloquea_mensaje_legitimo` | 314.0 (-68.5) | 248 / 21h |
| C2 | — | ✓ | — | — | — | 20.6 | Sin datos | N/A — delimitación nunca bloquea | 263.0 (-119.5) | 181 / 15h |
| C3 | — | — | ✓ | — | — | 28.1 | 100.0* | 0/1 — `test_chat_clasificacion_no_bloquea_entrada_legitima` | **588.0 (+205.5)** | 309 / 34h |
| C4 | — | — | — | ✓ | — | 29.2 | Sin datos | 0/1 (a nivel de mecanismo) — `test_validar_privilegio_no_bloquea_texto_sin_credenciales` | 356.0 (-26.5) | 167 / 14h |
| C5 | — | — | — | — | ✓ | 22.6 | 0.2 | 0/1 — `test_chat_aprobacion_humana_no_bloquea_mensaje_legitimo` | 273.0 (-109.5) | 694 / 69h |
| **C6** | ✓ | ✓ | ✓ | ✓ | ✓ | **15.0** | 0.1 | 0/1 — `test_c6_peticion_legitima_pasa_limpia_por_los_5_mecanismos` | 268.0 (-114.5) | 1599 / 153h |

Cómo leerla:
- **ASR promedio V1-V4**: media sin ponderar de los cuatro vectores presentes
  en las 7 configuraciones. **V1 vale 40% en todas** (`V1-A`/`V1-C`: Ollama
  alcanzable directo en la VM de Colab; es del entorno, no de ningún
  mecanismo) y suma ~10 puntos a todas por igual. Sin V1 (V2-V4): C0 29.8,
  C1 6.7, C2 14.2, C3 24.2, C4 25.7, C5 16.9, C6 6.7.
- **\*** V5 en C3: 20 filas, todas en un solo nivel de carga que C0 nunca
  probó; no es comparable (`matriz_real_vs_hipotesis.md`, 3.5).
- **Latencia mediana**: de las peticiones de chat (V2-V4) que llegaron al
  modelo. Las bloqueadas se excluyen porque responden en milisegundos sin
  pagar inferencia (incluirlas hacía parecer "más rápidas" a C5/C6). **Las
  diferencias de ~100 ms no son distinguibles del ruido; solo C3 (+205 ms)
  destaca.** Mismo hardware y mismo código para las 7. C6 tiene solo 15
  peticiones que llegan al modelo.
- **Falsos positivos** es evidencia puntual (un test por configuración), no
  una tasa sobre tráfico legítimo representativo.

## 4. Gráficas (`resultados/graficas_finales/`, dpi=300)

1. `asr_por_configuracion.png` — ASR promedio V1-V4 por configuración.
2. `latencia_por_configuracion.png` — latencia mediana (escala log).
3. `matriz_cobertura_heatmap.png` — hipótesis vs. real; "N/A (n.s.)" marca
   celdas cuya diferencia contra C0 no es significativa (Fisher p ≥ 0.05).

## 5. Qué se encontró

**5.1. Pocos efectos son distinguibles del ruido, y los que lo son no son los que
predecía la hipótesis.** De 25 pares vector × mecanismo, solo estos
muestran un efecto estadístico (p ≤ 0.004): V4 × Filtrado (8/24 → 0/24),
V4 × Aprobación humana (8/24 → 0/24) y V5 × Aprobación humana; más el paso 2
de V4 × Mínimo privilegio (5/5 bloqueado). Detalle y vereditos celda por
celda en `analisis/matriz_real_vs_hipotesis.md`.

**5.2. Mínimo privilegio hace exactamente lo que se diseñó.** En C4 la
extracción (paso 1) sigue funcionando (5/12, por diseño) y el uso cruzado
(paso 2) se bloquea en 5 de 5; en C0 el paso 2 tuvo éxito en 4 de 4. Ataque
completo: 4/12 → 0/12. El ASR agregado de V4 lo muestra diluido (8/24 →
5/24, p=0.52) porque mezcla los dos pasos.

**5.3. Filtrado frena V4 de forma indirecta.** El paso 1 de V4 reutiliza
payloads de extracción (V2/V3) que filtrado sí cubre; sin extracción no hay
uso cruzado (paso 1 bloqueado 7/12 en C1, exitoso 0/12).

**5.4. Contra prompt injection (V3) no se puede medir el aporte, porque el
modelo base ya resiste.** C0 filtra el secreto en 3 de 48 intentos; ningún
mecanismo tiene espacio para mostrar una reducción. Los mecanismos sí
actúan (clasificación bloqueó 14/48, filtrado 7/43), pero casi todo lo que
bloquean es lo que el modelo ya habría rechazado. Que "no se vea efecto" es
una limitación del experimento (modelo de 1B muy alineado), no evidencia de
que esos mecanismos no sirvan.

**5.5. La protección aparente de C5 y C6 es sobre todo límite de tasa.** En
C6 los 36 bloqueos de V1-V4 se atribuyen a `aprobacion_humana`; en C5, 28.
La batería dispara peticiones más rápido que el límite (10/min), así que gran
parte de lo "bloqueado" se encola sin que ningún otro mecanismo haya juzgado
el contenido. Por eso el 15.0% de C6 (vs. 32.4% de C0) **no puede
atribuirse a la defensa en profundidad** con estos datos. Aprobación humana
sí es efectiva contra volumen (V5: 0.2% vs. 74.7%), por diseño.

**5.6. Ningún combo llega a 0 frente a un atacante adaptativo.** El sondeo
iterativo V6-C (`ataques/vector6_adaptativo.py`) encontró en 3 intentos un
parafraseo que atraviesa los 5 mecanismos (corrida del 2026-09-30, GPU, otra
versión del proxy; el modelo igual se negó a revelar el secreto).

## 6. Respuesta a la pregunta de investigación

Evidencia por mecanismo (costo = horas de implementación, estimación;
latencia = mediana sobre peticiones que llegan al modelo, C0 = 382.5 ms):

| Mecanismo | Efecto medido sobre fuga | Qué bloquea | Costo impl. | Costo en latencia |
|---|---|---|---|---|
| Filtrado | V4 8/24→0/24 (p=0.004); V2 10/20→4/20 (p=0.10) | 24 peticiones | 21h | ninguno distinguible |
| Delimitación | ninguno distinguible (V4 p=0.07) | nada, por diseño | 15h | ninguno distinguible |
| Clasificación | ninguno distinguible (efecto suelo en V3) | 26 peticiones | 34h | **+205 ms** |
| Mínimo privilegio | V4 paso 2 bloqueado 5/5; ataque completo 4/12→0/12 | 5 (uso cruzado) | 14h (la más barata) | ninguno distinguible |
| Aprobación humana | V5 por volumen; en V1-V4 es límite de tasa | 28 (volumen) | 69h | ninguno distinguible |

**Protección.** C6 tiene el menor ASR medido (15.0% frente a 32.4%), pero esa
cifra la sostiene sobre todo el límite de tasa (5.5), no la combinación de
defensas; los efectos *de contenido* demostrables son de filtrado y mínimo
privilegio. **Utilidad.** Sin evidencia de falsos positivos en el caso
puntual verificado por configuración; no es una tasa medida. **Costo.**
Mínimo privilegio y filtrado dan los efectos demostrables más baratos
(14h y 21h) y sin sobrecosto de latencia; clasificación es la única con
sobrecosto de latencia claro (+205 ms, y en el despliegue Prompt Guard
corre en CPU aunque haya GPU, así que es un costo reducible) y la más
cara por hora sin efecto medible aquí; aprobación humana es la más cara de
implementar y su valor está en el volumen, no en el contenido.

**Respuesta defendible:** con la evidencia disponible, la mejor relación
protección/costo no la da la configuración con más mecanismos sino la que
combina **mínimo privilegio y filtrado** —los únicos con efecto de contenido
demostrable y costo bajo (35h en total)— más **aprobación humana si el
riesgo relevante es el abuso por volumen**. Esa combinación **no se
ejecutó** como configuración (solo C1-C5 y C6), así que es una
recomendación derivada de efectos por mecanismo, no una medición.
**Clasificación y delimitación no muestran valor medible aquí**: la primera
por el efecto suelo (modelo base muy alineado) y su costo de latencia; la
segunda, por diseño, nunca bloquea. Es razonable esperar que la clasificación
importe más con un modelo menos alineado, pero eso es una hipótesis que este
experimento no probó. C6 sigue siendo la única configuración con defensa en
profundidad por construcción y la que mejor tolera un atacante que evade
una capa, pero este experimento no puede demostrar ese beneficio.

## 7. Limitaciones declaradas

- **n pequeño**: 15-48 intentos por celda; la mayoría de las diferencias
  no es estadísticamente distinguible. Varias celdas de la matriz son
  "no concluyentes", no "sin efecto".
- **Efecto suelo**: el modelo base filtra el secreto en 3/48 de V3 en C0.
- **Límite de tasa fijo** (10/min por cliente) saturado por la propia
  batería en C5 y C6: la atribución de mecanismo en esas dos es poco confiable.
  Además V4 corre justo después de V1-V3 sin pausa.
- **V1 es del entorno** (40% en todas); **V5 no se re-corrió** (datos
  anteriores, otro hardware/código; C3 en un solo nivel de carga).
- **Mediciones de cliente**: los scripts no ven los bloqueos en *salida*
  (el proxy responde 200 con el texto retenido), así que algunos bloqueos de
  clasificación o filtrado de salida figuran como "permitido" en el CSV (p. ej.
  un V2-D de C6 que el log del proxy registra bloqueado por clasificación; hay
  6 filas de C6 que no cruzan limpio contra `eventos.jsonl`).
- **Horas de costo** son una estimación (no hubo registro de tiempo);
  **falsos positivos** es evidencia puntual.
- **Prompt Guard corrió en CPU** en estas corridas aunque hubiera GPU
  (`pipeline()` sin `device`): parte de los +205 ms de clasificación es
  evitable. Ya se corrigió en el código (`device=0` si hay CUDA); la latencia
  de C3 y C6 de este documento es anterior a ese cambio.
- **LLM no determinista**; los resultados no se reproducen bit a bit.
- Dos ambigüedades de datos abiertas, documentadas en
  `docs/LIMPIEZA_DATOS.md` (`paso_bloqueado` en V4 "paso 2 omitido"; filas
  de 2026-09-18/19 con `mecanismo_que_bloqueo` discordante).

## 8. Qué queda pendiente

1. Re-correr V5 en GPU con el código actual y los mismos niveles de carga en
   las 7 configuraciones.
2. Re-medir la latencia de clasificación (C3, C6) con Prompt Guard en GPU
   (ya implementado, falta correrlo).
3. Un modelo base menos alineado (o un conjunto de payloads más fuertes)
   para que V3 tenga espacio de medición.
4. Re-correr C5/C6 con la pausa entre peticiones (`--pausa-entre-peticiones-s`,
   ya implementada) para que dejen de medir saturación del límite de tasa.
5. Ejecutar la combinación mínimo privilegio + filtrado (+ aprobación
   humana) como configuración propia, para convertir la recomendación en
   una medición.

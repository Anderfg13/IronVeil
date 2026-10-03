# Resultados finales — IronVeil

> Versión del 2026-10-04, sobre tres re-corridas en Colab GPU T4. **Reemplaza**
> a las anteriores: la del 2026-09-30 mezclaba criterios de éxito y hardware,
> y la del 2026-10-03 atribuía a defensa lo que era saturación del límite de
> tasa en C5/C6 (ver `docs/LIMPIEZA_DATOS.md`, sección 6).
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
aprobación humana + límite de tasa) en 7 configuraciones (C0 baseline … C6 los
cinco) contra 5 vectores originales. **ASR = intentos en que la credencial
realmente apareció en la respuesta.**

- V1-V4: C0-C4 con 7 repeticiones (n = 35 / 35 / 84 / 42 intentos por vector);
  C5 y C6 con 3 repeticiones y 7 s entre peticiones, para no saturar el límite
  de 10/min (n = 15 / 15 / 36 y 34 / 18). Cada comparación lleva su valor p
  (test exacto de Fisher contra C0): **una diferencia de uno o dos eventos no
  se distingue del ruido del LLM**.
- V5: no se re-corrió; sus filas son de corridas anteriores (otro hardware y
  versiones del proxy). Solo se usa donde es robusto por diseño.
- Modelo base `llama3.2:1b`, que ya rechaza casi todo por su cuenta (5.4).

## 3. Tabla maestra (Sección 7.3)

| Config. | Filt. | Del. | Clas. | M.P. | A.H. | ASR prom. V1-V4 (%) | ASR V5 (%) | Falsos positivos | Latencia mediana (ms) | Costo (líneas/horas) |
|---|---|---|---|---|---|---|---|---|---|---|
| C0 | — | — | — | — | — | 32.4 | 74.7 | N/A (baseline) | 375.0 (baseline) | 0 / 0h |
| C1 | ✓ | — | — | — | — | **15.0** | Sin datos | 0/1 — `test_chat_filtrado_no_bloquea_mensaje_legitimo` | 294.0 (-81.0) | 248 / 21h |
| C2 | — | ✓ | — | — | — | 19.2 | Sin datos | N/A — delimitación nunca bloquea | 262.0 (-113.0) | 181 / 15h |
| C3 | — | — | ✓ | — | — | 26.1 | 100.0* | 0/1 — `test_chat_clasificacion_no_bloquea_entrada_legitima` | **605.0 (+230.0)** | 309 / 34h |
| C4 | — | — | — | ✓ | — | 29.9 | Sin datos | 0/1 (a nivel de mecanismo) — `test_validar_privilegio_no_bloquea_texto_sin_credenciales` | 340.5 (-34.5) | 167 / 14h |
| C5 | — | — | — | — | ✓ | 34.2 | 0.2 | 0/1 — `test_chat_aprobacion_humana_no_bloquea_mensaje_legitimo` | 386.0 (+11.0) | 694 / 69h |
| **C6** | ✓ | ✓ | ✓ | ✓ | ✓ | **15.0** | 0.1 | 0/1 — `test_c6_peticion_legitima_pasa_limpia_por_los_5_mecanismos` | 429.5 (+54.5) | 1599 / 153h |

Cómo leerla:
- **ASR promedio V1-V4**: media sin ponderar de los cuatro vectores presentes
  en las 7 configuraciones. **V1 vale 40% en todas** (`V1-A`/`V1-C`: Ollama
  alcanzable directo en la VM de Colab; es del entorno, no de ningún
  mecanismo) y suma ~10 puntos a todas por igual. Sin V1 (V2-V4): C0 29.8,
  C1 6.7, C2 12.3, C3 21.5, C4 26.6, C5 32.2, C6 6.7.
- **\*** V5 en C3: 20 filas en un solo nivel de carga que C0 nunca probó; no
  comparable.
- **Latencia mediana**: de las peticiones de chat (V2-V4) que llegaron al
  modelo (las bloqueadas responden en milisegundos sin pagar inferencia).
  **Diferencias de ~100 ms no son distinguibles del ruido; solo C3 (+230 ms)
  destaca.** C6: 32 peticiones llegan al modelo.
- **Falsos positivos** es evidencia puntual (un test por configuración), no una
  tasa sobre tráfico legítimo.

## 4. Gráficas (`resultados/graficas_finales/`, dpi=300)

1. `asr_por_configuracion.png` — ASR promedio V1-V4.
2. `latencia_por_configuracion.png` — latencia mediana (escala log).
3. `matriz_cobertura_heatmap.png` — hipótesis vs. real; "N/A (n.s.)" = Fisher
   p ≥ 0.05.

## 5. Qué se encontró

**5.1. Filtrado es el mecanismo con mejor evidencia.** Reduce V2 (18/35 →
7/35, p=0.012) y V4 (14/42 → 0/42, p<0.001), sin costo de latencia
distinguible. Su efecto sobre V4 es indirecto: frena la extracción del paso 1.

**5.2. Mínimo privilegio hace exactamente lo que se diseñó.** En C4 la
extracción sigue funcionando (6/21, por diseño) y el uso cruzado se bloquea 6
de 6; en C0 el paso 2 tuvo éxito 7 de 7. Ataque completo: 7/21 → 0/21
(p=0.0006 sobre los casos condicionados). El ASR agregado de V4 lo muestra
diluido (14/42 → 6/42, p=0.07) porque mezcla los dos pasos.

**5.3. Delimitación reduce V4 sin bloquear nada (14/42 → 2/42, p=0.002).**
Efecto no predicho por la hipótesis. Con el criterio de fuga verificada,
reestructurar el prompt cambia lo que el modelo hace; la dirección se repite
en V2 (p=0.087). Mecanismo causal no probado.

**5.4. Contra prompt injection (V3) no se puede medir el aporte**, porque el
modelo base ya resiste: C0 filtra el secreto en 4/84 intentos. Los mecanismos
sí actúan (clasificación bloqueó 46 peticiones, filtrado 38), pero casi todo
lo que bloquean es lo que el modelo ya rechazaba. Es una limitación del
experimento, no evidencia de que no sirvan.

**5.5. Aprobación humana no intercepta nada por contenido.** Con el ritmo
bajo el límite, C5 tiene 0 bloqueos en V1-V4 y un ASR igual a C0 (34.2 vs.
32.4). Solo actúa cuando otro mecanismo bloquea (lo convierte en cola) o se
excede el límite de tasa: contra volumen (V5, 0.2% vs. 74.7%) es efectiva, por
diseño. Las corridas anteriores mostraban "protección" de C5 que era
saturación de la cola.

**5.6. C6 no mejora a filtrado solo en estas cuatro familias.** C6 y C1
quedan en 15.0% (V2 20%, V3 0%, V4 0% en ambas). En C6 los bloqueos
(25 atribuidos a `aprobacion_humana`, 1 a `filtrado`) son detecciones de otros
mecanismos interceptadas por la cola; **la atribución al mecanismo que
detectó se pierde por diseño**. El valor de las capas extra aparecería si
filtrado se evade, y se demostró que existe esa evasión: el sondeo V6-C
(`ataques/vector6_adaptativo.py`) encontró en 3 intentos un parafraseo que
atraviesa los 5 mecanismos (corrida del 2026-09-30, otra versión del proxy; el
modelo igual se negó). Ningún combo llega a 0 frente a un atacante adaptativo.

**5.7. Clasificación tiene costo de latencia y no muestra efecto medible.**
+230 ms (605 vs. 375 ms) sobre peticiones que llegan al modelo; sin reducción
de fuga significativa (V2 p=0.34, V4 p=0.47). El tiempo que el proxy mide
dentro del clasificador es solo ~68 ms de mediana (C3, entrada + salida);
**los ~160 ms restantes del sobrecosto no están explicados por el
clasificador**. Pasar Prompt Guard a GPU no cambió esa cifra (68 ms antes y
después).

## 6. Respuesta a la pregunta de investigación

| Mecanismo | Efecto medido sobre fuga | Qué bloquea | Costo impl. | Latencia (vs. C0 = 375 ms) |
|---|---|---|---|---|
| Filtrado | V2 p=0.012; V4 p<0.001 | 38 peticiones | 21h | −81 ms (n.s.) |
| Delimitación | V4 p=0.002 (V2 p=0.087) | nada, por diseño | 15h | −113 ms (n.s.) |
| Clasificación | ninguno distinguible (efecto suelo en V3) | 46 peticiones | 34h | **+230 ms** |
| Mínimo privilegio | V4 paso 2 bloqueado 6/6; ataque completo 7/21→0/21 | 6 (uso cruzado) | 14h | −35 ms (n.s.) |
| Aprobación humana | solo V5 (volumen); ninguno en V1-V4 | 0 en V1-V4 | 69h | +11 ms (n.s.) |

**Respuesta defendible:** con la evidencia disponible, la mejor relación
protección/costo **no** la da la configuración con más mecanismos sino
**filtrado + delimitación + mínimo privilegio** (los tres con efecto
demostrable sobre fuga, 50h en total, sin sobrecosto de latencia
distinguible), más **aprobación humana solo si el riesgo relevante es abuso
por volumen**. La evidencia: C1 (21h) iguala a C6 (153h) en ASR de V1-V4
(15.0% ambas), y los efectos demostrables de contenido son de filtrado,
delimitación y mínimo privilegio. **Esa combinación no se ejecutó como
configuración** (solo C1-C5 y C6): es una recomendación derivada de efectos
por mecanismo, no una medición, y habría que correrla.
**Clasificación no muestra valor medible aquí** (efecto suelo + 230 ms +
34h); que importe con un modelo menos alineado es una hipótesis no probada.
**C6 sigue siendo la única con defensa en profundidad por construcción**, y
esa redundancia es lo que cubriría una evasión de filtrado como la de V6-C,
pero este experimento no puede demostrar ese beneficio.

## 7. Limitaciones declaradas

- **n pequeño**: 15-84 intentos por celda; muchas diferencias no son
  distinguibles del ruido. Varias celdas son "no concluyentes", no "sin efecto".
- **Efecto suelo** en V3 (modelo base de 1B muy alineado); **V1 es del
  entorno** (40% en todas).
- **V5 no se re-corrió** (datos anteriores, otro hardware/código; C3 en un solo
  nivel de carga).
- **C6 pierde la atribución**: la cola intercepta los bloqueos de los demás
  mecanismos. C5/C6 son 3 repeticiones (vs. 7 de C0-C4) y con pausa de 7 s.
- **Mediciones de cliente**: los scripts no ven los bloqueos en *salida* (el
  proxy responde 200 con texto retenido), así que algunos figuran "permitido"
  (ej. un V2-D de C6); esas filas no cruzan limpio contra `eventos.jsonl`.
- **Latencia**: mediana de peticiones servidas; ~100 ms de ruido de
  generación del LLM; solo C3 destaca y su sobrecosto no se explica por completo
  con el tiempo del clasificador medido por el proxy.
- **Horas de costo** son una estimación; **falsos positivos** es evidencia
  puntual; el **LLM no es determinista**.
- Dos ambigüedades de datos abiertas (`docs/LIMPIEZA_DATOS.md`): `paso_bloqueado`
  en V4 "paso 2 omitido", y filas de 2026-09-18/19 con
  `mecanismo_que_bloqueo` discordante.

## 8. Qué queda pendiente

1. Re-correr V5 en GPU con el código actual y los mismos niveles de carga en
   las 7 configuraciones.
2. Medir por etapas dónde se va el tiempo en C3 (llamada al modelo de chat
   vs. clasificador) para explicar los ~160 ms sin atribuir. De eso depende
   evaluar un clasificador alternativo (p. ej. un modelo de decisión como
   Jev): con ~68 ms medidos dentro del clasificador, su techo de ganancia es
   bajo.
3. Ejecutar filtrado + delimitación + mínimo privilegio como configuración
   propia, para convertir la recomendación en una medición.
4. Verificar la causa del efecto de delimitación sobre V4 y V2 con más
   repeticiones y un diseño que lo aísle.
5. Un modelo base menos alineado (o payloads más fuertes) para que V3 tenga
   espacio de medición.

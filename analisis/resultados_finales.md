# Resultados finales — IronVeil

> Versión del 2026-10-06, sobre **cinco corridas** en Colab GPU T4 (2026-10-02,
> las dos del 2026-10-03, la del 2026-10-05 y la del 2026-10-06) más una
> **medición directa del costo por mecanismo** hecha dentro del proxy.
> **Reemplaza** a la versión del 2026-10-05. Qué cambió: se sumó la 5.ª corrida
> (3 repeticiones más por configuración; **ningún veredicto de la matriz cambió**,
> solo porcentajes, n y valores p) y el costo de latencia se midió de nuevo con
> los recortes del clasificador: **la mediana no cambió (≈ 75 ms) pero el p95
> bajó de 133 a 91 ms en C3 y de 160 a 95 ms en C6** (sección 5.7).
>
> **De dónde sale cada cosa:** `docs/DE_DONDE_SALE_CADA_TABLA.md` (mapa
> tabla/figura → script → datos). **Este archivo es texto escrito a mano**
> sobre tablas generadas por script: si se ingesta otra corrida, hay que
> actualizar las cifras de aquí y de `analisis/matriz_real_vs_hipotesis.md`.
>
> **Material de apoyo (generado por script):** `analisis/tabla_maestra.{csv,md,tex}`,
> `analisis/matriz_real_vs_hipotesis.md` (+ `matriz_real_pvalores.md`,
> `v4_ataque_completo.md`), `analisis/costo_por_mecanismo.{csv,md}` y
> `costo_por_mecanismo_retenidas.{csv,md}`, `analisis/latencia_peticiones_permitidas.md`,
> `analisis/costo_mecanismos.md`, gráficas en `resultados/graficas_finales/` (las
> versiones reemplazadas, en `resultados/graficas_anteriores/`).

## 1. Pregunta de investigación

> ¿Qué combinación de mecanismos ofrece la mejor relación protección /
> utilidad / costo?

## 2. Qué se midió y con qué incertidumbre

Cinco mecanismos (filtrado, delimitación, clasificación, mínimo privilegio,
aprobación humana + límite de tasa) en 7 configuraciones (C0 baseline … C6 los
cinco) contra 5 vectores originales. **ASR = intentos en que la credencial
realmente apareció en la respuesta.**

- V1-V4: C0-C4 con 13 repeticiones (n = 65 / 65 / 156 / 78 intentos por
  vector); C5 y C6 con 9 repeticiones y 7 s entre peticiones, para no saturar
  el límite de 10/min (n = 45 / 45 / 108 y 106 / 54). Cada comparación lleva su
  valor p (test exacto de Fisher contra C0): **una diferencia de uno o dos
  eventos no se distingue del ruido del LLM**.
- **Las repeticiones no son idénticas entre sí**: el ASR de C0 en V3 fue 0/12,
  4/72, 5/36 y 3/36 en cuatro corridas con la misma configuración. Es el LLM no
  determinista; se declara como limitación.
- V5: no se re-corrió; sus filas son de corridas anteriores (otro hardware y
  versiones del proxy). Solo se usa donde es robusto por diseño.
- Modelo base `llama3.2:1b`, que ya rechaza casi todo por su cuenta (5.4).
- **Costo de latencia**: medido aparte, dentro de cada petición (sección 5.8;
  2 repeticiones × 30 mensajes legítimos por configuración).

## 3. Tabla maestra (Sección 7.3)

| Config. | Filt. | Del. | Clas. | M.P. | A.H. | ASR prom. V1-V4 (%) | ASR V5 (%) | Falsos positivos | Latencia mediana (ms) | **Sobrecosto propio (ms)** | Costo (líneas/horas) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C0 | — | — | — | — | — | 31.2 | 74.7 | N/A (baseline) | 369.5 (baseline) | 0.23 (p95 0.67) | 0 / 0h |
| C1 | ✓ | — | — | — | — | **15.0** | Sin datos | 0/1 — `test_chat_filtrado_no_bloquea_mensaje_legitimo` | 302.0 (-67.5) | 0.40 (p95 1.00) | 248 / 21h |
| C2 | — | ✓ | — | — | — | 19.7 | Sin datos | N/A — delimitación nunca bloquea | 263.0 (-106.5) | 0.29 (p95 0.86) | 181 / 15h |
| C3 | — | — | ✓ | — | — | 28.6 | 100.0* | 0/1 — `test_chat_clasificacion_no_bloquea_entrada_legitima` | 537.0 (+167.5) | **76.6 (p95 90.6)** | 309 / 34h |
| C4 | — | — | — | ✓ | — | 28.2 | Sin datos | 0/1 (a nivel de mecanismo) — `test_validar_privilegio_no_bloquea_texto_sin_credenciales` | 338.0 (-31.5) | 0.46 (p95 0.95) | 167 / 14h |
| C5 | — | — | — | — | ✓ | 32.4 | 0.2 | 0/1 — `test_chat_aprobacion_humana_no_bloquea_mensaje_legitimo` | 401.0 (+31.5) | 0.35 (p95 0.85) | 694 / 69h |
| **C6** | ✓ | ✓ | ✓ | ✓ | ✓ | **15.0** | 0.1 | 0/1 — `test_c6_peticion_legitima_pasa_limpia_por_los_5_mecanismos` | 419.0 (+49.5) | **75.2 (p95 94.9)** | 1599 / 153h |

Cómo leerla:
- **ASR promedio V1-V4**: media sin ponderar de los cuatro vectores presentes
  en las 7 configuraciones. **V1 vale 40% en todas** (`V1-A`/`V1-C`: Ollama
  alcanzable directo en la VM de Colab; es del entorno, no de ningún
  mecanismo) y suma 10 puntos a todas por igual. Sin V1 (V2-V4): C0 28.2,
  C1 6.7, C2 12.9, C3 24.7, C4 24.3, C5 29.9, C6 6.7.
- **\*** V5 en C3: 20 filas en un solo nivel de carga que C0 nunca probó; no
  comparable.
- **Sobrecosto propio** (la cifra que debe citarse como costo de latencia):
  latencia total menos el tiempo del modelo, medido dentro de cada petición
  que llegó al modelo; mediana y p95. **C0 es el proxy sin ningún mecanismo**
  (HTTP + JSON + registro del log): 0.23 ms. Sin clasificación, todo el proxy
  cuesta menos de ~0.5 ms; con clasificación, ≈ 75-77 ms de mediana.
- **Latencia mediana (columna antigua)**: mediana de las peticiones de chat
  (V2-V4) que llegaron al modelo, y su diferencia contra C0. **Se conserva
  solo como contraste**: incluye el tiempo del modelo, que cambia entre
  configuraciones, y por eso C1 y C2 salen «más rápidas» que el baseline y C3
  pasó de +230 ms (versión anterior) a +155 ms y luego a +167.5 ms solo por sumar datos. No debe
  citarse como costo de los mecanismos.
- **Falsos positivos** es evidencia puntual (un test por configuración), no una
  tasa sobre tráfico legítimo.

## 4. Gráficas (`resultados/graficas_finales/`, dpi=300)

1. `asr_por_configuracion.png` — ASR promedio V1-V4.
2. `sobrecosto_propio_por_configuracion.png` — costo propio (mediana y p95,
   escala log). **La que va en el informe para latencia.**
3. `latencia_por_configuracion.png` — latencia mediana contra C0 (escala log);
   solo de contraste, ver la nota de la tabla maestra.
4. `matriz_cobertura_heatmap.png` — hipótesis vs. real; "N/A (n.s.)" = Fisher
   p ≥ 0.05.

## 5. Qué se encontró

**5.1. Filtrado es el mecanismo con mejor evidencia.** Reduce V2 (30/65 →
13/65, p=0.003), V3 (12/156 → 0/147, p<0.001) y V4 (24/78 → 0/78, p<0.001), con
un costo propio de 0.4 ms. Su efecto sobre V4 es indirecto: frena la extracción
del paso 1.

**5.2. Mínimo privilegio hace exactamente lo que se diseñó.** En C4 la
extracción sigue funcionando (12/39, por diseño) y el uso cruzado se bloquea 12
de 12; en C0 el paso 2 tuvo éxito 12 de 12. Ataque completo: 12/39 → 0/39
(p=0.0002; sobre los casos condicionados, p≈7×10⁻⁷). El ASR agregado de V4
queda en 24/78 → 12/78 (p=0.036) porque mezcla los dos pasos.

**5.3. Delimitación reduce V4 sin bloquear nada (24/78 → 2/78, p<0.001).**
Efecto no predicho por la hipótesis. Con el criterio de fuga verificada,
reestructurar el prompt cambia lo que el modelo hace; la dirección se repite
en V2 (p=0.150, no significativo). Mecanismo causal no probado.

**5.4. Contra prompt injection (V3) solo filtrado se puede medir.** El modelo
base ya resiste: C0 filtra el secreto en 12/156 intentos (7.7%; por corrida
0/12, 4/72, 5/36, 3/36). Filtrado lo lleva a 0/147 (p<0.001); delimitación,
clasificación y aprobación humana quedan en 6/156, 7/156 y 4/108 (p ≥ 0.20):
**no concluyentes**, no «sin efecto». Los mecanismos sí actúan (clasificación
bloqueó 84 peticiones en V1-V4, filtrado 68) pero casi todo lo que bloquean es
lo que el modelo ya rechazaba. Es una limitación del experimento.

**5.5. Aprobación humana no intercepta nada por contenido.** Con el ritmo
bajo el límite, C5 tiene 0 bloqueos en V1-V4 y un ASR igual a C0 (32.4 vs.
31.2). Solo actúa cuando otro mecanismo bloquea (lo convierte en cola) o se
excede el límite de tasa: contra volumen (V5, 0.2% vs. 74.7%) es efectiva, por
diseño. Las corridas anteriores a la pausa mostraban "protección" de C5 que era
saturación de la cola.

**5.6. C6 no mejora a filtrado solo en estas cuatro familias.** C6 y C1
quedan en 15.0% (V2 20%, V3 0%, V4 0% en ambas). En C6 los bloqueos
(73 atribuidos a `aprobacion_humana`, 4 a `filtrado`) son detecciones de otros
mecanismos interceptadas por la cola; **la atribución al mecanismo que
detectó se pierde por diseño**. El valor de las capas extra aparecería si
filtrado se evade, y se demostró que existe esa evasión: el sondeo V6-C
(`ataques/vector6_adaptativo.py`) encontró en 3 intentos un parafraseo que
atraviesa los 5 mecanismos (corrida del 2026-09-30, otra versión del proxy; el
modelo igual se negó). Ningún combo llega a 0 frente a un atacante adaptativo.

**5.7. Clasificación tiene costo de latencia y no muestra efecto medible.**
Costo propio de **76.6 ms** de mediana (p95 91 ms) en C3; sin reducción de fuga
significativa (V2 p=0.72, V3 p=0.34, V4 p=0.86). Casi todo es el clasificador:
76.0 ms medidos dentro de él, que desde la 5.ª corrida se separan en **entrada
(Prompt Guard) ≈ 39 ms y salida (Llama Guard) ≈ 38 ms** en C3 (C6: 32 y 36 ms).
La versión anterior atribuía +230 ms a C3 y decía que ~160 ms no estaban
explicados: **era ruido de la mediana del modelo**, no un costo del proxy.

*Qué cambió con los recortes de latencia* (Prompt Guard en fp16 si hay GPU,
Llama Guard con `num_predict=32` y temperatura 0, `OLLAMA_MAX_LOADED_MODELS=4`;
ver `docs/FUENTE_DE_VERDAD.md`): **la mediana no cambió** (C3 80.8 → 76.6 ms,
IC 95 % −11.9 a +2.8; C6 76.0 → 75.2 ms) pero **la cola sí**: p95 de C3 133 →
91 ms y de C6 160 → 95 ms (máximo de C6 175 → 98 ms), consistente en las dos
mitades de la corrida. **Todo el cambio está en los mensajes largos** (444
palabras): sobrecosto de C3 131 → 79 ms y de C6 158 → 90 ms, mientras que en
los cortos (10 palabras) y medianos (84) no hay diferencia (≈ 65-73 ms: un piso
fijo de tokenización, Python, copias CPU↔GPU y la llamada a Llama Guard). Como
Llama Guard evalúa la respuesta del modelo y su tiempo es estable (35-38 ms) en
las tres longitudes, **la parte que depende de la longitud solo puede ser de
Prompt Guard**: lo más probable es que la causa sea fp16 (la atención crece con
el cuadrado de los tokens), pero **es inferencia**: la comparación es entre dos
sesiones de Colab y los cambios se aplicaron juntos; la comprobación directa
(fp32 contra fp16 en la misma sesión) es la celda 7b del notebook, cuya salida
no se guardó. Las decisiones del clasificador **no cambiaron**: bloquea las
mismas variantes (V2-B, V3-A/D/G, V4-A/B paso 1; 19 de 69 en C3, igual que el
2026-10-05) y los 60 mensajes legítimos pasaron en C0, C3 y C6. **No se
midió la escalabilidad** (esta corrida no tiene V5).

**5.8. Costo propio medido directamente (corrida de Colab del 2026-10-06).**
El proxy cronometra cada mecanismo y el modelo dentro de cada petición
(`latencia_<pieza>_us`); la resta total − modelo da el costo propio sin
compararse contra C0. Resultado (mediana por mecanismo): filtrado 0.110 ms,
delimitación 0.011 ms, mínimo privilegio 0.031 ms, límite de peticiones
0.018 ms, aprobación humana (decidir si retener) 0.001 ms, **clasificación
76.0 ms (C3) y 75.0 ms (C6)**. **Rechazar casi no cuesta**: retener por
filtrado o mínimo privilegio < 1 ms, por clasificación ≈ 28 ms (p95 28), y en
C6 encolar una petición ≈ 1 ms (p95 39). Primera medición (2026-10-05, antes de
los recortes, archivada en la historia de git): clasificación 79.6 ms (C3) y
75.4 ms (C6). Detalle y metodología: `analisis/costo_por_mecanismo.md`,
`docs/FUENTE_DE_VERDAD.md` (entradas del 2026-10-05 y 2026-10-06).

**5.9. Hallazgo adicional (multilingüe, indicio y no demostración).** El mismo
ataque de «ignora tus instrucciones» en francés que el filtro de patrones no
detecta (C1: 0 de 4) lo retuvo Prompt Guard en C3 y C6 (4 de 4); la credencial
cruzada no la ve Prompt Guard (0 de 4) y sí mínimo privilegio. Es una sola
frase con n = 4, en dos corridas
(`resultados/2026-10-05|06/costo_mecanismos_C*_*.jsonl`): no prueba cobertura
general de ese idioma.

## 6. Respuesta a la pregunta de investigación

| Mecanismo | Efecto medido sobre fuga | Qué bloquea | Costo impl. | Costo propio de latencia (mediana, ms) |
|---|---|---|---|---|
| Filtrado | V2 p=0.003; V3 p<0.001; V4 p<0.001 | 68 peticiones | 21h | 0.40 (todo el proxy en C1) |
| Delimitación | V4 p<0.001 (V2 p=0.150) | nada, por diseño | 15h | 0.29 |
| Clasificación | ninguno distinguible (V2 p=0.72, V3 p=0.34, V4 p=0.86) | 84 peticiones | 34h | **76.6** |
| Mínimo privilegio | V4 paso 2 bloqueado 12/12; ataque completo 12/39→0/39 | 12 (uso cruzado) | 14h | 0.46 |
| Aprobación humana | solo V5 (volumen); ninguno en V1-V4 | 0 en V1-V4 | 69h | 0.35 |

**Respuesta defendible:** con la evidencia disponible, la mejor relación
protección/costo **no** la da la configuración con más mecanismos sino
**filtrado + delimitación + mínimo privilegio** (los tres con efecto
demostrable sobre fuga, 50h en total, **y con un costo propio de latencia
inferior a 1 ms medido directamente**), más **aprobación humana solo si el
riesgo relevante es abuso por volumen**. La evidencia: C1 (21h) iguala a C6
(153h) en ASR de V1-V4 (15.0% ambas), y los efectos demostrables de contenido
son de filtrado, delimitación y mínimo privilegio. **Esa combinación no se
ejecutó como configuración** (solo C1-C5 y C6): es una recomendación derivada
de efectos por mecanismo, no una medición, y habría que correrla.
**Clasificación no muestra valor medible aquí** (efecto suelo + ≈ 76 ms +
34h); que importe con un modelo menos alineado es una hipótesis no probada.
**C6 sigue siendo la única con defensa en profundidad por construcción**, y
esa redundancia es lo que cubriría una evasión de filtrado como la de V6-C,
pero este experimento no puede demostrar ese beneficio.

## 7. Limitaciones declaradas

- **n pequeño**: 30-120 intentos por celda; muchas diferencias no son
  distinguibles del ruido. Varias celdas son "no concluyentes", no "sin efecto".
- **Variabilidad entre corridas**: configuraciones idénticas dieron ASR
  distintos (C0 en V3: 0/12, 4/72, 5/36, 3/36). Dos celdas (V3 × Filtrado y
  V4 × Mín. Privilegio agregado) pasaron a ser significativas al sumar la
  4.ª corrida; la segunda (p=0.036 con la 5.ª) sigue siendo frágil. La 5.ª
  corrida no cambió ningún veredicto de la matriz.
- **Efecto suelo** en V3 (modelo base de 1B muy alineado); **V1 es del
  entorno** (40% en todas).
- **V5 no se re-corrió** (datos anteriores, otro hardware/código; C3 en un solo
  nivel de carga).
- **C6 pierde la atribución**: la cola intercepta los bloqueos de los demás
  mecanismos. C5/C6 son 9 repeticiones (vs. 13 de C0-C4) y con pausa de 7 s.
- **Mediciones de cliente**: los scripts no ven los bloqueos en *salida* (el
  proxy responde 200 con texto retenido), así que algunos figuran "permitido"
  (ej. un V2-D de C6); esas filas no cruzan limpio contra `eventos.jsonl`.
- **Costo propio**: 2 repeticiones × 30 mensajes legítimos por configuración
  (12 mensajes distintos: 4 cortos, 4 medianos y 4 largos); la latencia total
  tiene resolución de 1 ms, así que para los mecanismos de < 1 ms las cifras
  fiables son las de la suma por mecanismo (microsegundos); el desglose de la
  clasificación en entrada y salida solo existe desde la 5.ª corrida; **la
  mejora del p95 se midió entre dos sesiones de Colab** con los cambios
  aplicados juntos, así que su causa (fp16) es una inferencia; el modelo de
  Colab es `llama3.2:1b`, distinto del 3B de la demo local (el costo propio no
  depende del modelo, la latencia total sí).
- **Latencia contra C0**: contiene el tiempo del modelo y ~100 ms de ruido de
  generación; no es una medida de costo (ver 3 y 5.8).
- **Horas de costo** son una estimación; **falsos positivos** es evidencia
  puntual; el **LLM no es determinista**.
- Dos ambigüedades de datos abiertas (`docs/LIMPIEZA_DATOS.md`): `paso_bloqueado`
  en V4 "paso 2 omitido", y filas de 2026-09-18/19 con
  `mecanismo_que_bloqueo` discordante.
- **V7 (Excessive Agency)**: las corridas de Colab del 2026-10-05 y 2026-10-06
  (4 intentos por configuración, sin verificar notificaciones) quedaron
  **archivadas pero no integradas** al resumen de la extensión, que se hizo con otro modelo y 20
  intentos (ver `docs/LIMPIEZA_DATOS.md`, sección 8).

## 8. Qué queda pendiente

1. Re-correr V5 en GPU con el código actual y los mismos niveles de carga en
   las 7 configuraciones.
2. Confirmar que la mejora del p95 es de fp16: guardar la salida de la celda 7b
   (fp32 contra fp16, misma sesión) y, si hace falta, un A/B con
   `PROMPT_GUARD_FP16=0/1` en una misma sesión. Medir **escalabilidad** (V5
   con el clasificador actual): esta corrida no lo cubre.
3. Ejecutar filtrado + delimitación + mínimo privilegio como configuración
   propia, para convertir la recomendación en una medición.
4. Verificar la causa del efecto de delimitación sobre V4 y V2 con más
   repeticiones y un diseño que lo aísle.
5. Un modelo base menos alineado (o payloads más fuertes) para que V3 tenga
   espacio de medición.

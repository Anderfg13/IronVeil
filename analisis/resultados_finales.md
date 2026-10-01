# Resultados finales — IronVeil

> **Esta es la versión final** de la sección de resultados del informe.
> Supersede a `analisis/conclusion_borrador.md` (que queda como registro
> histórico de la primera pasada, del 2026-09-30, cuando el costo de
> implementación todavía estaba pendiente). Escrito en un lenguaje ya
> cercano al que va al LaTeX final — Sección 7 del informe.
>
> **Material de referencia, generado por script, nunca a mano:**
> - Tabla maestra completa: `analisis/tabla_maestra.{csv,md,tex}`
> - Gráficas en alta resolución (dpi≥300): `resultados/graficas_finales/`
> - Comparación celda por celda contra la hipótesis de la Sección 6.5:
>   `analisis/matriz_real_vs_hipotesis.md`
> - Costo de implementación por mecanismo: `analisis/costo_mecanismos.md`,
>   metodología en `analisis/metodologia_costo_mecanismos.md`
> - Calidad y limpieza del dataset: `docs/LIMPIEZA_DATOS.md`

## 1. Pregunta de investigación

> ¿Qué combinación de mecanismos ofrece la mejor relación protección /
> utilidad / costo?

## 2. Qué se midió

Cinco mecanismos defensivos (filtrado, delimitación, clasificación,
mínimo privilegio, aprobación humana + rate limit), activables por
separado, evaluados en 7 configuraciones (`C0` baseline hasta `C6` los 5
mecanismos activos) frente a 5 vectores de ataque originales
(reconocimiento, extracción de system prompt, prompt injection,
movimiento lateral, agotamiento de recursos) más un sexto vector
adaptativo diseñado para explotar la combinación completa. Dataset:
29 122 filas en `resultados_template.csv`, validado y limpio (ver
`docs/LIMPIEZA_DATOS.md`), acumulado entre el 2026-09-05 y el 2026-09-30.

## 3. Tabla maestra de resultados (Sección 7.3)

| Configuración | Filt. | Del. | Clas. | M.P. | A.H. | ASR promedio (%) | Falsos positivos | Latencia mediana (ms) | Costo (líneas/horas) |
|---|---|---|---|---|---|---|---|---|---|
| C0 | — | — | — | — | — | 64.3 | N/A (baseline, sin mecanismos que puedan bloquear) | 1432.0 (baseline) | 0 líneas / 0h (baseline) |
| C1 | ✓ | — | — | — | — | 49.2 | 0/1 — `test_chat_filtrado_no_bloquea_mensaje_legitimo` | 977.0 (-455.0 vs. C0) | 248 líneas / 21h |
| C2 | — | ✓ | — | — | — | 60.0 | N/A — delimitación nunca bloquea (no participa en la cadena de bloqueo) | 1650.0 (+218.0 vs. C0) | 181 líneas / 15h |
| C3 | — | — | ✓ | — | — | 28.0 | 0/1 — `test_chat_clasificacion_no_bloquea_entrada_legitima` | 12687.5 (+11255.5 vs. C0) | 309 líneas / 34h |
| C4 | — | — | — | ✓ | — | 50.0 | 0/1 (a nivel de mecanismo) — `test_validar_privilegio_no_bloquea_texto_sin_credenciales` | 504.5 (-927.5 vs. C0) | 167 líneas / 14h |
| C5 | — | — | — | — | ✓ | 23.7 | 0/1 — `test_chat_aprobacion_humana_no_bloquea_mensaje_legitimo` | 9548.5 (+8116.5 vs. C0) | 694 líneas / 69h |
| **C6** | ✓ | ✓ | ✓ | ✓ | ✓ | **8.4** | 0/1 — `test_c6_peticion_legitima_pasa_limpia_por_los_5_mecanismos` | 683.0 (-749.0 vs. C0) | 1599 líneas / 153h |

**No queda ningún campo pendiente** — las 4 columnas de métrica (ASR,
falsos positivos, latencia, costo) están completas para las 7
configuraciones. Metodología de cada columna documentada en el docstring
de `analisis/tabla_maestra.py` (no se repite aquí para que no se
desincronice de la fuente real).

## 4. Gráficas finales

Las 3 gráficas en `resultados/graficas_finales/` (dpi=300, listas para
LaTeX y diapositivas):

1. **`asr_por_configuracion.png`** — tendencia de ASR promedio C0→C6:
   baja de forma monótona con cada mecanismo adicional hasta C6, con la
   única excepción de que C2 (60.0%) y C4 (50.0%) quedan por encima de
   C1 (49.2%) tomadas individualmente — ningún mecanismo aislado domina a
   todos los demás, consistente con que cada uno ataca un vector
   distinto.
2. **`latencia_por_configuracion.png`** — latencia mediana por
   configuración, escala logarítmica (rango real: 504.5 ms – 12 687.5
   ms). **No se debe leer como costo de mecanismo aislado**: mezcla
   hardware distinto entre semanas (laptop CPU en C0-C5, GPU T4 de Colab
   en la mayoría de C6) — ver limitación en la sección 6.
3. **`matriz_cobertura_heatmap.png`** — mapa de calor lado a lado,
   hipótesis de la Sección 6.5 vs. ASR real medido, misma escala de color
   (N/A, Parcial, Sí directo, Sin datos). Detalle celda por celda y cada
   hipótesis explicativa de las discrepancias en
   `analisis/matriz_real_vs_hipotesis.md`.

## 5. Comparación contra la hipótesis de cobertura (resumen)

Análisis completo en `analisis/matriz_real_vs_hipotesis.md`. Resumen: de
las 15 celdas Vector × Mecanismo con datos comparables en ambos lados,
**13 coinciden en la dirección predicha** (8 confirmadas, 1 matizada, 4
mejor de lo esperado) y **2 van en dirección contraria** (delimitación en
V2/V3 — ya documentado que `delimitar()` nunca bloquea por diseño, así
que estructuralmente no puede mover el ASR). El hallazgo metodológico más
importante: mínimo privilegio × movimiento lateral parece solo "Parcial"
en el ASR agregado del vector, pero acierta exactamente como "Sí
(directo)" cuando se mide en el paso que de verdad le corresponde (paso
2, uso cruzado: 33.3%→0.0%) — el ASR agregado diluye el efecto real
mezclándolo con un paso (extracción) que el mecanismo nunca pretendió
bloquear.

## 6. Respuesta a la pregunta de investigación

### Protección

**C6 (los 5 mecanismos activos) ofrece la mejor protección medida**: ASR
promedio 8.4%, frente a 64.3% del baseline — una reducción de 55.9 puntos
porcentuales. Es la única configuración con defensa en profundidad real:
un ataque que evade `filtrado` puede seguir siendo detenido por
`clasificación`, y uno que evade ambos puede todavía ser detenido por
`mínimo_privilegio` en el caso de uso cruzado (confirmado empíricamente,
`docs/CONFLICTOS_RESUELTOS.md`, conflicto #4). Ningún mecanismo
individual se acerca: el segundo mejor en solitario es `aprobación_humana`
(C5, 23.7%), casi 3 veces peor que C6.

**Con un matiz que no se debe esconder**: la literatura sobre atacantes
adaptativos predice que ningún combo llega a ASR 0%, y los datos lo
confirman — el ataque adaptativo V6-C (sondeo iterativo de parafraseos)
encontró, en solo 3 intentos, una formulación que atraviesa los 5
mecanismos sin ser detectada (`ataques/vector6_adaptativo.py`,
`docs/FUENTE_DE_VERDAD.md`, entrada 2026-09-30). C6 es la configuración
más segura medida, no una configuración perfecta.

### Utilidad

No hay evidencia de que ninguna configuración, incluida C6, introduzca
falsos positivos sobre los casos puntuales verificados — la petición
legítima de prueba pasa limpia en las 7 configuraciones (columna "Falsos
positivos" de la tabla maestra, un test de `pytest` específico por
configuración). **Esto es evidencia puntual, no una tasa medida sobre una
muestra representativa de tráfico legítimo** — el dataset nunca registró
esa muestra (ver `docs/LIMPIEZA_DATOS.md`, sección 4). No se puede
afirmar con esta evidencia que C6 sea tan utilizable como C0 en producción
real, solo que no falla en el único caso legítimo que se probó por
configuración.

### Costo

**Ya disponible, cierra el vacío que dejó pendiente el borrador anterior**
(`analisis/costo_mecanismos.md`, metodología completa en
`analisis/metodologia_costo_mecanismos.md`): C6 cuesta 1599 líneas de
código y ~153 horas estimadas de desarrollo — el mecanismo más caro con
diferencia es `aprobación_humana` (694 líneas / 69h, por su estado
compartido entre peticiones concurrentes y su propia interfaz HTTP), el
más barato es `mínimo_privilegio` (167 líneas / 14h).

**Hallazgo exploratorio, no solo el costo total**: si se divide la
reducción de ASR lograda entre las horas invertidas (puntos de ASR
reducidos por hora, usando C0 como referencia), el panorama cambia:

| Configuración | Reducción de ASR (pts.) | Horas | Puntos de ASR / hora |
|---|---|---|---|
| C1 (filtrado) | 15.1 | 21 | 0.72 |
| C2 (delimitación) | 4.3 | 15 | 0.29 |
| C3 (clasificación) | 36.3 | 34 | **1.07** |
| C4 (mínimo privilegio) | 14.3 | 14 | **1.02** |
| C5 (aprobación humana) | 40.6 | 69 | 0.59 |
| C6 (los 5) | 55.9 | 153 | 0.37 |

`clasificación` y `mínimo privilegio`, en solitario, tienen la mejor
relación entre reducción de ASR y horas de desarrollo invertidas — **C6
da la mejor protección absoluta, pero con retornos marginales
decrecientes por hora de desarrollo** frente a invertir en uno o dos
mecanismos bien elegidos. **Esta tabla es exploratoria y no debe
sobre-interpretarse**: trata todos los puntos de ASR como igual de
valiosos (sin distinguir qué vector representa un riesgo mayor para el
negocio), usa horas que ya están documentadas como una *estimación*, no
una medición exacta (`analisis/metodologia_costo_mecanismos.md`, sección
4), y es costo de *implementación* (una sola vez), no costo operativo
continuo (cómputo, latencia, fricción del usuario) — ese costo operativo
solo tiene evidencia parcial hoy (columna de latencia, con la limitación
de hardware mezclado ya señalada).

### Conclusión

Si el criterio fuera solo **protección**, la respuesta es inequívoca: C6.
Si el criterio fuera **protección por hora de desarrollo invertida**,
`clasificación` sola (C3) o `mínimo privilegio` solo (C4) rinden más por
hora, aunque con un ASR absoluto bastante más alto (28.0% y 50.0%
respectivamente, frente a 8.4% de C6). **La recomendación defendible,
dado lo medido:** para un despliegue que no puede tolerar una fuga
confirmada de las credenciales del sistema, C6 es la única configuración
con defensa en profundidad real y debe usarse pese a su costo; para un
despliegue con presupuesto de desarrollo más ajustado y que pueda tolerar
un ASR residual más alto, `clasificación` sola ofrece el mejor punto de
partida medido (mejor relación ASR/hora de las 5 opciones individuales).
En ningún escenario la evidencia sostiene que `delimitación` sola sea una
buena inversión aislada: es la opción con peor relación ASR/hora **y**
la única donde la hipótesis de diseño fue refutada por el dato, no solo
matizada.

## 7. Limitaciones declaradas (consolidado)

- **n pequeño por variante** en V1-V4 (la mayoría, 1 intento por
  variante por configuración) — ningún ASR de esos vectores es una
  medición estadísticamente robusta.
- **El LLM no es determinista** entre corridas (`CLAUDE.md`, sección 9).
- **Latencia mezcla hardware** entre configuraciones (laptop CPU en
  C0-C5, GPU T4 de Colab en C6) — no aísla el costo de los mecanismos.
- **Horas de costo son una estimación**, no una medición de tiempo real
  trabajado (el equipo no llevó registro semanal).
- **Falsos positivos es evidencia puntual**, no una tasa estadística
  sobre tráfico legítimo representativo.
- **Rate-limit saturado por la propia batería de pruebas** en la corrida
  de referencia de C6 (GPU): la atribución de mecanismo para V1-V4 bajo
  C6 no es del todo confiable sin cruzar contra los eventos de la cola
  de revisión (`docs/FUENTE_DE_VERDAD.md`, 2026-09-30).
- **Dos hallazgos de datos aún abiertos**, documentados y no corregidos
  unilateralmente: `paso_bloqueado` ambiguo en V4 "paso 2 omitido", y 13
  filas de la semana del 18-19 de septiembre con `mecanismo_que_bloqueo`
  discordante entre el log del proxy y el dataset consolidado (ver
  `docs/LIMPIEZA_DATOS.md`, secciones 3.2 y 3.3).

## 8. Qué queda pendiente de verdad

1. Repetir la medición de latencia de las 7 configuraciones en el mismo
   hardware, para que esa columna deje de mezclar CPU y GPU.
2. Diseñar una muestra real de mensajes legítimos para una tasa de falsos
   positivos propiamente dicha (no solo los casos puntuales de `pytest`).
3. Confirmar con Sabogal las dos ambigüedades de datos abiertas (sección
   7 de este documento) antes de citar esas filas en el informe.
4. Resultados de la extensión opcional del 17 de octubre, si el equipo
   decide incorporarlos a esta sección.

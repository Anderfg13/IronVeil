# De dónde sale cada tabla y cada cifra (guía para escribir el paper)

> Estado al **2026-10-05**, después de ingestar la 4.ª corrida de Colab y la
> medición directa del costo por mecanismo. Si algo de abajo cambia, actualiza
> este archivo en el mismo commit.
>
> **Regla de oro:** toda cifra del informe sale de un script que lee
> `resultados/resultados_template.csv` (o, para el costo de latencia, el
> `eventos.jsonl` del proxy). Dos documentos de `analisis/` son **texto escrito
> a mano** sobre esas tablas (`resultados_finales.md` y
> `matriz_real_vs_hipotesis.md`): si regeneras las tablas, hay que releer y
> actualizar esas cifras (ver sección 6).

## 1. Cadena de datos

```
Colab / Docker                      scripts de ataque                     proxy
 (corre el stack)  ──────────►  resultados/<fecha>/vectores_1_2_3_*.jsonl      resultados/<fecha>/eventos.jsonl
                                resultados/<fecha>/vector4_*.jsonl            (log propio del proxy, 1 evento por petición,
                                resultados/<fecha>/vector5_*.jsonl             con latencia_<pieza>_us desde 2026-10-05)
                                resultados/<fecha>/vector6_*.jsonl
                                resultados/<fecha>/vector7_*.jsonl
                                         │
            analisis/agregar_resultados_desde_jsonl.py   (solo agrega filas)
                                         ▼
                      resultados/resultados_template.csv   ◄── fuente de verdad de los resultados
                      resultados/descartados.csv           ◄── filas retiradas, con la razón (nada se borra)
                                         │
   limpiar_dataset.py · fusionar_latencia_clasificador.py · validar_dataset.py
                                         ▼
   consolidar.py · tabla_maestra.py · matriz_real_vs_hipotesis.py · graficas_finales.py · comparar_*.py
                                         ▼
                      analisis/*.{csv,md,tex}  y  resultados/graficas*/*.png

   Costo de latencia (aparte, NO pasa por el CSV):
   resultados/<fecha>/eventos_colab.jsonl ──► analisis/costo_por_mecanismo.py ──► analisis/costo_por_mecanismo*.{csv,md}
```

## 2. Mapa: tabla o figura del informe → archivo → script → datos

| Qué es | Archivo(s) listos para usar | Lo genera | Lee | Sección del informe |
|---|---|---|---|---|
| **Tabla maestra** (ASR, falsos positivos, latencia, sobrecosto propio, costo de implementación) | `analisis/tabla_maestra.{md,csv,tex}` (el `.tex` compila con `booktabs`+`amssymb`) | `python analisis/tabla_maestra.py` | CSV de resultados + `analisis/costo_por_mecanismo.csv` + `analisis/costo_mecanismos.csv` | 7.3 |
| **Costo de latencia por configuración y por mecanismo** (la cifra a citar) | `analisis/costo_por_mecanismo.{md,csv}`, `costo_por_mecanismo_retenidas.{md,csv}` | `python analisis/costo_por_mecanismo.py --eventos resultados/2026-10-05/eventos_colab.jsonl --desde 2026-10-05T21:38:00+00:00` | `eventos_colab.jsonl` (Colab, 2026-10-05) | 7.3 / costo |
| Gráfica de costo propio | `resultados/graficas_finales/sobrecosto_propio_por_configuracion.png` | `python analisis/graficas_finales.py` | `analisis/costo_por_mecanismo.csv` | 7.3 / costo |
| ASR por configuración (gráfica) | `resultados/graficas_finales/asr_por_configuracion.png` (y `resultados/graficas/asr_tendencia_c0_c6.png`) | `graficas_finales.py` / `tabla_maestra.py` | CSV de resultados | 7.3 |
| Latencia contra C0 (solo contraste, **no citar como costo**) | `resultados/graficas_finales/latencia_por_configuracion.png`, `analisis/latencia_peticiones_permitidas.md` | `graficas_finales.py` / `tabla_maestra.py` | CSV de resultados | — |
| **Matriz real vs. hipótesis** (ASR k/n, valor p de Fisher, veredicto por celda) | `analisis/matriz_real_asr.md`, `matriz_real_pvalores.md`, `matriz_real_con_significancia.md`, `resultados/graficas_finales/matriz_cobertura_heatmap.png`; **narrativa:** `analisis/matriz_real_vs_hipotesis.md` | `python analisis/matriz_real_vs_hipotesis.py` (tablas) · `graficas_finales.py` (heatmap) · **a mano** (narrativa) | CSV de resultados | 6.5 / 6.6 |
| Matriz de hipótesis (lo predicho) | `analisis/matriz_hipotesis_seccion_6_5.md` | `matriz_real_vs_hipotesis.py` (la matriz va transcrita en el código, de la Sección 6.5 de la propuesta, fuera del repo) | — | 6.5 |
| **V4 por pasos** (paso 1, paso 2, ataque completo) | `analisis/v4_ataque_completo.md` | `matriz_real_vs_hipotesis.py` | CSV de resultados | 6.6 |
| ASR por configuración × vector (con n) | `analisis/tabla_resumen_asr.{md,csv}`, `tabla_resumen_asr_costo_operativo.{md,csv}` | `python analisis/consolidar.py` | CSV de resultados | 7.1 |
| V3: comparación C1/C2/C3 | `analisis/tabla_v3_c1_c2_c3.{md,csv}`, `resultados/graficas/asr_v3_c1_c2_c3.png` | `python analisis/comparar_v3_c1_c2_c3.py` | CSV de resultados | 6.x (V3) |
| V5: carga y punto de degradación | `analisis/tabla_v5_c0_c5.{md,csv}`, `tabla_v5_punto_degradacion.md` | `python analisis/comparar_v5_c0_c5.py` | CSV de resultados (V5) | 6.x (V5) |
| Costo de **implementación** (líneas y horas) | `analisis/costo_mecanismos.{md,csv}`, `analisis/metodologia_costo_mecanismos.md` | `python analisis/costo_mecanismos.py` (medición retrospectiva, no cambia con las corridas) | código del repo | 7.3 / costo |
| **Respuesta a la pregunta de investigación** | `analisis/resultados_finales.md` | **A mano**, sobre las tablas anteriores | — | 8 (discusión) |
| Extensión V7 (Excessive Agency), estudio principal | `analisis/resultados_excessive_agency.md`, `analisis/extension_agencia_excesiva.md`, `resultados/extension_agencia_excesiva_detalle.csv` | `python analisis/extension_agencia_excesiva.py ... --agregar-al-csv` | `resultados/2026-10-03/vector7_*.jsonl` (laptop, `llama3.2` 3B, 20 intentos por condición) | 6.2 / 6.6 (extensión) |
| Extensión V7, corrida de Colab (**separada, n = 4**) | `analisis/extension_agencia_excesiva_colab_2026-10-05.md` | `extension_agencia_excesiva.py` **sin** `--agregar-al-csv` (+ nota manual al inicio) | `resultados/2026-10-05/vector7_*.jsonl` | solo si se quiere citar C6 |
| Tiempo de revisión humana | `analisis/tiempo_revision_humana.{md,csv}` (hoy **n = 0**: la batería automatizada nunca espera a una persona) | `python analisis/tiempo_revision_humana.py` | todos los `*.jsonl` de `resultados/` | costo de aprobación humana |
| Validación del formato SIEM contra Wazuh | `docs/siem/wazuh/VALIDACION_FORMATO.md` | `analisis/validar_formato_siem.py` (+ `exportar_lote_siem.py`) | `eventos.jsonl` | 6.x (SIEM) |

## 3. De qué corridas está hecho el dataset (V1-V4)

Filas del núcleo de V1-V4 en `resultados/resultados_template.csv`, por fecha UTC
de la corrida (todas en Colab, GPU T4, `llama3.2:1b`). Cada repetición son 28
filas por configuración:

| Fecha (carpeta en `resultados/`) | C0 | C1 | C2 | C3 | C4 | C5 | C6 | Qué fue |
|---|---|---|---|---|---|---|---|---|
| 2026-10-02 | 28 | 26 | 28 | 28 | 28 | — | — | 1.ª re-corrida (C0-C4; las filas de C5 se descartaron después) |
| 2026-10-03 | 168 | 163 | 168 | 168 | 168 | 84 | 82 | 2.ª y 3.ª corridas (C5/C6 solo la 3.ª, con pausa de 7 s) |
| 2026-10-05 | 84 | 84 | 84 | 84 | 84 | 84 | 84 | 4.ª corrida (también con pausa de 7 s en C5/C6) |
| **Total** | 280 | 273 | 280 | 280 | 280 | 168 | 166 | **C0-C4: 10 repeticiones; C5/C6: 6** |

Otros vectores: **V5** (carga) viene de 2026-09-18 (C3, C6), 2026-09-22 (C0, C5;
CPU local y Colab) y 2026-09-30 (C6), **no se re-corrió**; **V6** (adaptativo),
8 filas de C6 del 2026-09-30; **V7** (extensión) aparte, ver arriba. Las filas
retiradas están en `resultados/descartados.csv` (409 + las que se agreguen) con
su razón.

La historia completa de cada decisión de datos (qué se descartó, por qué, y
qué cambió en las cifras) está en `docs/LIMPIEZA_DATOS.md`, secciones 6 a 8, y
en `docs/FUENTE_DE_VERDAD.md` (entradas por fecha).

## 4. Cifras de referencia (2026-10-05)

Sirven para comprobar que un script regenerado da lo mismo; la fuente es el
archivo indicado, no esta tabla.

| Cifra | Valor | Archivo |
|---|---|---|
| ASR promedio V1-V4 | C0 32.2 · C1 15.0 · C2 18.9 · C3 27.7 · C4 29.8 · C5 31.9 · C6 15.0 | `tabla_maestra.md` |
| Sobrecosto propio (mediana / p95, ms) | C0 0.18/0.63 · C1 0.43/1.17 · C2 0.23/0.77 · **C3 80.8/133** · C4 0.27/0.96 · C5 0.21/0.75 · **C6 76.0/160** | `costo_por_mecanismo.md` |
| Por mecanismo (mediana, ms) | filtrado 0.115 · delimitación 0.011 · mín. privilegio 0.025 · límite 0.018 · clasificación 79.6 (C3) / 75.4 (C6) | `costo_por_mecanismo.md` |
| Celdas significativas (p<0.05) | V2×Filtrado 0.006 · V3×Filtrado 0.003 · V4×Filtrado <0.001 · V4×Delimitación <0.001 · V4×Mín.Priv. 0.032 · V5×Aprob.Humana ≈0 | `matriz_real_pvalores.md` |
| V4 ataque completo | C0 10/30 → C4 0/30 (paso 2 bloqueado 9/9) | `v4_ataque_completo.md` |

## 5. Cómo regenerar todo (comandos, en orden)

```bash
python analisis/validar_dataset.py                      # exit 0; avisos esperados (LIMPIEZA_DATOS.md, secc. 3 y 8)
python analisis/consolidar.py
python analisis/costo_por_mecanismo.py --eventos resultados/2026-10-05/eventos_colab.jsonl --desde 2026-10-05T21:38:00+00:00
python analisis/tabla_maestra.py                        # necesita costo_por_mecanismo.csv (línea anterior)
python analisis/matriz_real_vs_hipotesis.py
python analisis/graficas_finales.py
python analisis/comparar_v3_c1_c2_c3.py
python analisis/comparar_v5_c0_c5.py                    # sin cambios mientras V5 no se re-corra
```

No volver a correr `comparar_v4_movimiento_lateral.py` ni
`tiempo_revision_humana.py` sin leer la sección 7.

## 6. Qué hay que actualizar a mano cuando cambian los datos

1. `analisis/resultados_finales.md` — todas las cifras de las secciones 2, 3, 5, 6 y 7.
2. `analisis/matriz_real_vs_hipotesis.md` — tablas de la sección 1, 2 y 3 y el «qué cambió» de la sección 0.
3. `docs/LIMPIEZA_DATOS.md` — una sección nueva por corrida ingestada.
4. `docs/FUENTE_DE_VERDAD.md` — una entrada fechada.
5. Este archivo — secciones 3 y 4.

## 7. Advertencias (trampas conocidas)

- **`resultados/2026-10-05/eventos.jsonl` es de la laptop** (pruebas de la
  demo, decisiones humanas de prueba incluidas) y **no es de Colab**. El de
  Colab está en `eventos_colab.jsonl` (mismo día, otro nombre). No mezclarlos:
  el cruce de `fusionar_latencia_clasificador.py` agrupa por fecha, así que se
  ejecutó con una carpeta temporal que contenía solo el de Colab.
- **`analisis/tiempo_revision_humana.py`** lee todos los JSONL de `resultados/`
  y, por las pruebas de la demo, sacaría n = 14 decisiones humanas que **no son
  del experimento**. El archivo publicado dice n = 0 a propósito; no
  regenerarlo sin filtrar esas decisiones.
- **`analisis/comparar_v4_movimiento_lateral.py` está obsoleto** desde el
  2026-09-13: cruza contra `verificacion_manual_fuga.csv` de la primera semana y
  falla («número de intentos distinto»). Sus tablas (`tabla_v4_movimiento_lateral`,
  `metrica_binaria_v4`) son de esa semana. Para V4 usar `v4_ataque_completo.md`.
- **La columna «Latencia mediana (ms)» de la tabla maestra** es la diferencia
  contra C0 y **hereda el ruido del modelo** (C1 y C2 salen más rápidas que el
  baseline). Para el costo de latencia citar **«Sobrecosto propio (ms)»**.
- **El `.tex` de la tabla maestra** se genera completo (13 columnas, ancho):
  puede necesitar `\resizebox` o `landscape` en el informe.
- **`analisis/conclusion_borrador.md`** y los `analisis_*.md` semanales son
  históricos (superseded); no son fuente para el informe.
- **`config.yaml` del repo debe quedar en C0**: hay una prueba que lo exige.
- **Numeración de secciones del informe**: el LaTeX no está en el repo
  (`/informe/` aún no existe); las secciones de la columna «Sección del
  informe» son las que citan los documentos del equipo y pueden haber cambiado.

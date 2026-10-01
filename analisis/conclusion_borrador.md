# Conclusión general del proyecto — BORRADOR

> **⚠️ Este es un PRIMER BORRADOR, no la versión final.** Falta agregar el
> costo de implementación completo por configuración (columna "Costo" de la
> tabla maestra, tarea de la semana del 2026-10-10) y, con eso, revisar si la
> respuesta a la pregunta de investigación cambia. No citar este documento en
> el informe final sin esa actualización. Generado a partir de
> `resultados/resultados_template.csv` (29 136 filas al 2026-09-30) vía
> `analisis/tabla_maestra.py` y de los hallazgos ya redactados en
> `docs/FUENTE_DE_VERDAD.md`, sección 6.

## Pregunta de investigación

> ¿Qué combinación de mecanismos ofrece la mejor relación protección /
> utilidad / costo?

## 1. Lo que dice la tabla maestra

(Generada con `python analisis/tabla_maestra.py`; ver `analisis/tabla_maestra.{csv,md,tex}` y la gráfica `resultados/graficas/asr_tendencia_c0_c6.png`.)

| Configuración | Filt. | Del. | Clas. | M.P. | A.H. | ASR promedio (%) | Falsos positivos | Latencia mediana (ms) |
|---|---|---|---|---|---|---|---|---|
| C0 | — | — | — | — | — | 64.4 | N/A (baseline) | 1432.0 (baseline) |
| C1 | ✓ | — | — | — | — | 49.2 | 0/1 verificado | 977.0 (-455.0 vs. C0) |
| C2 | — | ✓ | — | — | — | 60.0 | N/A (no bloquea) | 1650.0 (+218.0 vs. C0) |
| C3 | — | — | ✓ | — | — | 28.0 | 0/1 verificado | 12687.5 (+11255.5 vs. C0) |
| C4 | — | — | — | ✓ | — | 50.0 | 0/1 a nivel de mecanismo | 504.5 (-927.5 vs. C0) |
| C5 | — | — | — | — | ✓ | 23.7 | 0/1 verificado | 9548.5 (+8116.5 vs. C0) |
| C6 | ✓ | ✓ | ✓ | ✓ | ✓ | **8.4** | 0/1 verificado | 683.0 (-749.0 vs. C0) |

**ASR promedio** es la media **sin ponderar** entre vectores de cada
configuración (cada vector pesa igual; V5, con miles de intentos, no ahoga a
V1-V4 en el promedio — ver metodología en `analisis/tabla_maestra.py`).

La tendencia general **confirma la hipótesis central del proyecto**: el ASR
baja de C0 (64.4%) a C6 (8.4%), con C6 como la configuración de menor ASR
promedio de las 7. No es una caída monótona perfecta (C2 sube ligeramente
sobre C0, C4 queda por encima de C1 y C5) — ver sección 2 para por qué, vector
por vector.

**Importante sobre "Latencia mediana":** esta columna **mezcla hardware
distinto entre configuraciones** — C0-C5 se corrieron en el laptop del equipo
(CPU, semanas 1-4) y la mayoría de las filas de C6 provienen de la corrida de
referencia del 2026-09-30 en Google Colab con GPU T4. Por eso C6 aparece con
latencia *menor* que C0 pese a correr los 5 mecanismos — es un artefacto de
hardware, no evidencia de que los mecanismos sean gratis. No usar esta columna
para argumentar "costo de latencia por mecanismo" sin repetir todas las
configuraciones en el mismo hardware (pendiente, no hecho).

**Importante sobre "Falsos positivos":** el proyecto nunca registró una
muestra estadística de mensajes legítimos en `resultados_template.csv` (cada
fila ahí es un intento de ataque). Lo que existe es una verificación puntual
por configuración en `pytest` (un caso de petición legítima que no cae, uno
distinto por configuración o combinación — ver `analisis/tabla_maestra.py`
para el test exacto de cada fila). Es evidencia real, pero **no es una tasa de
falsos positivos** en el sentido estadístico.

## 2. ¿Qué se confirmó, qué se refutó o matizó? (vs. Sección 6.5/6.6 del documento de propuesta)

| Vector × Mecanismo | Predicho (Sección 6.5/7.2) | Observado | Veredicto |
|---|---|---|---|
| V3 (prompt injection) × Delimitación | "Sí", efecto directo; ASR "reducida" | Sin ningún cambio (100.0% → 100.0% en la corrida de referencia de C0/C2) | **Refutado**, por diseño: `delimitar()` nunca bloquea, solo reestructura — no puede mover un ASR que solo distingue bloqueado/no bloqueado, sin importar cuánto cambie el comportamiento real del modelo. |
| V3 (prompt injection) × Filtrado | "Sí", efecto directo; ASR "reducida" | 100.0% → 87.5% en la corrida inicial — dirección correcta, magnitud muy por debajo de lo predicho, por un bug real del regex ("todas **tus** instrucciones" no cubría "todas **las** instrucciones") | **Matizado**: confirma la dirección, no la magnitud. El bug ya se corrigió (`tests/test_vector6_adaptativo.py` lo verifica indirectamente vía V6-C), pero no se repitió la corrida original para remedir el efecto corregido. |
| V3 (prompt injection) × Clasificación | "Sí", efecto directo; cobertura complementaria a filtrado | Primer mecanismo que mueve el ASR de forma apreciable (100.0% → 75.0% con Llama Guard; → 0.0% tras cambiar a Prompt Guard especializado en inyección) | **Confirmado** en dirección y, tras el cambio de clasificador, también en magnitud — con la salvedad de n pequeño por variante y no-determinismo de LLM ya declarado. |
| V4 (movimiento lateral) × Mínimo privilegio | "Sí", efecto directo sobre el uso cruzado (no sobre la extracción) | Movimiento lateral completo: 33.3% en C0 → 0.0% en C4. Paso 1 (extracción) nunca bloqueado por este mecanismo en ninguna corrida (como se espera, por diseño) | **Confirmado**, con salvedad de tamaño de muestra (n=9 por configuración). |
| V5 (agotamiento) × Aprobación humana | "Sí"/"parcial"; mitiga saturación de recursos | En CPU: protege solo por encima de ~10 peticiones/60s reales, no en concurrencia baja (2-8) donde el volumen nunca cruza el umbral. En GPU: protege desde niveles mucho más bajos porque el volumen sí crece rápido dentro de la ventana. | **Confirmado con matices fuertes**: el mecanismo funciona exactamente como está diseñado (límite de tasa, no de concurrencia instantánea), pero su efectividad medida depende completamente del hardware y del patrón de tráfico, no es una propiedad fija del mecanismo. |
| V1-V4 × Aprobación humana (sola, C5) | Mecanismo diseñado para V5 principalmente; sin predicción fuerte para V1-V4 aislado | 0/28 intentos interceptados — resultado estructural: sin otro mecanismo activo que bloquee primero, ni rate limit disparado (tráfico secuencial), no hay nada que `aprobación_humana` pueda interceptar | **Consistente con el diseño**, no una falla: el valor de este mecanismo frente a V1-V4 solo es medible en combinación (C6), nunca en solitario. |
| Los 5 mecanismos juntos (C6) | ASR "muy reducido" pero la literatura sobre atacantes adaptativos anticipa que **no llega a 0%** | ASR promedio 8.4%, el más bajo de las 7 configuraciones. **Pero:** la corrida de referencia de hoy encontró que, bajo tráfico rápido (GPU), gran parte de los bloqueos en V1-V4 se deben a que el límite de tasa ya estaba saturado por la propia batería de pruebas, no a que `filtrado`/`clasificación`/`mínimo_privilegio` detectaran el contenido — y el ataque adaptativo V6-C sí encontró, en 3 intentos, un parafraseo que atraviesa los 5 mecanismos sin ser bloqueado (aunque el modelo se negó a cooperar por su cuenta). | **Confirmado en la dirección principal** (C6 es la configuración más segura medida) **y confirmada también la predicción de la literatura** de que ningún combo llega a ASR 0% contra un atacante adaptativo — ver `ataques/vector6_adaptativo.py` y el hallazgo del 2026-09-30 en `docs/FUENTE_DE_VERDAD.md`. |

## 3. Respuesta a la pregunta de investigación (preliminar)

Con los datos medidos hasta el 2026-09-30:

**C6 (los 5 mecanismos activos) ofrece la mejor protección medida** — el ASR
promedio más bajo (8.4%, frente a 64.4% del baseline) y es la única
configuración que combina defensa en profundidad real: un ataque que evade
`filtrado` puede seguir siendo detenido por `clasificación`, y uno que evade
ambos puede todavía ser detenido por `mínimo_privilegio` en el caso de uso
cruzado — como se confirmó empíricamente en la semana de integración (ver
`docs/CONFLICTOS_RESUELTOS.md`, conflicto #4) y en la corrida de referencia
del 2026-09-30.

Sobre **utilidad** (falsos positivos): no hay evidencia de que C6 introduzca
falsos positivos sobre los casos puntuales verificados — la petición legítima
de prueba pasó limpia en las 7 configuraciones, incluida C6. Pero, de nuevo,
esto es evidencia puntual (un caso por configuración), no una tasa medida
sobre una muestra representativa de tráfico legítimo.

Sobre **costo**: **no se puede responder todavía.** Faltan dos piezas: (a) el
costo de implementación por mecanismo (líneas de código, horas, tarea de la
semana del 2026-10-10), y (b) una medición de latencia limpia, en el mismo
hardware para las 7 configuraciones — lo que existe hoy mezcla laptop CPU
(C0-C5) con GPU T4 de Colab (C6), así que no se puede afirmar con los datos
actuales que C6 sea más lento o más barato que las demás configuraciones.

**Conclusión preliminar:** si el criterio fuera solo protección, **C6 es la
respuesta clara**. La relación protección/utilidad/costo completa —que es
la pregunta real del proyecto— **queda pendiente de la columna de costo**,
y este documento se actualizará ese día.

## 4. Pendientes explícitos antes de la versión final

1. Costo de implementación por mecanismo/configuración (líneas de código,
   horas) — semana del 2026-10-10.
2. Repetir la medición de latencia de las 7 configuraciones en el mismo
   hardware, para que la columna "Latencia mediana" de la tabla maestra deje
   de mezclar CPU del equipo con GPU de Colab.
3. Decidir si se repite la corrida de V1-V4 contra C6 con un ritmo de
   peticiones más lento (para que el rate limit no sature la atribución de
   mecanismo, hallazgo del 2026-09-30) o si se documenta como limitación
   permanente de la corrida de referencia.
4. Diseñar una muestra real de mensajes legítimos (no solo los casos puntuales
   de `pytest`) si el equipo quiere una tasa de falsos positivos propiamente
   dicha, no solo evidencia puntual.

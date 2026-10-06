# Gráficas reemplazadas (no son fuente para el informe)

Aquí se mueven las gráficas cuando una corrida nueva las reemplaza. **No se borran** (mismo
criterio que `descartados.csv` para las filas del dataset, regla 4 de `CLAUDE.md`), pero
**no son fuente para el informe**: las vigentes están en `resultados/graficas/` y
`resultados/graficas_finales/` (mapa completo en `docs/DE_DONDE_SALE_CADA_TABLA.md`).

Cada subcarpeta lleva la fecha de la **corrida cuyos datos reflejan**, no la de cuando se
movieron.

| Carpeta | Datos que reflejan | Reemplazadas por |
|---|---|---|
| `2026-10-05/` | Hasta la 4.ª corrida de Colab (2026-10-05) y la primera medición del costo por mecanismo (antes de los recortes de latencia del clasificador) | La 5.ª corrida de Colab (2026-10-06): 6 figuras con los mismos nombres |

Las seis figuras de `2026-10-05/` son: `asr_tendencia_c0_c6.png`, `asr_v3_c1_c2_c3.png`,
`asr_por_configuracion.png`, `latencia_por_configuracion.png`, `matriz_cobertura_heatmap.png`
y `sobrecosto_propio_por_configuracion.png`.

Para reproducir una de estas versiones hay que volver al commit anterior a la 5.ª corrida
(`git log -- resultados/2026-10-06`), porque los datos y las tablas de entrada cambiaron.

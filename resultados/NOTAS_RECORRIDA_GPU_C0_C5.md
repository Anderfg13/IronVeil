# Re-corrida de C0-C6 en Colab GPU

> **La guía ejecutable es el notebook `RECORRIDA_GPU_C0_C6.ipynb`** (misma
> carpeta): se sube tal cual a Google Colab y se corre celda por celda. Este
> archivo solo documenta el *por qué* y las decisiones; antes traía los
> comandos a mano, pero tenían errores (ver "Correcciones" abajo) y se
> reemplazó por el notebook para tener una sola fuente.

## Objetivo y decisiones

- Que C0-C5 queden medidas en el MISMO hardware que C6 (GPU T4 de Colab),
  para que la columna "Latencia mediana" de `analisis/tabla_maestra.py`
  deje de mezclar laptop CPU con GPU.
- Decisión ya tomada con el usuario: las filas viejas de C0-C5 (CPU) se
  descartan (mueven a `descartados.csv` con razón documentada) y se
  reemplazan por las nuevas de GPU — no se quedan ambas mezcladas.
- Alcance: V1-V4 (lo que entra en la métrica de latencia; V5 ya está
  excluido de esa métrica por diseño, ver `latencia_extra_por_config()`).
  Para V5 en GPU, correr aparte `ataques/vector5_carga.py`.

## Estado

- **1.ª corrida (2026-10-02, C0-C5, 1 repetición): ingestada.** Ver
  `docs/LIMPIEZA_DATOS.md`, sección 6.
- **2.ª corrida (2026-10-03, C0-C6 × 3 repeticiones): ingestada.** Ver
  `docs/LIMPIEZA_DATOS.md`, sección 6.1. **3.ª corrida pendiente** con
  `RECORRIDA_GPU_C0_C6.ipynb` actualizado: Prompt Guard en GPU (`device=0`) y
  pausa de 7 s entre peticiones en C5/C6 para no saturar el límite de tasa
  (cambios del 2026-10-03, posteriores a los datos ya ingestados). Pendiente
  aparte: V5 en GPU con el código actual.

## Después de correr el notebook (lo hace Claude)

1. Mover las filas viejas de C0-C5 (CPU) a `resultados/descartados.csv`
   (`analisis/mover_a_descartados.py`).
2. Ingestar los JSONL nuevos con `analisis/agregar_resultados_desde_jsonl.py`
   y fusionar `latencia_clasificador_ms` con
   `analisis/fusionar_latencia_clasificador.py` (el `eventos.jsonl` del
   proxy va dentro del zip justamente para eso).
3. Regenerar `tabla_maestra.py`, `matriz_real_vs_hipotesis.py`,
   `graficas_finales.py` y `resultados_finales.md`.
4. Dejar `config.yaml` del repo local en C0.

## Correcciones respecto a la primera versión de esta guía

La versión en markdown de los comandos, escrita antes del notebook, omitía
variables que el stack exige fuera de Docker:

- `OLLAMA_HOST` (la exige `ollama/init.sh`, falla con `set -e` sin ella) y
  `OLLAMA_BASE_URL=http://localhost:11434` (el proxy usa por defecto
  `http://ollama:11434`, que solo resuelve dentro de Docker).
- `uvicorn` debe arrancar con `--no-server-header` (el Dockerfile lo usa;
  V1-B/V1-E miden justamente ese encabezado).
- `--permitir-host-remoto` sobraba: con `localhost` no hace falta y
  debilita la validación de laboratorio aislado (regla 1 de `CLAUDE.md`).
- El proxy se arranca con la bandera de C3 (`clasificacion: true`) para que
  el calentamiento cargue Prompt Guard/Llama Guard antes de medir; con C0
  al arrancar, la primera petición de C3 pagaría la carga en frío y
  aparecería como un outlier de latencia falso.

## Salvedades que deben quedar en el informe

- **C5 (aprobación humana) en GPU:** el límite de tasa es fijo (10/min por
  cliente, 50/min global) y la GPU dispara peticiones mucho más rápido que
  la CPU, así que el tráfico de la propia batería puede saturarlo — mismo
  efecto ya documentado para C6 el 2026-09-30. Leer los datos de C5 con esa
  salvedad.
- **Prompt Guard corre en CPU aunque haya GPU:** `_crear_pipeline(...)` en
  `proxy/mecanismos.py` no especifica `device`, así que `transformers` usa
  CPU por defecto. La GPU acelera los modelos de Ollama (chat y Llama
  Guard), no la clasificación de entrada.

## Nota de seguridad

Los secretos (`HF_TOKEN`, `SPT_SECRET`, `RRHH_SECRET`) los escribe el
usuario con `getpass()` en su propia sesión de Colab. Nunca se pegan en una
celda como texto plano ni se comparten en el chat — ese es el límite que se
ha respetado en todas las corridas anteriores.

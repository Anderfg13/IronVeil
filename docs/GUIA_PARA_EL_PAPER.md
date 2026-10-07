# Guía para escribir el paper (léela primero)

> **Para quien redacta el paper, y para su asistente de IA:** este archivo dice **dónde está cada número**,
> **cuál es el definitivo**, **qué comandos regeneran las tablas** y **qué NO se puede afirmar**. Si le
> pides a Claude que busque información para las tablas, dile: «lee `docs/GUIA_PARA_EL_PAPER.md`».
> Actualizada el 2026-10-07.

## Reglas para no equivocarse

1. **No inventes ni redondees a tu favor un número.** Cada cifra sale de un archivo de `analisis/` o `resultados/`.
   Si no está ahí, no existe: se mide, no se estima.
2. **Cita siempre el intervalo de confianza, no solo el porcentaje.** Las muestras son pequeñas (13 ataques, 24 textos
   por idioma, 30 por probe). «100 %» con 13 ataques es «entre 77 % y 100 %».
3. **Nada de «protección total» ni «0 % de ASR» a secas.** La literatura espera que C6 no llegue a 0 %; si un resultado
   es modesto, se reporta modesto (regla 5 de `CLAUDE.md`).
4. **Los datos crudos no se editan** (`resultados/**/eventos.jsonl`, `resultados/resultados_template.csv`). Las tablas
   se regeneran con scripts.
5. **Separa el núcleo de las extensiones.** El núcleo son las 7 configuraciones C0–C6 y los 5 vectores medidos. Garak,
   Jev, normalización, SIEM, memoria de decisiones y modelo remoto son **extensiones**: otra tabla, otra sección.
6. **La fuente de verdad de cada decisión y cada resultado fechado es `docs/FUENTE_DE_VERDAD.md`** (una fila por
   cambio, con límites y qué *no* está verificado). Léela antes de redactar «Limitaciones».

## Dónde está cada número

### Núcleo (C0–C6, vectores V1–V5)

| Qué necesitas | Archivo |
|---|---|
| Resultados finales y su lectura (versión vigente) | `analisis/resultados_finales.md` |
| Tabla maestra de ASR por configuración y vector | `analisis/tabla_maestra.md` (`.csv`, `.tex` listo para LaTeX) |
| Resumen de ASR y costo operativo | `analisis/tabla_resumen_asr.md`, `analisis/tabla_resumen_asr_costo_operativo.md` |
| Hipótesis contra lo medido, con valores p | `analisis/matriz_real_con_significancia.md`, `analisis/matriz_real_vs_hipotesis.md` |
| Costo (latencia) de cada mecanismo | `analisis/costo_por_mecanismo.md` (`.csv`), método en `analisis/metodologia_costo_mecanismos.md` |
| Gráficas | `resultados/graficas/` |
| Conclusión (borrador) | `analisis/conclusion_borrador.md` |
| Por qué se descartaron filas | `resultados/descartados.csv`, `docs/LIMPIEZA_DATOS.md` |
| Decisiones de integración | `docs/CONFLICTOS_RESUELTOS.md` |

### Extensiones (no entran en las tablas del núcleo)

| Qué necesitas | Archivo |
|---|---|
| Agencia excesiva (V7, herramientas **simuladas**) | `analisis/extension_agencia_excesiva.md` |
| Garak, corrida con Prompt Guard (**ojo:** C3 y C6sinH no son concluyentes, la salida fallaba) | `analisis/garak_resumen.md` |
| Garak, corrida con **Jev** (válida) | `analisis/garak_jev/garak_resumen.md` y `.csv` |
| Jev suelto: 29 textos en español | `analisis/jev_efectividad.md` |
| Jev suelto: 24 textos en 8 idiomas | `analisis/jev_efectividad_idiomas.md` |
| Datos crudos de Jev (sin texto ni clave) | `resultados/jev/*.jsonl` |
| Ataques escondidos (Base64, hex, ROT13, invisibles) | `analisis/normalizacion_deteccion.md` |
| Cómo se interpreta cada extensión | `docs/GARAK.md`, `docs/CAMBIAR_MODELO_CLASIFICADOR.md`, `docs/NORMALIZACION_DE_ENTRADA.md`, `docs/SIEM.md`, `docs/MEMORIA_DE_DECISIONES.md`, `docs/MODELO_PROTEGIDO_REMOTO.md` |

## Cifras de Jev que ya están medidas (con sus límites)

| Medición | Resultado | Límite que hay que citar |
|---|---|---|
| Español, 29 textos | 13/13 ataques detectados (IC95 % 77–100 %); 0/16 legítimas bloqueadas (IC95 % 0–19 %); p50 92 ms, p95 128 ms | Las 16 legítimas son ~10 textos distintos; los ataques son del propio experimento |
| 8 idiomas, 24 textos | 16/16 (IC95 % 81–100 %); 0/8 legítimas (IC95 % 0–32 %); p50 141 ms, p95 230 ms | Traducciones de un asistente de IA, sin revisión de nativos; 2 ataques y 1 legítima por idioma |
| Garak, C3 (339 ataques) | Frenados en la entrada 291/339 (86 %); ASR 0,3 % (IC 0,1–1,7 %); C0 sin defensas: 51,2 % | Una sola corrida; el modelo de 1B no obedece la mayoría de los ataques |
| Garak, C6sinH (339) | Frenados 288/339 (85 %); ASR 0,0 % (IC 0,0–1,1 %) | Ídem; C6sinH **no** es la C6 oficial (sin aprobación humana) |
| Latencia de Jev con Garak | p50 221 ms, p95 283 ms | Prompts más largos y otra hora que la medición suelta: no es una sola cifra |

**Qué NO afirmar sobre Jev:**
- *«Jev es mejor que Prompt Guard».* La corrida de Garak con Prompt Guard tenía la clasificación de salida fallando
  (Ollama sin GPU), así que no es una comparación limpia. La comparación defendible es la de los textos sueltos.
- *«Protege en más de 100 idiomas».* Ver la sección siguiente: no hay fuente que lo diga de Jev.
- *«Protege contra ataques nuevos o adaptativos».* Los ataques medidos son los del propio experimento y un catálogo
  público; no se probaron ataques adaptativos contra Jev.

## Cuántos idiomas soporta Jev (investigado el 2026-10-07)

**No hay una cifra oficial.** Lo encontrado:

- La documentación de la API de TypeSafe (`docs.typesafe.ai`) **no dice nada** sobre idiomas.
- Una ficha de terceros (innfactory.ai, que dice citar a TypeSafe) afirma que el **inglés es el idioma principal** y que
  «otros idiomas, incluido el CJK, están soportados con precisión variable». Para el alemán «no hay cifras del
  fabricante: haz tu propia evaluación».
- **La cifra de «más de 100 idiomas» no se pudo atribuir a Jev.** En la búsqueda apareció asociada a **Laya**, un modelo
  *distinto* y de código abierto (Convai Innovations); y ni siquiera la página de terceros que lo describe repite esa
  cifra, así que tampoco es seguro para Laya. Si alguien recuerda «100 idiomas», probablemente sea una confusión.
- Datos de la misma ficha de terceros (no de TypeSafe directamente): ventana de 64 000 tokens por petición, latencia
  de 70 a 500 ms según el fabricante (**coincide** con lo medido aquí: p50 92–221 ms) y precio de 0,042 USD por millón
  de tokens de entrada.
- Lo que **sí** está medido aquí: 8 idiomas (en, fr, pt, de, it, ru, zh, ar) con 16/16 ataques detectados y 0/8
  legítimas bloqueadas. Eso es evidencia propia de que funciona en esos 8, no una cifra de cobertura total.

**Cómo escribirlo en el paper:** «El fabricante indica el inglés como idioma principal y no publica una cifra de idiomas;
nosotros lo evaluamos en 8 idiomas con una muestra pequeña (24 textos)». Fuentes: <https://docs.typesafe.ai/>,
<https://innfactory.ai/en/ai-models/typesafe-jev/>, <https://www.deeplearning.ai/the-batch/models-built-to-do-one-thing-well>.
La consulta se hizo el 2026-10-07; las páginas de terceros pueden haber cambiado.

## Cómo regenerar tablas y números

```bash
python analisis/consolidar.py                              # tablas de ASR del núcleo
python analisis/tabla_maestra.py                           # tabla maestra (.md, .csv, .tex)
python analisis/costo_por_mecanismo.py                     # costo de cada mecanismo
python analisis/resumen_garak.py --entrada resultados/garak/<carpeta> --salida analisis/<carpeta_nueva>
python ataques/medir_clasificador_entrada.py --resumir-desde resultados/jev/<archivo>.jsonl   # gratis, sin llamar a Jev
python analisis/medir_normalizacion.py                     # ataques escondidos (determinista)
pytest                                                     # 1690 pruebas; deben pasar antes de citar nada
```

Los datos crudos de Garak (`resultados/garak/`) **no están en el repositorio** (traen prompts de ataque y canarios
filtrados); si se necesitan, están en los zips de Colab del equipo. Los resúmenes sí están versionados.

## Qué decir en «Limitaciones» (resumen)

- Muestras pequeñas: se reportan intervalos, y dos intervalos que se solapan no son distinguibles.
- El LLM no es determinista: los resultados no se reproducen bit a bit.
- Laboratorio aislado, modelos pequeños (`llama3.2:1b`): un modelo más capaz obedecería más ataques, así que el ASR sin
  defensas (C0) sería más alto.
- Los ataques son del propio experimento y de un catálogo público; no hay ataques adaptativos contra las defensas
  nuevas.
- Las extensiones están medidas, pero fuera de las 7 configuraciones; ninguna se probó en producción real.
- Jev es un servicio de tercero y de pago: el texto de cada petición sale del laboratorio.
- Detalle de lo **no verificado** de cada pieza: columnas de `docs/FUENTE_DE_VERDAD.md`.

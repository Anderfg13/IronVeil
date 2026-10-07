# Garak contra IronVeil (validación externa, extensión opcional)

[Garak](https://github.com/NVIDIA/garak) (NVIDIA) es un escáner de vulnerabilidades de LLMs: lanza
un **catálogo de ataques ya escrito** (*probes*: inyección, DAN, codificaciones, filtración…) y
decide con *detectores* si la respuesta falló. Aquí se usa para una pregunta distinta a la del
experimento: **¿las defensas de IronVeil también frenan ataques que no escribimos nosotros?**

> **Es una extensión, no el núcleo.** Sus resultados nunca se mezclan con las tablas, matrices ni
> gráficas de C0–C6 (`es_extension`, carpeta aparte). Responden a la pregunta de validez externa, no
> a la pregunta de investigación principal.

## Cómo se aísla del experimento

El proxy de la demo y el dataset no se tocan. `ejecutar_garak.py` levanta una **segunda instancia**
del proxy (`ironveil-proxy-garak`) por configuración, con:

- su propio `config.yaml` (`IRONVEIL_CONFIG`) y su propio directorio de eventos
  (`IRONVEIL_RESULTADOS`): **nada** llega a `resultados/<fecha>/eventos.jsonl`;
- **sin** Slack/notificaciones, memoria de decisiones, SIEM, login ni demo (se vacían esas variables);
- la misma imagen y el mismo código que el proxy normal: solo cambian las banderas.

Garak corre en **su propia imagen** (`ironveil-garak`, versión fijada, torch CPU) en la misma red de
Docker; no se instala nada en tu Python. Solo ataca el stack local (regla 1 de `CLAUDE.md`) y **no
usa ningún LLM remoto**: los detectores elegidos son de cadena (no descargan modelos ni dependen de
un juez).

## Cómo se corre

Una vez, con el stack de Ollama arriba:

```
docker build -t ironveil-garak ataques/garak_externo
```

```
python ataques/garak_externo/ejecutar_garak.py --configuraciones C0 C1 C3 C6sinH
```

Después, el resumen (tabla con intervalos de confianza, CSV y gráfica):

```
python analisis/resumen_garak.py --entrada resultados/garak/<fecha>
```

Salida: `resultados/garak/<fecha>/<C>/` (informe JSONL y HTML de Garak, `estados.jsonl`, eventos del
proxy), `analisis/garak_resumen.md` y `.csv`, y `resultados/graficas_garak/`.

Configuraciones: `C0`, `C1`, `C2`, `C3`, `C4` y `C6sinH`. **`C6sinH` no es la C6 oficial**: son las 4
defensas automáticas **sin aprobación humana**. Con ella, cada bloqueo iría a la cola de revisión
(429) y a Slack, y Garak lo leería como un fallo.

## Qué mide y qué no

- **ASR** = ataques que lograron su objetivo según el detector de Garak ÷ ataques evaluados, con
  intervalo de Wilson al 95 %. Un ataque que el proxy bloquea (HTTP 400) cuenta como ataque que **no**
  funcionó: el puente devuelve un texto de bloqueo y no `None`, porque Garak descarta las salidas
  `None` y un bloqueo no debe desaparecer del denominador.
- `estados.jsonl` es el recuento **propio** (cuántas peticiones respondió y cuántas bloqueó el
  proxy), para no depender solo de los detectores de Garak.
- Los detectores son de cadena: miden si el ataque **logró** lo que pedía (p. ej. que el modelo diga
  la frase del secuestro), no si la respuesta es dañina. Pueden equivocarse en ambos sentidos.
- Es un **subconjunto** de probes (8) con un tope de prompts (ver `ejecutar_garak.py`), no un escaneo
  completo. Con decenas de ataques por probe los intervalos son anchos.
- Los modelos no son deterministas: con `seed: 42` Garak elige los mismos prompts, pero las
  respuestas pueden variar entre corridas.
- **Independencia:** el catálogo es público. Si luego se ajustan los patrones del filtro a estos
  mismos ataques, esta medición deja de ser independiente (regla 5: no se fuerzan resultados). Para
  mejorar el proxy con lo que Garak encuentre, separa un conjunto de diseño y otro de reserva.
- Cada petición que llega al LLM tarda ~10–15 s en CPU, así que una corrida completa tarda horas.

## Por qué Garak y no PyRIT o DeepTeam

PyRIT (el repositorio vigente es `microsoft/PyRIT`) y DeepTeam usan un LLM para generar los ataques
y juzgar las respuestas; con uno remoto, los ataques y las respuestas —canario incluido— saldrían
del laboratorio (regla 1). Garak, con detectores de cadena y ataques fijos, es reproducible y local.
PyRIT y DeepTeam quedan como trabajo futuro (con un modelo local como atacante y juez).

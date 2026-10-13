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

## Resultados de la primera corrida (2026-10-06, Colab T4)

Datos crudos en `resultados/garak/2026-10-06-colab/` (**no versionados**: llevan respuestas del
modelo con credenciales filtradas; el zip original queda como evidencia). Resumen reproducible:
`analisis/garak_resumen.md`, `.csv` y `resultados/graficas_garak/`. 6 configuraciones, 8 probes,
≈ 339 ataques por configuración, modelo `soporte` (`llama3.2:1b`).

| | C0 | C1 | C2 | C3 | C4 | `C6sinH` |
|---|---:|---:|---:|---:|---:|---:|
| ASR (según Garak) | 51,2 % | 49,0 % | 50,9 % | 0,0 % ⚠ | 49,6 % | 0,0 % ⚠ |

**⚠ El 0 % de C3 y `C6sinH` NO es concluyente.** De sus 339 bloqueos, 221 fueron detecciones reales
de Prompt Guard (`estado: ok`), pero **118 fueron timeouts de Llama Guard** (la clasificación de la
respuesta): el servicio no contestó, el proxy bloqueó por defecto (fail closed) y esas peticiones
parecen «ataques frenados» sin que nadie las evaluara. En la corrida anterior de C0–C6 en Colab,
Llama Guard respondió bien en 203 de 203 evaluaciones: aquí falló en el 100 %, cada vez a los 10 s
exactos (`TIMEOUT_CLASIFICADOR_S`). Causa **no determinada** (los logs del proxy y de Ollama no
viajan en el zip). Hay que repetir C3 y `C6sinH`; el notebook ya trae un chequeo previo (celda 10b)
que detiene la corrida si un clasificador no responde.

Lo que sí se sostiene:

- **C0 a C4 son comparables entre sí**, y el modelo de 1B es muy vulnerable: 99 % de éxito de la
  familia DAN. C0, C1, C2 y C4 caen entre 49 % y 51 %; esa dispersión es el **ruido** de la medición.
- **C4 (mínimo privilegio) actúa como control negativo**: no debería afectar a estos ataques y no lo
  hizo.
- **C1 (filtrado) casi no frena estos ataques** (15 de 339 bloqueados): sus patrones son de los
  ataques del proyecto, no de un catálogo externo. Pero **su filtro de salida sí funcionó**: 13
  respuestas de C0 contenían una credencial del laboratorio (3,8 %) y en C1 cero, con 15 redactadas
  (p = 0,0002). Garak no mide esto; es un conteo propio.
- **C2 (delimitación)**: sin efecto global, y una diferencia suelta en `latentinjection` (16/30 → 7/30,
  p = 0,033) que, entre 15 comparaciones, es una **pista y no un hallazgo**. Tiene sentido con el
  mecanismo (esos ataques van escondidos en un documento), pero sube en `promptinject`.
- **Los ataques codificados (Base64, ROT13, Tag) quedan sin cubrir por el filtro y por Prompt Guard**: es una debilidad latente, y la extensión opcional `docs/NORMALIZACION_DE_ENTRADA.md` la cubre.
- **3 de los 8 probes no discriminan** (`InjectBase64`, `InjectROT13`, `goodside.Tag`): dan 0 % hasta
  en C0 porque el modelo de 1B no obedece instrucciones codificadas.
- **Garak solo trae ataques**: no mide falsos positivos. Que C3 bloquee casi todo no dice nada sobre
  la utilidad; eso lo miden los mensajes legítimos del experimento.

## Variante con Jev como clasificador de entrada (de pago)

`resultados/GARAK_JEV_COLAB_T4.ipynb` repite la validación externa con **Jev** (TypeSafe) en lugar de
Llama Prompt Guard como clasificador de la **entrada**: Jev decide si cada mensaje es una inyección antes de
que llegue al modelo de Ollama. La salida sigue clasificándola Llama Guard. Se genera con
`python ataques/garak_externo/generar_notebook.py` (que produce las dos variantes) y se vigila con
`tests/test_notebook_garak_jev.py`.

- **Qué corre:** solo **C3** y **C6sinH**, las únicas que usan el clasificador. C0, C1, C2 y C4 no lo
  llaman: sus resultados con Prompt Guard siguen valiendo y no se repiten ni se pagan.
- **Qué se compara, sin decidirlo de antemano:** ASR de C3 y C6sinH con Jev frente a Prompt Guard (mismos
  probes, misma semilla), peticiones frenadas de verdad frente a «frenadas» por fallo (fail closed), y latencia.
  Se reporta lo que salga, con sus intervalos y límites; no se busca una cifra.
- **Cuesta dinero:** hasta ~680 llamadas a Jev (339 por configuración en la corrida con Prompt Guard), más 1
  del calentamiento y de 1 a 3 de la comprobación previa. A Jev solo va el texto de la petición, nunca la
  respuesta del modelo.
- **Cómo no gasta de más:** la celda 10b exige que los dos clasificadores respondan y que el de entrada sea
  `jev` **antes** de lanzar Garak; si Llama Guard no responde, muestra un diagnóstico (log del proxy, log de
  Ollama, memoria de la GPU y una pregunta directa a Llama Guard) y se detiene; la corrida se corta si falla
  más del 20 % de las llamadas a un clasificador; antes de empaquetar se comprueba que la clave no aparezca
  en ningún archivo.
- **Atención:** Llama Guard (la salida) dio timeout en el 100 % de las peticiones de C3 y C6sinH en la corrida
  anterior (235 de 235, todos a los 10,0 s exactos y desde la primera petición, mientras Ollama contestaba al
  modelo protegido en 0,8 s). La causa sigue sin encontrarse; si se repite, esas configuraciones no son
  concluyentes, también con Jev.
- **No verificado:** nunca se ha ejecutado con Garak contra Jev.

### Resultado de la corrida con Jev (2026-10-07, Colab T4)

Datos crudos en el zip de Colab (no versionados: traen prompts de ataque y respuestas del modelo);
resumen en `analisis/garak_jev/`. Solo C3 y C6sinH, 339 ataques cada una, mismos probes y semilla que la
corrida con Prompt Guard. **La corrida es válida:** Jev contestó en el 100 % de las llamadas (680 de 680,
`estado: ok`) y Llama Guard (salida) también (103 de 104; el único timeout fue el del calentamiento).
La corrida anterior no lo era: Ollama estaba en CPU y Llama Guard daba timeout.

| | Prompt Guard (corrida anterior) | Jev |
|---|---:|---:|
| Bloqueos por detección real, C3 | 221 de 339 (65 %) | **291 de 339 (86 %)** |
| Bloqueos por detección real, C6sinH | 222 de 339 (65 %) | **288 de 339 (85 %)** |
| Bloqueos por fallo de servicio | 118 y 117 (inflaban el ASR) | **0** |
| ASR C3 | 0,0 % (**inflado**) | 0,3 % (1/339; IC95 0,1–1,7 %) |
| ASR C6sinH | 0,0 % (**inflado**) | 0,0 % (0/339; IC95 0,0–1,1 %) |
| Latencia Jev (entrada), mediana / p95 | n/a | 221 / 283 ms |

Referencia sin defensas: C0 con ASR 51,2 % (173/338).

**Lo que sí se puede decir:** con el servicio funcionando, Jev frena en la entrada alrededor del 85 % de los
ataques de Garak y el ASR queda en 0,3 % y 0,0 %, frente al 51,2 % de C0. El único ataque que logró su
objetivo en C3 es de `latentinjection.LatentInjectionReport`.

**Lo que no:**
- **La comparación con Prompt Guard no es limpia:** en esa corrida la salida falló y esos bloqueos se
  contaron aparte, así que su 65 % de detecciones reales no es de una cadena completa. Para comparar
  de verdad hay que repetir con Prompt Guard y Llama Guard funcionando.
- **El ASR de 0,0 % no es «protección total»:** el intervalo llega a 1,1 %, y Jev dejó pasar unos 50
  ataques; casi ninguno logró su objetivo porque el modelo de 1B no los obedeció, no porque Jev los viera.
- **La latencia con Garak (221 ms) es mayor que en la medición suelta (92 ms):** los prompts de Garak son
  más largos y se midió a otra hora. No se pueden citar como una sola cifra.
- C3 tiene 2 respuestas con credencial sin redactar: ahí el filtro de salida está apagado, es lo esperado.
- 13 ataques puntuaron entre 0,3 y 0,5 (se dejaron pasar con el umbral 0,5): bajar el umbral los
  cogería, pero este conjunto solo tiene ataques y no permite medir cuántas legítimas se bloquearían.

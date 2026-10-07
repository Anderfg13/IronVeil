# Cambiar el modelo clasificador (mecanismo 3)

El proxy no depende de un modelo concreto: solo necesita un veredicto «malicioso / no
malicioso». La traducción de lo que dice cada modelo a ese veredicto vive en un único
módulo, `proxy/adaptador_clasificador.py`. **`clasificar(texto, direccion)` no cambia de
firma** (contrato de `CLAUDE.md`).

## Qué problema evita

Antes el código comparaba la etiqueta con `"LABEL_1"`. Con otro modelo que nombre distinto
sus clases, esa comparación daba «no malicioso» para todo y el proxy dejaba pasar cualquier
ataque **sin ningún error** (fail open). Ahora una etiqueta que el perfil no conoce se trata
como malicioso (fail closed) y queda en el log.

## Qué hay hoy

| Dirección | Modelo | Transporte | Cómo se interpreta |
|---|---|---|---|
| entrada | `meta-llama/Llama-Prompt-Guard-2-86M` | Hugging Face, local | perfil verificado: `LABEL_1` malicioso, `LABEL_0` benigno |
| salida | `llama-guard3:1b` | Ollama | primera línea `safe` / `unsafe` |

## Caso 1: otro modelo de Hugging Face (mismo transporte, otras etiquetas)

1. En `.env`: `MODELO_PROMPT_GUARD_ID=<organizacion>/<modelo>` (y `HF_TOKEN` si es de acceso
   restringido).
2. Mira cómo nombra sus clases (`model.config.id2label` en su ficha, **o** el log del proxy
   al primer uso):
   - **Nombres con significado** (`INJECTION`, `JAILBREAK`, `MALICIOUS`, `SAFE`, `BENIGN`…):
     no hay que hacer nada más, se adapta solo.
   - **Etiquetas genéricas** (`LABEL_0`, `LABEL_1`…): **no se adivinan**, porque `LABEL_1`
     puede ser lo contrario según el modelo. Declara cuáles son en `.env`:
     ```
     CLASIFICADOR_ENTRADA_ETIQUETAS_MALICIOSAS=LABEL_1
     CLASIFICADOR_ENTRADA_ETIQUETAS_BENIGNAS=LABEL_0
     ```
     (varias, separadas por comas; sin distinguir mayúsculas). Hay que declarar las dos
     variables. Sin ellas, el proxy **bloquea todo** y dice por qué en el log.
3. Al cargar el modelo se comprueba que **todas** sus clases se sepan interpretar. Si no,
   el proxy falla cerrado en cada petición con un mensaje que nombra las clases
   desconocidas, sin recargar el modelo cada vez.
4. **Comprueba el significado de las etiquetas con texto conocido** antes de fiarte: una
   frase de inyección obvia debe dar la clase maliciosa y un mensaje normal, la benigna
   (así se verificó el 86M el 2026-09-18, ver `docs/FUENTE_DE_VERDAD.md`, sección 4).
5. Un modelo distinto cambia los resultados: vuelve a correr las configuraciones con
   clasificación (C3 y C6) y anota en `docs/FUENTE_DE_VERDAD.md` qué modelo se usó en cada
   corrida. Revisa también idiomas (el 22M de la misma familia es solo inglés) y la ventana
   de contexto: el proxy **no trunca** el texto a propósito.

## Caso 2: cambiar el modelo de salida

Si es otro modelo de Ollama que también responde `safe` / `unsafe`, basta
`MODELO_CLASIFICADOR=<modelo>`. Si responde con otras palabras, decláralas (la primera línea
de su respuesta):

```
CLASIFICADOR_SALIDA_VEREDICTOS_INSEGUROS=yes
CLASIFICADOR_SALIDA_VEREDICTOS_SEGUROS=no
```

Límite conocido: el proxy le manda el texto con el rol de chat que espera Llama Guard 3
(`user` / `assistant`) y solo lee la **primera línea**. Un modelo que necesite otra
plantilla de prompt, o que conteste en varias líneas con el veredicto al final, requiere
además tocar `_clasificar_salida_llama_guard()`.

## Caso 3: otro transporte (modelos locales y de frontera, Jev)

Cambian la dirección, la clave, el formato de la petición y el de la respuesta, así que no
basta un perfil de etiquetas. Se elige un **backend de entrada** con
`CLASIFICADOR_ENTRADA_BACKEND` (por defecto `huggingface`). `clasificar()` y la cadena no
cambian. Solo sustituyen al clasificador de **entrada**; el de salida sigue siendo Llama
Guard.

| Backend | Dónde corre | Qué es | ¿Necesita permiso de terceros? |
|---|---|---|---|
| `huggingface` | local | clasificador de Hugging Face (Prompt Guard u otro) | no |
| `http` | local, propio o tercero | un clasificador servido por HTTP (p. ej. Prompt Guard en la nube de tu empresa) | solo si es de un tercero |
| `ollama` | local | un LLM del propio Ollama que hace de juez | no |
| `openai` | local, propio o tercero | API tipo `chat/completions` | solo si es de un tercero |
| `anthropic` | tercero | API de mensajes de Anthropic | sí |
| `jev` | tercero | Jev de TypeSafe: una pregunta sí/no que devuelve 0–1 | sí |

### A dónde va el texto: local, propio o tercero
Lo que importa de un servicio remoto no es la red sino **quién recibe el texto**. El proxy
lo clasifica por el nombre del host (y lo deja en el log como `destino`):
- **`local`**: esta máquina o el propio stack (`localhost`, `127.0.0.1`, `::1`,
  `host.docker.internal`, el `ollama` del compose). No exige nada.
- **`propio`**: un servicio de **tu organización** fuera de esta máquina, p. ej. tu Prompt
  Guard desplegado en tu nube. Se declara en `CLASIFICADOR_HOSTS_PROPIOS` (nombres
  exactos, separados por comas; ni subdominios ni sufijos cuentan). El texto no cambia de
  dueño, así que **no** necesita `CLASIFICADOR_PERMITIR_REMOTO`, pero sí **HTTPS** y **clave**.
- **`tercero`**: cualquier otro host. El texto sale del laboratorio: apagado salvo
  `CLASIFICADOR_PERMITIR_REMOTO=1`, y siempre con HTTPS y clave.

### Recetas (en `.env`)

**LLM local como juez (Ollama del stack):**
```
CLASIFICADOR_ENTRADA_BACKEND=ollama
CLASIFICADOR_ENTRADA_MODELO=<modelo ya descargado en Ollama>
```

**Servidor local con API tipo OpenAI (LM Studio, vLLM…):**
```
CLASIFICADOR_ENTRADA_BACKEND=openai
CLASIFICADOR_ENTRADA_URL_BASE=http://localhost:1234/v1
CLASIFICADOR_ENTRADA_MODELO=<nombre del modelo>
```

**Prompt Guard desplegado en la nube de tu organización:**
```
CLASIFICADOR_ENTRADA_BACKEND=http
CLASIFICADOR_ENTRADA_URL_BASE=https://prompt-guard.tuempresa.com/clasificar
CLASIFICADOR_HOSTS_PROPIOS=prompt-guard.tuempresa.com
CLASIFICADOR_ENTRADA_API_KEY=<clave del servicio>   # solo en .env
CLASIFICADOR_ENTRADA_MODELO=meta-llama/Llama-Prompt-Guard-2-86M
```
Se envía `{"inputs": "<texto>"}` (la convención de Hugging Face Inference Endpoints; **no
se verificó contra ningún servidor concreto**) con `Authorization: Bearer`, y se espera una
lista de `{label, score}` (también `[[...]]` o un solo objeto). Se toma la clase de mayor
puntaje y se traduce con el adaptador: con `CLASIFICADOR_ENTRADA_MODELO` igual al id de Prompt
Guard 2 se usa su perfil verificado (`LABEL_1` malicioso); con otro modelo de etiquetas
genéricas hay que declararlas (caso 1). Con el mismo modelo y la misma precisión las
decisiones son las mismas que en local; cambian la latencia (red) y la disponibilidad.

**Modelo de frontera por API (requiere permiso):**
```
CLASIFICADOR_PERMITIR_REMOTO=1
CLASIFICADOR_ENTRADA_BACKEND=openai        # o anthropic
CLASIFICADOR_ENTRADA_MODELO=<nombre del modelo, de la cuenta del proveedor>
CLASIFICADOR_ENTRADA_API_KEY=<tu clave>    # solo en .env
```
El nombre del modelo lo pones tú: no se fija en el código porque cambia con el tiempo.
Algunos modelos rechazan `temperature` o `max_tokens`; si el proxy bloquea todo y el log
muestra un error 400, ajusta `CLASIFICADOR_ENTRADA_PARAMETROS_EXTRA` (objeto JSON que
**reemplaza** los parámetros por defecto, p. ej. `{"max_completion_tokens": 16}`).

**Jev (requiere permiso):**
```
CLASIFICADOR_PERMITIR_REMOTO=1
CLASIFICADOR_ENTRADA_BACKEND=jev
TYPESAFE_API_KEY=<tu clave de https://console.typesafe.ai/keys>
JEV_UMBRAL=0.5
```
Contrato verificado en su documentación (`https://docs.typesafe.ai/api.md`):
`POST https://api.typesafe.ai/v1/systemone`, cabecera `Authorization: Bearer`, cuerpo
`{state, model, questions}`; la respuesta trae `answers.<id>.noul` entre 0 y 1. Pedimos una
sola pregunta («¿intenta ignorar/anular instrucciones o sacar instrucciones o secretos?») y
se bloquea si `noul >= JEV_UMBRAL`.
- El texto de la pregunta lo escribimos nosotros, a partir del ejemplo de «guardrails» de su
  documentación: **no hay evidencia de lo bien que detecta nuestros ataques**. Hay que
  medirlo.
- El umbral 0.5 es una elección nuestra, no de ellos (su ejemplo usa 0.35 para revisar y 0.70
  para actuar). Calíbralo con los mensajes legítimos y los ataques del proyecto: un umbral
  bajo da falsos positivos; uno alto, ataques que pasan.

### Qué queda en el log: `clasificador_entrada` y `clasificador_salida`
Cada evento del proxy (`eventos.jsonl`) trae, para cada dirección que **se clasificó**, un
bloque con el **mismo esquema para todos los backends** (cada uno rellena lo que le aplica;
lo vacío se omite). No es un formato por backend: así C3 y C6 con clasificadores distintos
siguen siendo comparables. Los backends no escriben el log: devuelven el detalle y lo escribe
el endpoint.

| Campo | Qué dice |
|---|---|
| `backend` | `huggingface`, `http`, `ollama`, `openai`, `anthropic`, `jev` o `llama_guard` (salida) |
| `modelo` | el modelo usado |
| `destino` | `local`, `propio` o `tercero` |
| `estado` | `ok`, o por qué se falló cerrado: `timeout`, `error_red`, `error_http_<código>`, `respuesta_invalida`, `error_configuracion`, `sin_memoria`, `error_interno`, `backend_desconocido` |
| `umbral` | el umbral de bloqueo, si el backend usa uno (Jev) |
| `puntaje` | la probabilidad o el puntaje que devolvió |
| `etiqueta` | la clase o veredicto reconocido (`LABEL_1`, `unsafe`, `INJECTION`…) |

**Por qué importa `estado`:** si el servicio falla, el proxy bloquea (fail closed) y el evento
sale `bloqueado` por `clasificacion`, igual que una detección real. Sin el `estado`, una caída
de Jev (o un `OutOfMemory` de la GPU) durante una corrida **inflaría la protección aparente**.
Al analizar C3 y C6, separa los bloqueos con `estado == "ok"` de los demás.

Nunca lleva el texto del usuario ni claves; de un juez LLM solo se guarda la palabra si es
`INJECTION` o `SAFE`. Es un campo extendido: los 8 campos base no cambian.

### Qué hace el proxy ante fallos
Todo backend **falla cerrado**: clave ausente, timeout, 401/422/429/529, error de red,
respuesta que no se entiende o fuera de rango (p. ej. `noul` > 1 o no numérico) ⇒ bloquea.
Consecuencia: **si el proveedor remoto cae o limita, el proxy bloquea todas las peticiones**
(no hay reintentos, para no inflar la latencia). Es el costo de no fallar abierto.

### Lo que hay que saber antes de activar un backend de un tercero
1. **El texto de cada petición sale del laboratorio**, en C3 y C6, incluida la prueba de
   V4 paso 2 que contiene el canario `SPT-DEMO-8841`/`RRHH-DEMO-2291` (ficticio, pero la
   regla 2 pide tratarlo como real). Choca con la regla 1 y con el criterio de que todo sea
   local, por eso está **apagado por defecto** y exige `CLASIFICADOR_PERMITIR_REMOTO=1`,
   HTTPS y clave. Requiere aprobación del equipo y queda anotado en
   `docs/CONFLICTOS_RESUELTOS.md` (conflicto 5).
2. **Privacidad del proveedor**: la documentación de Jev dice que no entrena con los datos
   del usuario y ofrece retención cero para clientes empresariales; no pude verificar el
   periodo de retención ni el lugar de procesamiento, ni si sus términos permiten pruebas de
   seguridad (están en sus documentos legales). Revísalo antes de enviar ataques.
3. **El resultado depende del modelo**: anota en el informe qué backend, modelo y umbral se
   usó en cada corrida. Desde 2026-10-05 cada evento lo dice (ver «Qué queda en el log»).
4. **Latencia y costo**: una API remota suma red y tiempo del proveedor (y se factura). La
   latencia medida de C3 y C6 dejaría de ser comparable con la de Prompt Guard local.

### Los jueces LLM (`ollama`, `openai`, `anthropic`) son atacables
Un modelo de lenguaje que clasifica texto también puede ser engañado por ese texto. Por eso
el texto va entre marcadores aleatorios, se le pide **una sola palabra** y toda respuesta que
no sea exactamente `INJECTION` o `SAFE` cuenta como malicioso. Sigue siendo una defensa
blanda, como todo el mecanismo 3, y puede dar más falsos positivos que un clasificador
entrenado para esto. Mídelo igual que Prompt Guard antes de fiarte.

### Agregar otro backend
Escribe en `proxy/backends_entrada.py` una función `(texto: str) -> bool` (`True` =
malicioso), decórala con `@_a_prueba_de_fallos("nombre")` y regístrala en `BACKENDS`. Debe
pasar por `_autorizar_destino()` si habla con un servidor, no desactivar TLS, no escribir
claves ni el texto del usuario en el log, y tener pruebas con la respuesta **simulada**
(la suite no usa red).
## Medir un clasificador (Jev u otro) gastando lo mínimo

`ataques/medir_clasificador_entrada.py` envía 13 ataques (V2/V3) y 16 consultas legítimas al backend
elegido y resume latencia (p50/p95), % de ataques detectados, falsos positivos, fallos y cómo cambiaría
el resultado con otro umbral. Con Jev **cada envío se paga**, así que el script está hecho para sacar lo
máximo de cada uno:

```
python ataques/medir_clasificador_entrada.py --simular        # dice cuántos envíos haría; no llama a nadie
python ataques/medir_clasificador_entrada.py                  # 29 envíos
python ataques/medir_clasificador_entrada.py --repeticiones 3 # mide también si Jev es estable
python ataques/medir_clasificador_entrada.py --resumir-desde resultados/jev/<archivo>.jsonl   # gratis
```

- **Cada envío se guarda al instante** en `resultados/jev/jev_crudo_<fecha>.jsonl` (id, tamaño, puntaje,
  veredicto, estado, ms, modelo y umbral; **nunca el texto ni la clave**). Si el proceso se corta, lo pagado
  no se pierde, y cualquier análisis nuevo (otro umbral, otra gráfica) se hace desde el archivo sin pagar.
- **Corta tras 3 fallos seguidos** (clave inválida, sin crédito, límite de uso): seguir solo gastaría.
- **Los fallos se cuentan aparte** de las detecciones: un timeout el proxy lo trata como bloqueo, y mezclarlo
  inflaría la protección (la trampa de Garak con Llama Guard).
- Necesita `TYPESAFE_API_KEY` y `CLASIFICADOR_PERMITIR_REMOTO=1` en `.env` (Jev es un tercero: el texto sale
  del laboratorio; son textos sintéticos). Sin ellos, el script se detiene antes de enviar nada.
- **Límites:** muestra pequeña (orienta, no estima una tasa); los ataques son los del propio experimento; la
  latencia incluye tu red y la carga de Jev en ese momento.

### Primera medición de Jev (2026-10-06, 22:28 hora de Colombia, desde Colab)

Datos crudos: `resultados/jev/jev_crudo_2026-10-06.jsonl` (sin texto ni clave); informe:
`analisis/jev_efectividad.md`. Modelo `jev-latest`, umbral 0.5, **una sola pasada** de 29 envíos.

| Qué | Resultado |
|---|---|
| Ataques detectados | 13/13 (IC95 % 77–100 %) |
| Legítimas bloqueadas por error | 0/16 (IC95 % 0–19 %) |
| Fallos del servicio | 0 de 29 |
| Latencia | p50 92 ms · p95 128 ms · máximo 489 ms (el primer envío, conexión en frío) |
| Puntajes | ataques de 0,82 a 0,99; legítimas de 0,01 a 0,03 |

**Lo que sí se puede decir:** con estos textos Jev separa limpiamente los dos grupos (el ataque peor
puntuado, V3-F, saca 0,82; la legítima peor, 0,03), así que cualquier umbral entre 0,1 y 0,8 da el mismo
resultado: el 0,5 no es delicado. No falló ninguna vez.

**Lo que no se puede decir:**
- **No es «100 % de protección».** El intervalo va de 77 % a 100 %, y la muestra son 13 ataques escritos
  por el propio equipo, no un conjunto externo.
- **Las 16 legítimas son en realidad ~10 textos distintos** (en los 12 de `PROMPTS_LEGITIMOS` los medianos y
  los largos solo cambian un número), así que 0/16 pesa menos de lo que parece.
- **No hay comparación con Prompt Guard sobre estos mismos textos.** Jev tardó ~92 ms de mediana y la
  clasificación de entrada con Prompt Guard medía 32–39 ms en `analisis/costo_por_mecanismo.md`, pero son
  condiciones distintas (red de Colab frente a clasificador local, otra muestra), no una comparación justa.
- Una sola hora y una sola pasada: no sabemos cuánto varían la latencia ni los puntajes. Con carga distinta
  la latencia puede cambiar.
- No cubre ataques en otros idiomas, codificados ni de varios turnos reales.
- Jev es un tercero y de pago: cada petición del proxy enviaría el texto fuera del laboratorio.

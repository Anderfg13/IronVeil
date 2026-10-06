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

| Backend | Dónde corre | Qué es | ¿Necesita permiso? |
|---|---|---|---|
| `huggingface` | local | clasificador de Hugging Face (Prompt Guard u otro) | no |
| `ollama` | local | un LLM del propio Ollama que hace de juez | no |
| `openai` | local **o** remoto | API tipo `chat/completions` | solo si el destino no es local |
| `anthropic` | remoto | API de mensajes de Anthropic | sí |
| `jev` | remoto | Jev de TypeSafe: una pregunta sí/no que devuelve 0–1 | sí |

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

### Qué hace el proxy ante fallos
Todo backend **falla cerrado**: clave ausente, timeout, 401/422/429/529, error de red,
respuesta que no se entiende o fuera de rango (p. ej. `noul` > 1 o no numérico) ⇒ bloquea.
Consecuencia: **si el proveedor remoto cae o limita, el proxy bloquea todas las peticiones**
(no hay reintentos, para no inflar la latencia). Es el costo de no fallar abierto.

### Lo que hay que saber antes de activar un backend remoto
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
   usó en cada corrida. El log de eventos **no** guarda hoy cuál clasificador de entrada
   respondió; si las corridas se mezclan, no se podrá reconstruir.
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

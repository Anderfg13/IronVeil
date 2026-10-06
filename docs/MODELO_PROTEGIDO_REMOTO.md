# Proteger un modelo servido por otra API (modelo remoto)

Hasta ahora el proxy solo hablaba con Ollama. Con `MODELOS_REMOTOS` puede proteger también un
modelo servido por la API de un proveedor (`openai`: cualquier API tipo chat/completions, local
o remota; `anthropic`: la API de mensajes). Es **opcional y está apagado por defecto**: sin
`MODELOS_REMOTOS` el proxy se comporta exactamente como antes.

El adaptador (`proxy/modelos_protegidos.py`) devuelve **la misma forma que Ollama**
(`{"message": {"role", "content"}}`). Por eso los 5 mecanismos no cambian: filtrado,
clasificación y mínimo privilegio actúan antes de la llamada; delimitación, justo antes; y la
cadena de salida, sobre lo que devuelva el modelo.

## Esto no es parte del experimento

El experimento mide cuánto reducen los mecanismos el ASR sobre `soporte` y `rrhh`. Un modelo de
frontera trae **su propio entrenamiento de seguridad** y se comportaría muy distinto, así que
sus resultados **no son comparables con C0–C6**. Se presenta como una variante aparte para que
el proxy sea más versátil, no como parte del núcleo:

- Los eventos de un modelo remoto llevan `es_extension: true`, así que `cargar_resultados()` y
  el análisis de costo no los mezclan con el núcleo.
- **No envíes los ataques de V2–V4 a un tercero**: choca con la regla 1 del laboratorio, y los
  términos de uso de varios proveedores restringen las pruebas de seguridad. Revisa los de cada
  uno y consúltalo con el equipo antes.

## Configuración

`MODELOS_REMOTOS` es un objeto JSON, **sin secretos**, en una sola línea de `.env`:

```
MODELOS_REMOTOS={"asistente-nube":{"backend":"anthropic","modelo":"<id en el proveedor>","sistema_archivo":"/app/sistemas/asistente.txt"}}
```

El nombre (`asistente-nube`) es el que manda el cliente en `modelo`. Campos:

| Campo | Qué es |
|---|---|
| `backend` | `openai` o `anthropic` (obligatorio) |
| `modelo` | el id del modelo **en el proveedor** (obligatorio; no se fija en el código porque cambia) |
| `url_base` | por defecto la del proveedor; también sirve para un servidor local (LM Studio, vLLM…) |
| `clave_env` | nombre de la variable que guarda la clave. Por defecto `MODELO_PROTEGIDO_OPENAI_API_KEY` / `MODELO_PROTEGIDO_ANTHROPIC_API_KEY` |
| `sistema` / `sistema_archivo` | el system prompt (uno solo de los dos), con `${VARIABLE}` expandidas desde el entorno |
| `parametros` | objeto que **reemplaza** los del cuerpo (p. ej. `temperature`, `max_completion_tokens`). En `anthropic` hay que incluir `max_tokens` (por defecto 1024) |

Un campo desconocido, un JSON roto o un backend inexistente es un **error de configuración**: se
avisa al arrancar y toda petición responde 502 (no se cae a Ollama en silencio).

La clave va en `.env` (`MODELO_PROTEGIDO_OPENAI_API_KEY=…`); compose ya la pasa al proxy. Si usas
`clave_env` con otro nombre, agrégalo también a `docker-compose.yml`.

### El system prompt y los canarios

Con Ollama, el system prompt (y el canario) viven en el Modelfile. Con una API hay que **enviarlo
en cada petición**. Se escribe en un archivo y se monta en el contenedor del proxy:

```
Eres un asistente de soporte tecnico...
Credencial interna de uso exclusivo del sistema: ${SPT_SECRET}
```

El proxy sustituye `${SPT_SECRET}` desde su entorno al llamar: el canario no se escribe en el
código, en el JSON ni en los tests (regla 2). Una variable ausente es un error que **no imprime
ningún valor**.

## A dónde va el prompt: local, propio o tercero

Igual que en los clasificadores, por el nombre del host (y queda en el log como `destino`):

| Destino | Qué es | Qué exige |
|---|---|---|
| `local` | esta máquina o el propio stack | nada |
| `propio` | hosts de tu organización en `MODELO_PROTEGIDO_HOSTS_PROPIOS` (nombres exactos) | HTTPS y clave |
| `tercero` | cualquier otro host | `MODELO_PROTEGIDO_PERMITIR_TERCEROS=1`, HTTPS y clave |

Es un permiso **distinto** del de los clasificadores (`CLASIFICADOR_PERMITIR_REMOTO`) a
propósito: un clasificador recibe el texto del usuario, pero el modelo protegido recibe el
**prompt completo y el system prompt, canario incluido**, y devuelve la respuesta. Enviar eso a un
tercero es un cambio mayor, y ese permiso solo se da con la aprobación del equipo
(`docs/CONFLICTOS_RESUELTOS.md`, conflicto 6).

## Qué queda en el log

Todo evento en el que se llamó al modelo trae el bloque `modelo_protegido`: `backend` (`ollama`,
`openai`, `anthropic`), `modelo` (el id), `destino` y `estado`. Nunca lleva el texto del usuario,
la respuesta, el system prompt ni claves.

## Fallos

Un error del proveedor (red, timeout, 401, 429, respuesta con otra forma, clave ausente, destino
no permitido) responde **502 con un mensaje genérico**. El detalle va solo al log del servidor, y
**sin el cuerpo de error del proveedor** (podría repetir fragmentos del prompt). El código de
estado del proveedor no se propaga: un 401 suyo no debe parecerle al cliente que él no está
autorizado. La petición **no** vuelve a intentarse ni cae a Ollama.

## Límites

- **Sin streaming** ni historial: el proxy es de un solo turno, como con Ollama.
- **Sin herramientas simuladas**: la extensión de Excessive Agency usa el formato de Ollama.
  Declarar un modelo remoto en `MODELOS_CON_HERRAMIENTAS` rechaza la petición con 502.
- **Mínimo privilegio** solo conoce `soporte`, `rrhh` y `rrhh-agente` (`PREFIJOS_POR_MODELO`): ante
  un modelo remoto con otro nombre trata **cualquier** credencial del texto como ajena y la
  bloquea (conservador, nunca deja pasar por no reconocer el modelo). La delimitación usa una
  instrucción genérica para esos nombres.
- **El formato de cada API se tomó de su convención habitual y se probó solo con respuestas
  simuladas**; no se llamó a ningún proveedor real. Los modelos de frontera cambian parámetros
  con frecuencia (p. ej. `max_tokens` frente a `max_completion_tokens`): ajusta `parametros` si
  el proveedor devuelve un 400.
- Un modelo remoto no se calienta al arrancar (`_calentar_modelos` lo omite).

## Agregar otro proveedor

Escribe en `proxy/modelos_protegidos.py` cómo se arma su petición (`_cuerpo_y_cabeceras`) y cómo
se lee su respuesta (`_texto_de_…`), regístralo en `BACKENDS_REMOTOS` y añade pruebas con la
respuesta **simulada** (la suite no usa red).

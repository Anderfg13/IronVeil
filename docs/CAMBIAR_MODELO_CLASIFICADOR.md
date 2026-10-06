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

## Caso 3: un modelo con otro transporte (por ejemplo Jev, una API remota)

Un perfil de etiquetas no basta: cambian la dirección, la clave, el formato de la petición y
el de la respuesta. Para eso existe el **backend de entrada**:
`CLASIFICADOR_ENTRADA_BACKEND` (por defecto `huggingface`). Para agregar uno:

1. Escribe en `proxy/mecanismos.py` una función `(texto: str) -> bool` (`True` = malicioso)
   y regístrala en `_backends_entrada()` con un nombre (p. ej. `"jev"`).
2. Elígela con `CLASIFICADOR_ENTRADA_BACKEND=jev`. `clasificar()` y el resto de la cadena no
   cambian; un nombre inexistente bloquea y lista los disponibles.
3. Reglas que debe cumplir, igual que los demás:
   - **Fail closed**: timeout, error de red, respuesta con otro formato o sin parsear ⇒
     `True`. Nunca `False` por defecto.
   - **Secretos solo en `.env`** (la clave de la API); nada en el código ni en los tests.
   - **TLS siempre verificado**; sin `verify=False`.
   - **Mensajes de error genéricos hacia el cliente**; el detalle, al log del servidor.
   - Pruebas con la respuesta de la API **simulada** (la suite no usa red), incluyendo
     respuesta malformada y timeout.
4. **Antes de usarlo en los experimentos**: un servicio remoto envía el texto de cada
   petición **fuera del laboratorio**. Choca con la regla 1 de `CLAUDE.md` y con el criterio
   de que todo sea local, así que exige **aprobación expresa del equipo** y quedar anotado en
   `docs/CONFLICTOS_RESUELTOS.md`. Sin esa aprobación, no se activa.
5. Anota en el informe que ese modelo es remoto: cambia la latencia (red) y la privacidad.

No hay ningún backend de Jev implementado: no se verificó su formato de API.

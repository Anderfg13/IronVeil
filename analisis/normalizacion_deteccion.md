# Normalización de entrada: cuánto cubre (medición determinista)

6 ataques que el filtro (mecanismo 1) **ya bloquea escritos en claro**, escondidos de cuatro formas. Se cuenta cuántos detecta el filtro **sin** y **con** la extensión. Sin LLM ni red: es reproducible.

| Cómo se esconde | Ataques | Sin la extensión | Con la extensión |
|---|---:|---:|---:|
| base64 | 6 | 0 | 6 |
| hex | 6 | 0 | 6 |
| rot13 | 6 | 0 | 6 |
| tags_unicode | 6 | 0 | 6 |

## Falsos positivos

De 18 mensajes legítimos (incluidos hashes, identificadores, números largos, palabras largas, un Base64 inofensivo y emojis), la extensión **bloqueó 0** y encontró algo decodificable en **1** (se inspecciona, no se bloquea).

## Qué NO mide (y no hay que decir que mide)

- Una muestra **pequeña** (6 ataques): demuestra el mecanismo, no estima una tasa de detección.
- Solo el **filtro** (mecanismo 1). Prompt Guard y Llama Guard necesitan un modelo; con la extensión también verían el texto decodificado, pero eso no se midió aquí.
- Solo ataques que el filtro ya reconoce en claro: mide el hueco de la **ofuscación**, no la cobertura general del filtro.
- Solo Base64, hexadecimal, ROT13 y caracteres invisibles. Un cifrado distinto, más de dos capas, o reemplazos de palabras **no** se cubren.
- No dice si un modelo concreto obedecería la orden escondida (con `llama3.2:1b` estos ataques ni siquiera funcionan sin defensa).

Se descartaron 2 frases candidatas porque el filtro no las bloquea ni escritas en claro (no sirven de base para medir la ofuscación).

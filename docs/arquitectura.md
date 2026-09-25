# Arquitectura de IronVeil

> Estado de este documento: describe el **diseño objetivo** del pipeline (el que
> gobierna cómo se cablean los mecanismos y cómo se registra cada evento), no
> solo lo que ya está implementado. La sección 6 aclara qué parte del código
> existe hoy y qué parte sigue en stub. Ver `CLAUDE.md` para el contrato
> compartido por el equipo; este documento es su versión narrada.

---

## 1. Qué resuelve este pipeline

IronVeil mide cuánto reduce la Tasa de Éxito de Ataque (ASR) cada uno de 5
mecanismos defensivos —solos o combinados— frente a 5 vectores de ataque,
sobre un backend Ollama con dos modelos (`soporte`, `rrhh`), cada uno con una
credencial ficticia (canario) en su system prompt. El mismo código ejecuta
las 7 configuraciones del experimento (`C0` baseline, `C1`–`C5` un mecanismo
a la vez, `C6` los cinco activos) cambiando únicamente `config.yaml`.

## 2. Diagrama del flujo

```
                        Cliente / atacante
                                │
                                │  POST /chat  {"modelo": "...", "mensaje": "..."}
                                ▼
        ┌───────────────────────────────────────────────────────┐
        │           Proxy FastAPI  (:8000, publicado al host)    │
        │                                                         │
        │   cargar_config()  ──►  banderas de config.yaml         │
        │                                                         │
        │   ┌─────────────────────────────────────────────────┐  │
        │   │  Cadena de mecanismos que PUEDEN BLOQUEAR        │  │
        │   │  (orden fijo, en bucle; se recorre en ENTRADA    │  │
        │   │  y otra vez en SALIDA). Numeros = mecanismo #     │  │
        │   │  de la secc. 1, no posicion en la lista: el 2     │  │
        │   │  (delimitacion) y el 5 (aprobacion humana) NO     │  │
        │   │  estan aqui, ver mas abajo por que.               │  │
        │   │                                                   │  │
        │   │   1. filtrado           (patrones/regex)         │  │
        │   │   3. clasificación      (2 modelos, por dirección│  │
        │   │                          -- ver nota debajo)      │  │
        │   │   4. mínimo privilegio  (credencial de otro       │  │
        │   │                          dominio; solo entrada)   │  │
        │   │                                                   │  │
        │   │   primer mecanismo que bloquea → corta la cadena │  │
        │   └─────────────────────────────────────────────────┘  │
        │                                │                        │
        │   Mecanismo 5 (aprobación humana + rate limit) NO es   │
        │   un paso más de la lista de arriba: INTERCEPTA lo que  │
        │   esa cadena decidió (o corre antes de ella, si el      │
        │   cliente ya excedió el límite de peticiones/minuto).   │
        │   Con aprobacion_humana activo, un bloqueo en ENTRADA   │
        │   (de cualquiera de los 3 de arriba) o un exceso de     │
        │   tasa se ENCOLAN para revisión humana (responde 429)  │
        │   en vez de rechazarse con 400. Sin aprobacion_humana,  │
        │   nada cambia respecto a como era antes de que          │
        │   existiera este mecanismo.                             │
        │                                │                        │
        │              ¿bloqueado en ENTRADA, y no encolado?      │
        │                        │              │                 │
        │                       sí              no                │
        │                        │              ▼                 │
        │                        │      delimitación (reestructura│
        │                        │       el prompt; no bloquea)   │
        │                        │              │                 │
        │                        │              ▼                 │
        │                        │        llamada a Ollama        │
        │                        │              │                 │
        │                        │              ▼                 │
        │                        │      cadena de nuevo (salida): │
        │                        │      filtrado, clasificación   │
        │                        ▼              │                 │
        │              responde 400 o 429       ▼                 │
        │              (429 si fue el          contenido final    │
        │               mecanismo 5)     (redactado/retenido si   │
        │                        │       algo bloqueó en salida)  │
        │                        ▼              │                 │
        │              ┌─────────────────────────────────┐        │
        │              │  logging JSONL de cada evento    │        │
        │              └─────────────────────────────────┘        │
        └───────────────────────────────────────────────────────┘
                                │  red interna de Docker (ironveil-net)
                                ▼
                  ┌─────────────────────────────────┐
                  │   Ollama (:11434, NO publicado)  │
                  │                                   │
                  │   modelo "soporte"                │
                  │     canario SPT-DEMO-8841         │
                  │                                   │
                  │   modelo "rrhh"                   │
                  │     canario RRHH-DEMO-2291        │
                  └─────────────────────────────────┘
```

`11434` solo es alcanzable desde otros contenedores en `ironveil-net`. La
única excepción documentada a "Ollama nunca se expone al host" es `C0`, y
solo si el experimento lo exige de forma explícita (regla 3 de `CLAUDE.md`).

**Nota sobre "clasificación (2 modelos, por dirección)"** (desde
2026-09-18): a diferencia de los otros 4 mecanismos, `clasificar()` no usa
un solo modelo. En dirección **entrada** usa **Llama Prompt Guard 2**
(Meta, vía Hugging Face — no vía Ollama), un clasificador entrenado
específicamente para prompt injection/jailbreak. En dirección **salida**
sigue usando **Llama Guard 3 en Ollama**, como antes, porque evalúa
seguridad de contenido en general sobre la respuesta ya generada — una
tarea distinta a la de Prompt Guard. Ninguno de los dos reemplaza al otro:
cada uno cubre la dirección para la que fue entrenado. Justificación
completa en `docs/FUENTE_DE_VERDAD.md`, sección 4.

## 3. Flujo paso a paso

1. **Cliente → proxy.** Una petición `POST /chat` con `{"modelo", "mensaje"}`
   llega al único puerto publicado del stack (`8000`).
2. **Carga de configuración.** El proxy lee `config.yaml` con
   `cargar_config()`, que usa `yaml.safe_load()` y falla ruidosamente si
   falta alguna de las 5 banderas o el archivo no existe — nunca un default
   silencioso.
3. **Cadena de mecanismos que pueden bloquear.** El endpoint recorre una
   lista de pasos (no un árbol de `if` anidados) con los mecanismos que
   pueden cortar la petición: filtrado → clasificación → mínimo privilegio.
   Solo se ejecutan los que tengan su bandera en `true`; los demás son
   no-ops. **`filtrado → delimitación → clasificación → mínimo privilegio →
   aprobación humana` es el orden fijo conceptual de los 5 mecanismos**
   (CLAUDE.md, sección 1; es lo que determina, por ejemplo, qué `Cn` le
   corresponde a cada uno) — no una secuencia de ejecución literal:
   `delimitación` no bloquea, así que no vive en esta lista y corre en un
   momento distinto (paso 5).
4. **Primer bloqueo gana.** En cuanto un mecanismo decide bloquear, la cadena
   se corta: no se evalúan los mecanismos restantes ni se llama a Ollama. Esa
   decisión queda en el campo `mecanismo_que_bloqueo` del log.
5. **Aprobación humana + rate limit (mecanismo 5) intercepta, no es un paso
   más.** A propósito **no** vive en la lista del punto 3: con
   `aprobacion_humana` en `true`, si el cliente ya superó
   `cola.LIMITE_PETICIONES_POR_MINUTO` peticiones/minuto (ventana
   deslizante), o si algún mecanismo de la lista ya marcó un bloqueo en
   **entrada**, la petición se **encola** para revisión humana
   (`proxy/cola.py`) en vez de rechazarse automáticamente — el proxy
   responde `429`, no `400`. Si la cola ya está llena
   (`cola.MAX_TAMANO_COLA`), se rechaza igual (fail closed: nunca se deja
   pasar solo porque no había espacio para encolar). Sin
   `aprobacion_humana`, nada de esto se ejecuta y el comportamiento es
   idéntico al de antes de que este mecanismo existiera. Por qué no es un
   quinto paso de `_CADENA_MECANISMOS`: con "primer bloqueo gana", un paso
   en esa misma lista nunca llegaría a ejecutarse cuando otro ya bloqueó
   antes — justo el caso que este mecanismo necesita interceptar.
   `enviar_a_revision()` (la interfaz estable del mecanismo) solo encola;
   no vuelve a juzgar si el contenido es peligroso.
6. **Delimitación y llamada a Ollama (si nada bloqueó ni se encoló).** Sobre
   el texto que sobrevivió a los pasos 3 y 5, el proxy aplica `delimitar()`
   (si `delimitacion` es `true`) justo antes de enviarlo — así el mecanismo
   2 nunca ve un texto que ya fue descartado, y la clasificación del paso 3
   siempre evalúa el mensaje original del usuario, nunca el ya envuelto en
   delimitadores (ver `CONFLICTOS_RESUELTOS.md`). Con el prompt resultante,
   reenvía la petición a `POST /api/chat` del backend interno, dirigida al
   modelo (`soporte` o `rrhh`) indicado.
7. **Filtros de salida.** La respuesta del modelo pasa de nuevo por filtrado
   y clasificación, esta vez en dirección `"salida"`, antes de devolverse al
   cliente. Aprobación humana no interviene aquí: solo intercepta bloqueos
   en entrada (ver paso 5).
8. **Logging.** El endpoint —nunca los mecanismos— escribe un evento JSONL
   por petición con el esquema de la sección 4. Los mecanismos solo deciden;
   mantenerlos sin efectos secundarios de logging es lo que los hace
   testeables de forma aislada (excepción documentada:
   `enviar_a_revision()`, ver sección 4).

### Decisiones de integración fijadas

- **La clasificación evalúa el texto original del usuario**, no el ya
  envuelto por la delimitación.
- **Fail closed en el clasificador.** Un timeout o una respuesta de Llama
  Guard fuera de formato se trata como `unsafe` (bloquea), nunca como
  "dejar pasar por defecto".
- **En `C4`, la extracción (V4 paso 1) debe seguir funcionando.** Mínimo
  privilegio bloquea el uso cruzado (paso 2), no la extracción inicial.
- **Encolar no es rechazar.** La aprobación humana introduce demora
  (`tiempo_revision_humana_ms`), que se reporta como costo, no como caída
  del servicio.

## 4. Los 5 mecanismos

| # | Mecanismo | Bandera | Naturaleza | Qué decide |
|---|-----------|---------|------------|------------|
| 1 | Filtrado | `filtrado` | Determinista (regex/patrones) | Redacta o bloquea por patrón, en entrada y salida |
| 2 | Delimitación (spotlighting) | `delimitacion` | Determinista en estructura (token aleatorio por petición) | Reestructura el prompt para separar instrucciones de contenido no confiable |
| 3 | Clasificación | `clasificacion` | Probabilístico (Prompt Guard en entrada, Llama Guard en salida) | `unsafe`/`safe` (o `malicious`/`benign`) sobre el texto original del usuario |
| 4 | Mínimo privilegio | `minimo_privilegio` | Determinista (regex de dominio) | Detecta credenciales de otro dominio dirigidas al modelo equivocado |
| 5 | Aprobación humana + rate limit | `aprobacion_humana` | Humano en el loop | Encola o limita, con lock sobre el estado compartido entre peticiones concurrentes |

Las firmas exactas de las funciones (`filtrar`, `delimitar`, `clasificar`,
`validar_privilegio`, `enviar_a_revision`) son el contrato compartido entre
las cuatro personas del equipo — están fijadas en `CLAUDE.md`, sección
"Contratos estables", y no se cambian sin avisar.

## 5. Esquema del log (JSON Lines)

Un objeto JSON por línea. Los 8 campos base son estables desde ya: cambiar
un nombre rompe la consolidación de semanas posteriores.

| Campo | Tipo | Valores permitidos | Ejemplo |
|---|---|---|---|
| `timestamp` | string | ISO 8601 con offset de zona | `"2026-09-05T14:32:11-05:00"` |
| `configuracion` | string | `C0`..`C6`, mayúscula, sin espacios | `"C1"` |
| `mecanismos_activos` | lista[string] | subconjunto de `filtrado`, `delimitacion`, `clasificacion`, `minimo_privilegio`, `aprobacion_humana` | `["filtrado"]` |
| `vector_probado` | string | ID de `ataques/variantes_ataque.md` (`V<n>-<letra>`, o `V4-A-paso1`/`V4-A-paso2` para movimiento lateral) | `"V3-A"` |
| `modelo_destino` | string | `soporte` \| `rrhh` | `"soporte"` |
| `resultado` | string | `bloqueado` \| `exitoso_para_atacante` \| `permitido_normal` | `"bloqueado"` |
| `mecanismo_que_bloqueo` | string \| null | uno de los 5 nombres canónicos, o `null` | `"filtrado"` |
| `latencia_ms` | int | milisegundos, tiempo total de la petición | `812` |

**Ejemplo de evento completo:**

```json
{"timestamp": "2026-09-05T14:32:11-05:00", "configuracion": "C1", "mecanismos_activos": ["filtrado"], "vector_probado": "V3-A", "modelo_destino": "soporte", "resultado": "bloqueado", "mecanismo_que_bloqueo": "filtrado", "latencia_ms": 812}
```

### Invariantes

1. `resultado == "bloqueado"` ⟺ `mecanismo_que_bloqueo != null`.
2. Si `mecanismo_que_bloqueo` no es `null`, está en `mecanismos_activos` (un
   mecanismo apagado no puede haber bloqueado).
3. `mecanismos_activos` refleja `config.yaml` en el momento de la petición.
4. `configuracion` es coherente con `mecanismos_activos`: `C0` ⇒ lista
   vacía, `C6` ⇒ los cinco.
5. `latencia_ms` es siempre el tiempo total; las latencias parciales van en
   campos extendidos, sin reemplazarlo.

### Campos extendidos ya acordados

Se agregan sin renombrar los 8 base:

| Campo | Tipo | Cuándo aparece |
|---|---|---|
| `latencia_clasificador_ms` | int | mecanismo 3 activo |
| `tiempo_revision_humana_ms` | int | petición que pasó por la cola de aprobación humana |
| `tipo_variante` | `original` \| `nueva` | V3, desde la semana del 12 de septiembre |
| `paso_bloqueado` | `1` \| `2` \| null | V4 (movimiento lateral) |
| `nivel_carga` | int | V5 (agotamiento de recursos), ya en uso en `ataques/vector5_carga.py` |
| `es_extension` | bool | resultados fuera del núcleo de 7 configuraciones (p. ej. Excessive Agency) |

Cualquier campo nuevo se avisa al equipo y se documenta aquí y en
`CLAUDE.md` en el mismo commit.

### Serialización de `mecanismos_activos` en CSV

En JSONL, `mecanismos_activos` es una lista nativa (`["filtrado"]`). El CSV
no tiene tipo lista, así que en `resultados_template.csv` esa columna se
escribe como los nombres canónicos **separados por `;`** (p. ej.
`"filtrado;clasificacion"`), y vacía (`""`) cuando no hay ningún mecanismo
activo (`C0`). `analisis/consolidar.py` deberá hacer `str.split(";")` al
leer esta columna para tratarla igual que la lista del JSONL.

### Quién escribe el log

El log lo escribe **el endpoint `/chat`**, nunca las funciones de
`mecanismos.py`. Los mecanismos deciden (retornan bloqueo sí/no); el
endpoint es el único que sabe la latencia total, la configuración vigente y
el resultado final, así que es el único que arma el evento y lo serializa
con `json.dumps(evento, ensure_ascii=False)` + salto de línea.

## 6. Estado actual de la implementación (a la fecha de este documento)

- `proxy/main.py`: **los 5 mecanismos ya están cableados y funcionales.**
  Los mecanismos que pueden bloquear se recorren como una lista ordenada
  (`_CADENA_MECANISMOS`): `("filtrado", …)`, `("clasificacion", …)` y
  `("minimo_privilegio", …)`. `_ejecutar_cadena()` la recorre en entrada y
  en salida, salta los pasos con bandera en `false` y corta al primer
  bloqueo. La delimitación **no** está en esa lista (no bloquea): se
  aplica aparte en `_preparar_prompt()`, sobre el texto que salió de la
  cadena de entrada, justo antes de llamar a Ollama — así la clasificación
  nunca ve el texto ya envuelto en delimitadores (ver
  `CONFLICTOS_RESUELTOS.md`). Mínimo privilegio solo actúa en
  `direccion="entrada"` (no tiene análogo de salida, ver docstring de
  `validar_privilegio()`): en `"salida"` su paso siempre retorna sin
  bloquear. **Aprobación humana tampoco vive en `_CADENA_MECANISMOS`**
  (ver sección 3, paso 5, y el comentario junto a `_CADENA_MECANISMOS` en
  el código): `_gestionar_aprobacion_humana()` intercepta el resultado de
  la cadena de entrada (o corre antes, si el rate limit ya se excedió) y lo
  convierte en "encolar" (`429`) en vez de "rechazar" (`400`) cuando
  `aprobacion_humana` está activo. El endpoint escribe el log JSONL de la
  sección 5 en cada petición; añade `latencia_clasificador_ms` siempre que
  `config["clasificacion"]` sea `true`. **Las 7 configuraciones (`C0`..`C6`)
  ya se ejecutan de punta a punta.**
  - Un bloqueo en **entrada** responde `400` con un detalle genérico (o
    `429` si fue `aprobacion_humana` quien intervino) y no llega a
    consultar el modelo principal (ahorro de cómputo). Un bloqueo en
    **salida** responde `200` pero con el contenido del modelo sustituido:
    `filtrar()` redacta la credencial en su sitio; la clasificación, que solo
    devuelve un `bool`, reemplaza toda la respuesta por un aviso genérico
    (`_CONTENIDO_RETENIDO`). Mismo patrón en ambos: la salida cruda del
    modelo nunca sale al cliente.
  - **Hallazgo de esta semana:** `_registrar_evento()` abría/escribía/cerraba
    `eventos.jsonl` sin ningún lock desde que existe (semana de `filtrado`).
    Nunca antes había habido un test que disparara peticiones realmente
    concurrentes contra el mismo proceso; el primer test de ráfaga del
    mecanismo 5 lo hizo y expuso que se podían **perder eventos completos
    del log** bajo concurrencia real (no solo del rate limiter: cualquier
    ráfaga contra `/chat`, con cualquier mecanismo activo, corría el mismo
    riesgo). Corregido con un `threading.Lock` (`_registro_lock`) alrededor
    de la escritura — ver `docs/FUENTE_DE_VERDAD.md`, sección 9.
- `proxy/mecanismos.py`: las 5 funciones tienen lógica real. `filtrar()`
  bloquea en entrada por patrones de prompt injection y redacta
  credenciales canario en salida. `delimitar()` envuelve la entrada del
  usuario entre delimitadores textuales explícitos (spotlighting,
  arXiv:2403.14720); nunca bloquea, solo reestructura. Desde el
  2026-09-18 cada marcador lleva un token aleatorio distinto por petición
  (no es sesión: el proxy no tiene ese concepto), para que un atacante no
  pueda fabricar de antemano un cierre falso — `delimitar()` ya no es pura
  en el sentido estricto de "mismos argumentos, mismo string", solo
  determinista en su estructura.
  `clasificar()` usa un modelo distinto por dirección desde el 2026-09-18:
  en **entrada**, Llama Prompt Guard 2 (86M, Meta) vía Hugging Face —no vía
  Ollama—, cargado una sola vez de forma perezosa (`_obtener_pipeline_
  prompt_guard()`, protegido con lock) y evaluado con
  `_predecir_prompt_guard()`; en **salida**, sigue llamando a
  `llama-guard3:1b` en Ollama (`POST /api/chat`, rol `assistant`) e
  interpretando `safe`/`unsafe`. Falla cerrado (`True`) en las dos
  direcciones ante cualquier error — timeout/red/respuesta malformada en
  salida, o fallo de carga/inferencia (incluido `HF_TOKEN` ausente) en
  entrada — es la única probabilística, y la única con dos backends
  distintos.
  `validar_privilegio()` es determinista (regex de dominio,
  `PATRON_CREDENCIAL_GENERICO`): detecta si el texto dirigido a
  `modelo_destino` trae una credencial cuyo prefijo pertenece a otro modelo
  (`PREFIJOS_POR_MODELO`), señal de movimiento lateral (V4 paso 2). Un
  modelo destino desconocido se trata de forma conservadora: toda
  credencial encontrada se considera ajena. `enviar_a_revision()` delega en
  `proxy/cola.py` (`cola.cola_global.encolar()`); es la única de las 5 con
  un efecto secundario intencional (documentado en su propio docstring y en
  el contrato de `CLAUDE.md`): mantener la cola de revisión humana, no el
  log del experimento. También vive aquí `cargar_config()`, que es
  funcional.
- `proxy/cola.py`: `ColaRevision` — cola FIFO de peticiones pendientes (con
  `id` estable para que la interfaz de revisión pueda retirarlas sin
  ambigüedad) y rate limiter por cliente (ventana deslizante de
  `VENTANA_LIMITE_S` segundos). Ambas operaciones protegidas con el mismo
  `threading.Lock`. `cola_global` es la instancia compartida por todo el
  proceso; los tests crean instancias propias para no compartir estado.
  Expone `listar()` y `retirar(id)` además de `encolar()`/`excede_limite()`
  — el formato del diccionario que representa una petición pendiente (`id`,
  `encolado_en`, `modelo`, `mensaje`, `vector_probado`, `cliente`,
  `motivo`) se define una sola vez aquí; los endpoints de `/revision`
  (abajo) lo consumen tal cual, sin redefinirlo.
- `proxy/main.py`, interfaz de revisión humana (mecanismo 5, HTTP): `GET
  /revision` lista lo pendiente (`cola.cola_global.listar()`, la más
  antigua primero, con su `encolado_en`). `POST /revision/{id}/rechazar`
  retira la petición y la descarta sin tocar Ollama. `POST
  /revision/{id}/aprobar` la retira y corre `_completar_peticion()` —el
  resto del pipeline que comparte con `/chat` (delimitación → Ollama →
  cadena de SALIDA)—, **sin volver a evaluar la cadena de bloqueo de
  entrada**: esa es justamente la decisión que el humano anula. Ambos
  devuelven `404` explícito (no un error genérico) si el `id` ya no está en
  la cola (`_obtener_pendiente_o_404()`; `ColaRevision.retirar()` ya lanza
  `KeyError` para ese caso). Ambos escriben además un evento de log propio
  —aparte del que `/chat` ya escribió al encolar (JSONL es append-only,
  nunca se edita una fila existente)— con el campo extendido
  `tiempo_revision_humana_ms` (`_ms_transcurridos_desde()`: milisegundos
  entre `encolado_en` y el momento de la decisión). En el evento de
  aprobación, `latencia_ms` es el tiempo **total** (espera en cola +
  tiempo de completar la petición), y `tiempo_revision_humana_ms` es solo
  la parte de espera — la métrica de costo que necesita Fiquitiva, sin
  reemplazar el total (invariante 5 del esquema de log). `GET /revision/ui`
  sirve una página HTML mínima (JS vanilla, sin plantillas ni dependencias
  nuevas) sobre esos mismos 3 endpoints, para no depender de `curl` a mano
  durante las pruebas del equipo.
- `config.yaml`: las 5 banderas existen; el estado por defecto del repo es
  todas en `false` (`C0`).
- `proxy/Dockerfile` y `docker-compose.yml`: el build context es la raíz
  del repo (antes solo copiaba `main.py`, sin `mecanismos.py`, y no podía
  arrancar con lógica real). `config.yaml` se monta como volumen de solo
  lectura para poder cambiar de configuración sin rebuild.
- `ataques/vector5_carga.py` ya emite eventos JSONL con el esquema de 8
  campos + `nivel_carga`, útil como referencia de implementación del logger.
- `ollama/init.sh` ahora también descarga `MODELO_CLASIFICADOR`
  (`llama-guard3:1b` por defecto, `.env.example`) junto con `BASE_MODEL`.
- Los 5 mecanismos están completos de punta a punta, incluida la interfaz
  HTTP de aprobación/rechazo humano descrita arriba (`GET /revision`,
  `POST /revision/{id}/aprobar`, `POST /revision/{id}/rechazar`, `GET
  /revision/ui`). No queda pendiente ningún mecanismo del núcleo del
  experimento.

## 7. Documentos relacionados

- `CLAUDE.md` — contrato completo del proyecto: reglas no negociables,
  firmas estables, convenciones de código y reparto del equipo.
- `docs/FUENTE_DE_VERDAD.md` — valores canónicos (nombres, versiones, cifras
  consolidadas) cuando un dato se cita en más de un lugar.
- `ataques/variantes_ataque.md` — definición exacta de cada ID de vector
  (`V1-A`..`V5-D`) que alimenta el campo `vector_probado`.
- `resultados/resultados_template.csv` — plantilla de captura manual con las
  mismas columnas que este esquema, para pruebas ejecutadas fuera de un
  script (V1–V4).

## 8. Fuentes

- Formato de fecha/hora ISO 8601 (estándar seguido en el campo `timestamp`):
  <https://es.wikipedia.org/wiki/ISO_8601>
- JSON Lines (un objeto JSON por línea, formato del log de la sección 5):
  <https://jsonlines.org/>

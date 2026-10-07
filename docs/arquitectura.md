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
- **Extensiones opcionales (apagadas por defecto, no tocan el núcleo):**
  - `proxy/herramientas.py` + modelo `rrhh-agente`
    (`ollama/modelfiles/Modelfile.rrhh_agente.template`): function calling
    nativo de Ollama con dos herramientas **SIMULADAS** (`enviar_correo`,
    `consultar_base_datos`: solo escriben en el log, ningún efecto real).
    Solo se activan para los modelos listados en `MODELOS_CON_HERRAMIENTAS`.
    El modelo únicamente *solicita* una herramienta;
    `_gestionar_llamadas_a_herramientas()` (llamada desde
    `_completar_peticion()`) la encola en la cola de revisión humana si
    `aprobacion_humana` está activa y la deniega si no — nunca se ejecuta
    sin pasar por la cola. `POST /revision/{id}/aprobar` ejecuta entonces la
    versión simulada (`_aprobar_herramienta()`). Es un modelo distinto de
    `rrhh` a propósito: cambiar el system prompt de `rrhh` invalidaría la
    comparación entre las 7 configuraciones ya medidas.
  - `proxy/notificaciones.py`: cada vez que aprobación humana coloca una
    petición en la cola (límite de tasa, bloqueo de otro mecanismo o
    solicitud de herramienta), `_notificar_en_revision()` avisa por los
    canales configurados por variables de entorno (webhook genérico, Slack,
    correo SMTP, WhatsApp vía Twilio). **No bloqueante**: hilo daemon, un
    `try/except` y un timeout por canal; un fallo solo pierde la
    notificación. El mensaje lleva mecanismo/motivo, vector, configuración y
    timestamp, nunca el texto de la petición.
  - `proxy/memoria_decisiones.py` — **memoria de decisiones humanas**
    (`MEMORIA_RECHAZOS=1`; guía en `docs/MEMORIA_DE_DECISIONES.md`): cuando un
    revisor **rechaza** una petición que filtrado, clasificación o mínimo
    privilegio retuvo, `rechazar_revision()` guarda la huella SHA-256 del par
    (modelo, mensaje normalizado) y `_consultar_memoria()` rechaza solo el mismo
    mensaje al principio de `/chat` (400 inmediato, sin cola, sin aviso, sin llegar
    al modelo). Solo rechazos (nunca aprobaciones), por modelo, coincidencia exacta:
    no frena paráfrasis. Es un **paquete con puertos y adaptadores**
    (`proxy/memoria_decisiones/`: dominio, puerto `AlmacenMemoria`, servicio, registro,
    `almacenes/` y composición; cada capa depende solo de la de abajo y solo la
    composición lee el entorno). **Persistente** con almacén intercambiable (JSON Lines
    o SQLite en `./memoria`, carpeta del host); la base de datos de una empresa se
    conecta con `MEMORIA_RECHAZOS_ADAPTADORES`, sin editar IronVeil. Visible y
    revocable desde la pestaña *Memoria* de la consola. Los resultados de C0-C6 se midieron **sin** ella; sus
    eventos llevan `origen_decision: "memoria"`, `latencia_memoria_us` y
    `es_extension: true`, y se atribuyen a `aprobacion_humana`.
  - `proxy/modelos_protegidos.py` — **modelo protegido remoto**
    (`MODELOS_REMOTOS`; `docs/MODELO_PROTEGIDO_REMOTO.md`): el proxy puede proteger un
    modelo servido por otra API (`openai`, `anthropic`) en vez de Ollama.
    `_llamar_modelo_protegido()` despacha y el adaptador devuelve la forma de Ollama,
    así que los 5 mecanismos no cambian. Un tercero exige
    `MODELO_PROTEGIDO_PERMITIR_TERCEROS=1`; sus eventos llevan `es_extension`.
  - `proxy/backends_entrada.py` + `proxy/adaptador_clasificador.py` — **clasificador de
    entrada intercambiable** (`CLASIFICADOR_ENTRADA_BACKEND`;
    `docs/CAMBIAR_MODELO_CLASIFICADOR.md`): Prompt Guard local por defecto, o `http`,
    `ollama`, `openai`, `anthropic`, `jev`. El adaptador traduce el veredicto de cada
    modelo a «malicioso / no» (etiqueta desconocida = malicioso) y cada evento deja
    `clasificador_entrada` / `clasificador_salida` con backend, modelo, destino y
    estado (separa una detección real de una caída del servicio). `clasificar()` no
    cambia de firma.
  - `proxy/siem/` — exportación de cada evento a **cualquier SIEM**, como paquete con
    puertos y adaptadores (`docs/SIEM.md`). Cada capa depende solo de la de abajo:
    composición (lee el entorno, único lugar) → servicio `ExportadorSIEM` (entrega a todos los
    destinos, aislados entre sí, sin poder lanzar) → registro (`[formato@]esquema://destino`) →
    adaptadores. Dos puertos de un método cada uno: `FormateadorSIEM` (json para Wazuh/Splunk/Sentinel,
    cef, leef, ecs) y `ConectorSIEM` (archivo, syslog UDP/TCP/TLS, https, Splunk HEC, Elastic/OpenSearch,
    Azure Monitor, CloudWatch con firma SigV4 propia). Formato y transporte se combinan libremente.
    Los transportes de red se entregan en un hilo aparte (`ConectorAsincrono`: cola acotada,
    reintentos, descarta lo más nuevo si el SIEM lleva rato caído): **un SIEM lento o caído nunca
    frena ni rompe `/chat`**. `exportar_a_siem(evento, formato) -> str` sigue siendo una función
    pura (campos con su nombre, listas aplanadas, `null` omitido porque Wazuh lo vuelve la cadena
    `"null"`, `integration: "ironveil"`). Reglas de Wazuh en `docs/siem/wazuh/ironveil_rules.xml`
    y lote por lotes en `analisis/exportar_lote_siem.py`.
    **Cableado a `/chat`** (opt-in): `_registrar_evento()` escribe primero el dataset
    (`eventos.jsonl`, intacto) y después llama a `siem.exportar_evento()`, que solo actúa si hay
    `SIEM_DESTINOS` (o la forma histórica `SIEM_ARCHIVO_WAZUH`). Los eventos de `/revision/*`
    también se exportan, porque pasan por la misma `_registrar_evento()`. Otro SIEM se conecta con
    un módulo propio listado en `SIEM_ADAPTADORES`, sin editar IronVeil.
- `proxy/normalizacion/` — **extensión opcional** (apagada salvo `NORMALIZACION_ENTRADA=1`): cubre
  los ataques que se esconden (Base64, hexadecimal, ROT13, caracteres Unicode invisibles) que ni el
  filtro ni Prompt Guard ven. Actúa **antes** de la cadena: quita los invisibles (el modelo recibe
  el texto limpio), decodifica los tramos hasta dos capas y, si lo decodificado parece lenguaje,
  hace una segunda pasada con los **mismos** mecanismos (`_cadena_de_entrada()` en `main.py`; el
  primero que bloquea gana). No es un mecanismo nuevo: solo muestra a los existentes lo que estaba
  escondido, así que sin mecanismos activos no bloquea nada. Paquete con puertos y adaptadores
  (dominio → puerto `Decodificador` → servicio → registro → `decodificadores/` → composición, la
  única que lee el entorno); otra codificación se agrega con `NORMALIZACION_ADAPTADORES`. Con ella
  encendida los eventos llevan `normalizacion` y `es_extension`, y C0–C6 dejan de ser las del
  experimento. Medido sin LLM: 0/6 → 6/6 por codificación y 0/18 falsos positivos
  (`analisis/medir_normalizacion.py`; muestra pequeña). Guía: `docs/NORMALIZACION_DE_ENTRADA.md`.
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
  reemplazar el total (invariante 5 del esquema de log).
- `proxy/revision_panel.py` + `proxy/static/` (consola de revisión humana,
  extensión de la interfaz de arriba): `GET /revision/ui` sirve una consola
  (HTML/CSS/JS vanilla, sin dependencias nuevas, sin recursos externos) que
  consume `GET /revision/panel` (la cola **analizada**: mecanismo que la
  retuvo y por qué, fragmentos que coinciden con patrones conocidos, señales
  y una lectura **orientativa** falso positivo / ataque; para herramientas
  simuladas, las reglas de `rrhh-agente`) y `GET /revision/historial`
  (decisiones: quién, cuándo, cuánto tardó; **nunca el texto**). El texto de
  una petición puede ser un ataque: viaja como JSON y la página lo pinta con
  `textContent`, sin `innerHTML` (lo verifica un test). El logo es
  `proxy/static/logo.svg`, reemplazable.
- `proxy/demo_chat.py` + `proxy/static/demo.*` (pantalla de chat de la demo,
  **opt-in** con `IRONVEIL_DEMO=1`, apagada por defecto): `GET /demo` sirve una
  pantalla tipo chat que llama a `POST /chat` y muestra solo la respuesta (o un
  aviso genérico si hubo bloqueo o revisión). No agrega endpoints de datos ni
  toca el pipeline: lo que hizo cada mecanismo no se muestra en pantalla y queda
  en el log JSONL, los logs del proxy y el SIEM, para quien opera el sistema.
  Con login activo exige sesión. Un test impide que la pantalla nombre
  mecanismos o llame a otro endpoint que `/chat` (y, si el mensaje queda en
  revisión, `GET /chat/revision/{id}`, abajo).
- **Espera de la decisión humana** (`proxy/espera_revision.py`, `ResultadosRevision`
  en `proxy/cola.py`): al encolar, `/chat` sigue respondiendo 429 de inmediato
  (**el cuerpo no cambia**) pero agrega la cabecera `X-Revision-Id` con el id del
  turno (uuid4, 128 bits: es la llave); solo si la petición quedó de verdad en
  la cola. Antes, lo que decidiera el revisor nunca le llegaba a quien escribió
  (`aprobar` devuelve la respuesta al revisor). Ahora la consola, al decidir,
  deja el resultado (`aprobada` con la respuesta ya filtrada por la cadena de
  salida, `rechazada` o `fallida`) en un registro en memoria con caducidad de
  30 min y tope de 500. `GET /chat/revision/{id}?espera=25` dice el estado y
  **espera hasta 25 s a que cambie** (long polling; se despierta al instante, no
  sondea). Con `desde=pendiente|en_curso` vuelve en cuanto el estado sea otro: así
  el chat se entera de que ya se aprobó y se está generando la respuesta
  (`en_curso`) y puede mostrar «Preparando la respuesta…» y bloquear el envío.
  Estados: `pendiente`, `en_curso`, `aprobada`, `rechazada`, `fallida`,
  `desconocida`. Sin login, como `/chat` (el id es la llave); nunca devuelve el
  texto de la petición; tope de 100 esperas abiertas. Quien decide marca
  `en_curso` **antes** de sacar la petición de la cola, así quien espera nunca
  ve un hueco entre `pendiente` y el resultado.
- **Costo por pieza** (`_MetricasCadena.tiempos_ns` en `proxy/main.py`): cada
  mecanismo que corre, y el modelo, se cronometran con `perf_counter_ns` y salen
  en el `eventos.jsonl` como `latencia_<pieza>_us` (microsegundos; ver
  `CLAUDE.md`, sección 4). Restar `latencia_modelo_us` a `latencia_ms` da el
  costo propio del proxy sin compararse contra C0. Solo se registra lo que se
  ejecutó; los 8 campos base no cambian. `ataques/medir_costo_mecanismos.py`
  genera la carga (mensajes legítimos de tres tamaños y algunos que algún
  mecanismo retiene; el calentamiento lleva `vector_probado="CALENTAMIENTO"`) y
  `analisis/costo_por_mecanismo.py` resume por configuración.
- `proxy/auth.py` (login de la consola): **opt-in** — con `REVISION_USUARIOS`
  vacía todo se comporta como antes (scripts y tests del experimento
  intactos); con cuentas definidas, `GET /revision`, `/revision/panel`,
  `/revision/historial` y `POST /revision/{id}/aprobar|rechazar` exigen
  sesión (cookie `HttpOnly` + `SameSite=Strict` + `Secure`, token aleatorio con
  `secrets`, expiración por inactividad) y las decisiones exigen además rol
  `revisor` y la cabecera `X-CSRF-Token`. Claves con scrypt (`python -m
  proxy.auth USUARIO`), límite de intentos por usuario e IP, y la verificación
  cuesta lo mismo exista o no el usuario. `ProveedorAutenticacion` (patrón
  Adapter, como `proxy/siem/`) es el punto para conectar el LDAP, la base de datos
  de usuarios o el SSO de la organización sin tocar sesiones ni CSRF. Las
  sesiones viven en memoria del proceso. `python -m proxy.auth --demo` crea la
  cuenta `admin` (rol `revisor`) con una **clave aleatoria por máquina**: escribe
  solo el hash en el `.env` y la clave en `credenciales-demo.local.txt` (ignorado
  por Git); no hay ninguna clave por defecto en el código.
- **Consola en tiempo real** (`GET /revision/eventos`, SSE, en `revision_panel.py`):
  la cola (`ColaRevision.suscribir()/cancelar()`) avisa de cada cambio —encolar o
  retirar— a quien esté escuchando; el generador `flujo_eventos()` lo convierte en
  eventos `cambio`, funde ráfagas en un solo aviso y manda un latido cada 15 s.
  **El canal no lleva datos** (solo «cambió»): la consola vuelve a pedir
  `/revision/panel` por la vía autenticada de siempre, así que el texto de una
  petición nunca viaja por él. Exige sesión; cada latido comprueba que la sesión
  siga vigente **sin renovarla** (una pestaña abierta no mantiene viva una sesión
  inactiva) y, si venció, manda `sesion` y cierra. Tope de 50 consolas
  conectadas (`lleno` → la consola cae al sondeo). El cliente solo sondea como
  respaldo (cada 3 s si el canal está caído, cada 30 s aunque esté vivo).
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

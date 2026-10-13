# CLAUDE.md — IronVeil

> ## 📌 ¿Vas a escribir el paper o a sacar tablas y números?
> **Lee primero [`docs/GUIA_PARA_EL_PAPER.md`](docs/GUIA_PARA_EL_PAPER.md).** Dice dónde está cada cifra, cuál es la
> definitiva, qué comando regenera cada tabla y qué **no** se puede afirmar (por ejemplo, no hay cifra oficial de idiomas
> de Jev). Si eres un asistente de IA: no inventes números; cada cifra sale de `analisis/` o `resultados/`, y siempre
> con su intervalo de confianza.

Guía operativa para asistentes de IA que trabajen en este repositorio. Léela completa antes de tocar código.

---

## 1. Qué es este proyecto

IronVeil es un **framework académico de defensa en profundidad para LLMs autoalojados** (Ollama) expuestos accidentalmente en internet. Es un trabajo de seminario universitario, no un producto.

El experimento central: un proxy FastAPI se sienta entre el cliente y un backend Ollama con dos modelos (`soporte` y `rrhh`), cada uno con un secreto ficticio (canario) en su system prompt. Cinco mecanismos defensivos se activan/desactivan por bandera, y se mide cuánto reducen la Tasa de Éxito de Ataque (ASR) frente a cinco vectores de ataque.

**Pregunta de investigación:** ¿qué combinación de mecanismos ofrece la mejor relación protección / utilidad / costo?

### Los 5 mecanismos

| # | Nombre | Bandera en `config.yaml` | Naturaleza |
|---|--------|--------------------------|-----------|
| 1 | Filtrado | `filtrado` | Determinista (patrones/regex) |
| 2 | Delimitación (spotlighting) | `delimitacion` | Determinista (reestructura prompt) |
| 3 | Clasificación (Llama Guard) | `clasificacion` | Probabilístico (modelo) |
| 4 | Mínimo privilegio | `minimo_privilegio` | Determinista (regex de dominio) |
| 5 | Aprobación humana + rate limit | `aprobacion_humana` | Humano en el loop |

### Los 5 vectores de ataque

V1 reconocimiento · V2 extracción de system prompt · V3 prompt injection · V4 movimiento lateral · V5 agotamiento de recursos.

### Las 7 configuraciones

`C0` baseline (todo en `false`) · `C1`–`C5` un solo mecanismo activo · `C6` los cinco activos.

**El mismo código debe ejecutar las 7 configuraciones cambiando únicamente `config.yaml`.** Si una propuesta de implementación requiere ramas de código distintas por configuración, está mal: rehazla.

---

## 2. Reglas no negociables

1. **Laboratorio aislado.** Todo ataque, prueba de carga o escaneo se ejecuta **exclusivamente** contra el stack propio del equipo en localhost/Docker. Nunca contra un servidor Ollama de terceros, ni "solo para probar". Si un cambio propuesto apunta a un host que no es del laboratorio, detente y avisa.
2. **Las credenciales son ficticias, pero se tratan como reales.** `SPT-DEMO-8841` (soporte) y `RRHH-DEMO-2291` (rrhh) viven en `.env` / Modelfiles, nunca hardcodeadas en la lógica del proxy ni en los tests. Se manipulan como constantes o variables de entorno.
3. **Ollama nunca se expone al host.** Solo el proxy publica puerto (`8000`). `11434` queda dentro de la red interna de Docker. La única excepción documentada es C0 si el experimento lo exige, y debe quedar anotada.
4. **Los datos crudos no se editan a mano.** `resultados_template.csv` y los logs de `/resultados/` son evidencia. Toda transformación pasa por script reproducible. Ninguna fila se borra: se mueve a `descartados.csv` con razón documentada.
5. **No se fuerzan resultados hacia la hipótesis.** Si un mecanismo funciona peor (o mejor) de lo predicho, se reporta tal cual. Que C6 no llegue a 0% de ASR es un resultado esperado por la literatura, no un fracaso.
6. **Herramientas simuladas siempre marcadas.** En la extensión de Excessive Agency, `enviar_correo()` y `consultar_base_datos()` no tienen efecto real y el código debe decirlo de forma inequívoca.

---

## 3. Arquitectura

```
Cliente
  │  POST /chat  {modelo, mensaje}
  ▼
┌─────────────────────────────────────────────┐
│ Proxy FastAPI (:8000)                       │
│                                             │
│  cargar_config() ──► banderas               │
│                                             │
│  Cadena de mecanismos que PUEDEN BLOQUEAR   │
│  (orden fijo, en bucle; se recorre en       │
│  ENTRADA y otra vez en SALIDA). Numeros =   │
│  mecanismo # de la sección 1, no posición   │
│  en la lista (el 2 y el 5 no están aquí):   │
│   1. filtrado                               │
│   3. clasificación                          │
│   4. mínimo privilegio  (solo entrada)      │
│                                             │
│  Mecanismo 5 (aprobación humana + rate      │
│  limit) NO vive en la lista de arriba:      │
│  INTERCEPTA su resultado (o corre antes, si │
│  el rate limit ya se excedió) y lo convierte│
│  en "encolar" (429) en vez de "rechazar"    │
│  (400) cuando está activo.                  │
│                                             │
│    ¿bloqueado en entrada, y no encolado?    │
│         ▼ no                                │
│   delimitación (construye prompt final,     │
│   no bloquea)                               │
│         ▼                                   │
│      llamada a Ollama                       │
│         ▼                                   │
│   filtrado (salida) → clasificación (salida)│
│                                             │
│  logging JSONL de cada evento               │
└─────────────────────────────────────────────┘
  │ red interna Docker
  ▼
Ollama (:11434) — modelos "soporte", "rrhh", llama-guard3
```

### Reglas de la cadena

- **Orden fijo conceptual de los 5 mecanismos** (de ahí salen los nombres `C1`..`C5` de la sección 1): filtrado → delimitación → clasificación → mínimo privilegio → aprobación humana. **No es una secuencia de ejecución literal de una sola lista.** Delimitación no bloquea, así que no vive en la cadena de bloqueo, y se aplica aparte, justo antes de llamar a Ollama, sobre el texto que sobrevivió a esa cadena. Mínimo privilegio, además, solo actúa en dirección "entrada" (no tiene análogo de salida). **Aprobación humana tampoco vive en la cadena de bloqueo** — a diferencia de los otros 3 (filtrado, clasificación, mínimo privilegio), no es un paso que se salta o se ejecuta según su bandera: INTERCEPTA el resultado de esa cadena. Con "primer bloqueo gana", un cuarto paso ahí nunca se ejecutaría si otro ya bloqueó antes — justo el caso que aprobación humana necesita interceptar para poder encolarlo en vez de dejarlo como rechazo automático (ver `proxy/main.py`, `_gestionar_aprobacion_humana()` y el comentario junto a `_CADENA_MECANISMOS`). Justificación del orden entre los que sí bloquean: filtrado va primero por ser el más barato (regex local, coste ~0), para descartar lo obvio sin gastar nada; a partir de ahí el orden es el fijo conceptual de la sección 1, no un reordenamiento continuo por costo — clasificación (cara, modelo) va antes que mínimo privilegio (barata, regex) porque así lo fija el orden global, no porque sea más cara.
- **Primer bloqueo gana.** Cuando un mecanismo bloquea, la cadena se corta y no se evalúa el resto. Esto se refleja en el campo `mecanismo_que_bloqueo` del log.
- **La cadena se implementa como una lista de pasos recorrida en bucle**, no como `if` anidados. El endpoint `/chat` no debe superar ~40 líneas; el resto va en funciones auxiliares.
- **La clasificación evalúa el texto original del usuario**, no el texto ya envuelto por la delimitación. (Decisión de integración; ver `CONFLICTOS_RESUELTOS.md`.)

---

## 4. Contratos estables

Estas firmas y este esquema son **compartidos entre cuatro personas**. Cambiarlos rompe trabajo ajeno. Si hay que cambiar algo, se avisa al equipo primero y se actualiza este archivo en el mismo commit.

### `proxy/mecanismos.py`

```python
def filtrar(texto: str, direccion: str) -> tuple[str, bool]: ...
# direccion: "entrada" | "salida"
# retorna (texto_posiblemente_redactado, debe_bloquearse)

def delimitar(system_prompt: str, entrada_usuario: str) -> str: ...
# determinista en estructura, sin red, sin estado compartido entre
# peticiones; el texto exacto YA NO es puro a propósito (token aleatorio
# por petición en los marcadores, desde 2026-09-18 — ver FUENTE_DE_VERDAD.md)

def clasificar(texto: str, direccion: str) -> bool: ...
# True = unsafe/malicious. Timeout/error/fallo de carga ⇒ True (fail
# closed, nunca fail open). Desde 2026-09-18, modelo distinto por
# direccion: entrada = Prompt Guard (Hugging Face), salida = Llama Guard
# (Ollama, como antes) — ver FUENTE_DE_VERDAD.md, seccion 4

def validar_privilegio(modelo_destino: str, texto_entrada: str) -> bool: ...
# True = credencial de otro dominio detectada ⇒ rechazar

def enviar_a_revision(peticion: dict) -> bool: ...
# encola y devuelve señal de "pendiente"
```

> Nota: el stub original de `filtrar()` devolvía `str`. La firma vigente es la de arriba (`tuple[str, bool]`).

**Los mecanismos no escriben el log.** Deciden; el endpoint registra. Así siguen siendo testeables de forma aislada.

### `config.yaml`

```yaml
filtrado: false
delimitacion: false
clasificacion: false
minimo_privilegio: false
aprobacion_humana: false
```

`cargar_config()` usa `yaml.safe_load()` (nunca `yaml.load()`) y **falla ruidosamente** si falta cualquiera de las 5 claves o si el archivo no existe. Nada de defaults silenciosos.

### Esquema de log (JSON Lines, un objeto por línea)

```json
{
  "timestamp": "2026-09-05T14:32:11-05:00",
  "configuracion": "C1",
  "mecanismos_activos": ["filtrado"],
  "vector_probado": "V3-A",
  "modelo_destino": "soporte",
  "resultado": "bloqueado",
  "mecanismo_que_bloqueo": "filtrado",
  "latencia_ms": 812
}
```

`resultado` ∈ `bloqueado` | `exitoso_para_atacante` | `permitido_normal`. `mecanismo_que_bloqueo` es `null` si no hubo bloqueo.

Campos adicionales acordados sobre la marcha (latencia propia del clasificador, tiempo humano de revisión, tipo de variante `original`/`nueva`, paso 1/2 en V4) se agregan **sin renombrar los 8 campos base**.

**Costo por pieza (2026-10-05).** El `eventos.jsonl` del proxy (no el CSV de resultados) lleva, para cada pieza que **se ejecutó** en esa petición, `latencia_<pieza>_us` en **microsegundos** (entero): `filtrado`, `delimitacion`, `clasificacion`, `minimo_privilegio`, `limite` y `aprobacion_humana` (la comprobación de si hay algo que retener), más `modelo` (el tiempo del modelo protegido). Una pieza apagada, o que no corrió porque la cadena se cortó antes, **no deja campo** (no se confunde «no corrió» con «fue rápido»). `latencia_ms - latencia_modelo_us/1000` es el costo propio del proxy, sin compararse contra C0. `latencia_clasificador_ms` se conserva igual. Desde 2026-10-05 la clasificación también se desglosa en `latencia_clasificacion_entrada_us` (Prompt Guard) y `latencia_clasificacion_salida_us` (Llama Guard), ya contenidas en `latencia_clasificacion_us` (no sumarlas dos veces). Desde 2026-10-05 el evento también lleva `clasificador_entrada` y `clasificador_salida` (solo las direcciones que se clasificaron): un objeto con el mismo esquema para todos los backends (`backend`, `modelo`, `destino` = `local`/`propio`/`tercero`, `estado` = `ok` o el motivo del fallo cerrado, y si aplican `umbral`, `puntaje`, `etiqueta`), sin texto del usuario ni claves; separa los bloqueos reales (`estado == "ok"`) de una caída del servicio (ver `docs/CAMBIAR_MODELO_CLASIFICADOR.md`). También `modelo_protegido` (`backend`, `modelo`, `destino`, `estado`: qué modelo respondió; sin texto ni claves) y, si el modelo es remoto (`MODELOS_REMOTOS`), `es_extension: true` (ver `docs/MODELO_PROTEGIDO_REMOTO.md`). Con la memoria de decisiones activa (`MEMORIA_RECHAZOS=1`), un mensaje rechazado antes por un humano se rechaza solo y su evento lleva `origen_decision: "memoria"`, `latencia_memoria_us` y `es_extension: true` (se atribuye a `aprobacion_humana`; ver `docs/MEMORIA_DE_DECISIONES.md`). Con la normalizacion de entrada encendida (`NORMALIZACION_ENTRADA=1`) el evento lleva `normalizacion` (conteos: `invisibles_eliminados`, `decodificaciones`, `variante_inspeccionada`, `bloqueo_en_variante`; nunca texto) y `es_extension: true` (ver `docs/NORMALIZACION_DE_ENTRADA.md`). Se resume con `analisis/costo_por_mecanismo.py`; la carga de medición es `ataques/medir_costo_mecanismos.py`.

---

## 5. Estructura del repositorio

Esta es la estructura **objetivo**. Lo marcado `[ya existe]` está en el repo hoy; el resto es lo que se va creando a medida que avanzan las semanas — no asumas que ya está ahí sin comprobarlo.

```
/proxy/                 main.py (FastAPI) [ya existe], mecanismos.py, cola.py,
                        siem/ (PAQUETE con puertos y adaptadores, cableado a /chat de forma
                        opcional: puertos FormateadorSIEM y ConectorSIEM, servicio, registro,
                        formatos/ json|cef|leef|ecs y transportes/ archivo, syslog UDP/TCP/TLS,
                        https, Splunk, Elastic, Azure Monitor y CloudWatch; los de red se
                        entregan en un hilo aparte; SIEM_DESTINOS elige formato y destino, y
                        SIEM_ADAPTADORES conecta otro SIEM sin editar IronVeil;
                        exportar_a_siem(evento, "json"|"cef"|"leef"|"ecs") sigue siendo una
                        funcion pura; docs/SIEM.md y docs/siem/wazuh/)
                        complementos.py (carga de modulos de terceros que registran adaptadores,
                        compartida por la memoria de decisiones y el SIEM)
                        memoria_decisiones/ (EXTENSION opcional, PAQUETE con puertos y adaptadores:
                        dominio, puerto AlmacenMemoria, servicio, registro, almacenes/ y composicion;
                        recuerda los rechazos de la revision humana y rechaza solo el mismo mensaje;
                        persistente con almacen intercambiable (JSON Lines o SQLite en ./memoria; la
                        base de una empresa se conecta con MEMORIA_RECHAZOS_ADAPTADORES sin editar
                        IronVeil); apagada salvo MEMORIA_RECHAZOS=1; eventos con es_extension;
                        docs/MEMORIA_DE_DECISIONES.md)
                        normalizacion/ (EXTENSION opcional, PAQUETE con puertos y adaptadores:
                        decodifica Base64/hex/ROT13 y quita caracteres invisibles ANTES de la
                        cadena, y los mecanismos revisan tambien lo que estaba escondido;
                        apagada salvo NORMALIZACION_ENTRADA=1, y con ella los eventos llevan
                        normalizacion y es_extension; docs/NORMALIZACION_DE_ENTRADA.md)
                        modelos_protegidos.py (EXTENSION opcional: proteger un modelo servido
                        por otra API, openai/anthropic, en vez de Ollama; devuelve la forma de
                        Ollama, los 5 mecanismos no cambian; terceros apagados salvo
                        MODELO_PROTEGIDO_PERMITIR_TERCEROS=1; eventos con es_extension)
                        backends_entrada.py (clasificador de entrada alternativo: ollama,
                        openai, anthropic y jev; los remotos apagados salvo
                        CLASIFICADOR_PERMITIR_REMOTO=1)
                        adaptador_clasificador.py (traduce el veredicto de cada modelo
                        clasificador a "malicioso / no" y elige el backend de entrada;
                        cambiar de modelo no toca clasificar(); guia en
                        docs/CAMBIAR_MODELO_CLASIFICADOR.md)
                        demo_chat.py (pantalla de chat /demo, solo la cara visible de /chat;
                        opt-in IRONVEIL_DEMO=1; no cambia /chat)
                        espera_revision.py (GET /chat/revision/{id}: quien escribio se
                        entera de la decision humana; /chat solo suma la cabecera
                        X-Revision-Id al 429, su cuerpo no cambia)
                        auth.py + revision_panel.py + static/ (consola de revision humana
                        con login opcional REVISION_USUARIOS y canal en vivo SSE /revision/eventos;
                        logo en static/logo.svg)
                        herramientas.py + notificaciones.py (EXTENSIONES opcionales:
                        herramientas SIMULADAS de rrhh-agente y avisos por webhook/
                        Slack/correo/WhatsApp cuando aprobacion humana encola;
                        apagadas por defecto, ver .env.example)
/ollama/modelfiles/     Modelfile.soporte.template, Modelfile.rrhh.template [ya existen],
                        Modelfile.rrhh_agente.template (extension, herramientas simuladas)
/scripts/               utilidades (seleccionar_config.py: escribe config.yaml para C0..C6)
                        proxy/configuraciones.py (C0..C6 <-> banderas, una sola definicion) y
                        proxy/cli.py (comando `ironveil`: config, serve, auth-demo; pyproject.toml,
                        docs/PUBLICAR_PYPI.md). Autenticacion opcional de /chat con
                        CHAT_REQUIERE_AUTENTICACION=1 (proxy/auth.py, docs/AUTENTICACION.md)
/tests/                 pruebas unitarias y de integración
/ataques/               variantes_ataque.md, vector4_*.py, vector5_*.py, promptfooconfig.yaml,
                        garak_externo/ (EXTENSION: validacion externa con Garak contra una
                        segunda instancia del proxy, via IRONVEIL_CONFIG e IRONVEIL_RESULTADOS,
                        sin tocar el dataset; docs/GARAK.md)
/resultados/            resultados_template.csv, /YYYY-MM-DD/ logs crudos, /graficas/
/analisis/              consolidar.py, validar_dataset.py, análisis en Markdown
                        (resumen_garak.py: resumen de la extension Garak, aparte del nucleo)
                        (extension_agencia_excesiva.py: resumen de la extensión V7; sus
                        filas del CSV llevan es_extension=True y cargar_resultados() las
                        excluye del núcleo)
/.github/workflows/     ci.yml (ruff, black, pytest, paquete), publicar.yml (release + imagen en ghcr.io),
                        pages.yml (sitio en GitHub Pages) y pypi.yml (PyPI con trusted publishing)
/docs/                  arquitectura.md [ya existe], FUENTE_DE_VERDAD.md [ya existe, por rellenar],
                        CONFLICTOS_RESUELTOS.md, LIMPIEZA_DATOS.md, CHECKLIST_ENTREGA.md
/informe/               main.tex, PDF compilado
LICENSE (MIT) · pyproject.toml · docker-compose.yml [ya existe] · config.yaml · .env.example [ya existe] · README.md [ya existe]
```

Nada suelto en la raíz salvo lo listado arriba y los archivos de comunidad de GitHub (`LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`).

---

## 6. Comandos

```bash
docker compose up                 # levanta Ollama + proxy
docker compose up --build         # tras cambiar dependencias

curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"modelo":"soporte","mensaje":"hola"}'

pytest                            # suite completa, desde la raíz
pytest tests/test_mecanismos.py -k filtrar
ruff check . && black .           # linting y formato
python analisis/consolidar.py     # tablas de ASR
python analisis/validar_dataset.py
```

---

## 7. Convenciones de código

- Python 3.11+. **Type hints en todas las funciones**, sin excepción.
- Docstrings estilo PEP 257 en toda función pública: qué recibe, qué devuelve, qué hace.
- `logging` estructurado del stdlib (o structlog). **Nunca `print()`** fuera de scripts de demo.
- Nada de `pass` silencioso: o comportamiento neutro explícito y documentado, o `raise NotImplementedError("mensaje descriptivo")`.
- Estado compartido entre peticiones concurrentes (la cola de revisión) va protegido con lock. El V5 justamente dispara ráfagas simultáneas: las condiciones de carrera aquí son bugs reales, no teóricos.
- Constantes configurables (límite de peticiones/minuto, timeout del clasificador, patrón de credencial) definidas **una sola vez**, arriba del módulo o en `.env`.

### Testing

- Cada mecanismo nuevo llega con sus pruebas unitarias en el mismo commit.
- El clasificador se testea **con mocks** de la respuesta de Ollama. La suite debe correr sin el stack levantado.
- Cobertura mínima por mecanismo: caso que bloquea, caso legítimo que **no** debe bloquearse (falso positivo), caso de error/timeout.
- Antes de cualquier trabajo de integración, correr `pytest` completo. Un fallo tras combinar mecanismos es información valiosa sobre un conflicto real, no ruido a silenciar.

### Git

- Commits atómicos con prefijo: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`.
- Ramas para trabajo exploratorio sobre código compartido; merge solo con las pruebas en verde.
- Nada de `--force` sobre `main`.

### Seguridad del código (SonarCloud en A)

Aplica al código de infraestructura del proyecto (`proxy/`, `ataques/`,
`analisis/`) — **no** a los canarios (`SPT-DEMO-*`, `RRHH-DEMO-*`) ni a
los payloads de ataque en `ataques/variantes_ataque.md`: esos son el
objeto de estudio del experimento, no una vulnerabilidad del código, y
`.env`/`.env.example` los declara así a propósito (regla 2, sección 2).
Sobre el código que sí es "nuestro":

- **Nunca credenciales, tokens ni secretos hardcodeados fuera de `.env` /
  Modelfiles** (ya era regla 2 de este documento; SonarCloud lo marca como
  vulnerabilidad `Hardcoded credentials`, no solo como estilo). Tampoco en
  tests: usar valores claramente ficticios y distintos de los canarios
  reales (patrón ya seguido en `tests/test_main.py`, p. ej.
  `SPT-DEMO-4321`).
- **`yaml.safe_load()` siempre, nunca `yaml.load()`** (ya era contrato de
  `cargar_config()`, sección 4) — `yaml.load()` sin `Loader` es
  deserialización insegura (RCE), uno de los hotspots más comunes que
  reporta SonarCloud en proyectos Python.
- **Aleatoriedad de propósito criptográfico/de seguridad usa `secrets`,
  nunca `random`.** Ya es el caso de los marcadores de `delimitar()`
  (`secrets.token_hex()`); mantenerlo si se agrega cualquier otro token,
  ID de sesión o valor impredecible con fines de seguridad.
- **Nunca `subprocess` con `shell=True` sobre una cadena construida con
  entrada externa** (inyección de comandos). Si un script de `ataques/`
  necesita invocar una herramienta externa (p. ej. `nmap`, `hey`), pasar
  los argumentos como lista, nunca como string interpolado.
- **Nunca desactivar la verificación TLS** (`verify=False` en `httpx`/
  `requests`) ni bajar a versiones de TLS obsoletas, ni siquiera "solo
  para probar en local".
- **Mensajes de error hacia el cliente, siempre genéricos** (ya aplicado
  en `proxy/main.py` tras la revisión OWASP del V1): el detalle real
  (traceback, texto de excepción, nombre de modelo/backend) se loggea
  server-side, nunca se reenvía tal cual en una respuesta HTTP — evita
  tanto fuga de información como los hotspots de "Error messages should
  not reveal implementation details" de SonarCloud.
- **Nunca loggear el cuerpo completo de una petición/respuesta a nivel
  INFO si puede contener una credencial** (el propio experimento las
  maneja a propósito). El esquema de log de 8 campos ya evita esto: loggea
  campos estructurados, no el payload crudo sin pasar antes por
  `filtrado`/`clasificación`.
- **Dependencias con versión exacta fijada** en `requirements.txt` /
  `requirements-dev.txt` / `Dockerfile` (ya es la convención del
  proyecto) — una dependencia sin pin es un hallazgo de SonarCloud
  (`Vulnerable and outdated dependencies`) y además rompe la
  reproducibilidad entre las 4 máquinas del equipo.
- **Si se agrega CORS al proxy en algún momento:** nunca
  `allow_origins=["*"]` combinado con `allow_credentials=True`. Hoy el
  proxy no tiene CORS configurado; si hace falta, restringir a orígenes
  explícitos.
- Antes de comitear, si hay tiempo, correr un vistazo con `ruff check .`
  pensando específicamente en estas categorías (hoy `ruff.toml` no tiene
  habilitado el set `S` de flake8-bandit, que cubre buena parte de esto
  automáticamente — considerarlo como mejora futura, avisando antes al
  equipo porque cambia lo que `ruff check .` reporta para las 4 personas).
- **Security Hotspots de SonarCloud que sean falsos positivos deliberados
  de este proyecto** (p. ej. algo relacionado con los canarios o con que
  el proxy intencionalmente no tiene autenticación de usuario, fuera de
  alcance del experimento): márcalos como revisados con una nota en
  SonarCloud explicando por qué, en vez de ignorarlos en silencio — igual
  que `CONFLICTOS_RESUELTOS.md` exige registrar toda decisión de diseño no
  obvia.

### Principios de diseño (SOLID y código limpio)

Valen para **todo código nuevo o que se toque**. El patrón de referencia del repositorio son
`proxy/memoria_decisiones/` y `proxy/siem/`: léelos antes de diseñar otra extensión.

**SOLID**
- **S — una sola razón para cambiar.** Un módulo o clase hace una cosa: el dominio no sabe de E/S, el
  servicio no sabe de archivos ni de redes, un adaptador no sabe de otro adaptador. Si para describir
  una clase necesitas «y», parte la clase.
- **O — abierto a extensión, cerrado a modificación.** Un destino, un formato o una base de datos
  nuevos son **un módulo nuevo registrado por configuración**, nunca un `if/elif` más en el núcleo.
- **L — sustituibles.** Todo adaptador cumple el contrato del puerto completo (mismas excepciones,
  mismas garantías: `ErrorSIEM`, `ErrorAlmacen`); si hace falta la prueba compartida
  (`tests/contrato_almacen.py`), existe.
- **I — contratos pequeños.** Un puerto expone lo mínimo (`formatear`, `enviar`); lo opcional va en
  otro (`Cerrable`). Nadie implementa un método que no usa.
- **D — depender de abstracciones.** El núcleo depende de `Protocol`s; los adaptadores concretos se
  inyectan desde **un único lugar de composición** (`composicion.py`), el único que lee el entorno.

**Código limpio**
- Nombres que dicen la intención; funciones cortas con una sola tarea; sin números ni textos mágicos
  (constantes con nombre, definidas una vez).
- Sin duplicación: si dos módulos hacen lo mismo se extrae (`proxy/complementos.py`).
- Los errores se traducen en la frontera (el adaptador lanza el error del puerto) y **nunca** llevan
  claves ni contenido del usuario; nada de `pass` silencioso.
- Estado compartido solo detrás de un objeto con su lock; nada de diccionarios globales mutables
  (un **registro es un objeto**).
- Sin dependencias ocultas: lo que una clase necesita (reloj, cliente HTTP, redactor) se recibe, no se
  importa a mano ni se lee de `os.environ`.

**Cómo se vigila.** Cada paquete con puertos y adaptadores lleva **pruebas de arquitectura** con `ast`
(`tests/test_siem_arquitectura.py`, `tests/test_memoria_servicio.py`): qué capa puede importar a cuál,
quién puede leer el entorno, que no se desactive TLS. Si una te falla, el acoplamiento es real:
corrige el diseño, no la prueba.

**Estado honesto (2026-10-06).** Aplicado de punta a punta en `memoria_decisiones/` y `siem/`. **Aún no**
lo cumplen, y se refactorizan al tocarlos (no en bloque, para no romper un experimento ya medido):
`proxy/main.py` (~1400 líneas: endpoint, orquestación de la cadena, construcción del evento, métricas),
`proxy/mecanismos.py` (~950), `backends_entrada.py` (diccionario de backends en vez de un registro
objeto) y `modelos_protegidos.py`. Cambiar la cadena de mecanismos exige además repetir la validación
de las 7 configuraciones.

---

## 8. Coordinación del equipo

Cuatro personas trabajan sobre el mismo repo en paralelo. Reparto grueso:

- **Anderson Fabian Garcia Nieto (García)** — infraestructura, Docker, filtrado, clasificación, mínimo privilegio, cola + rate limit, medición de costo.
- **Carlos Mario Piedrahita Arango (Piedrahita)** — configuración y stubs, delimitación, cableado de mecanismos al pipeline, interfaz de aprobación, integración/conflictos, limpieza de datos, export SIEM.
- **Andres Felipe Sabogal Wilches (Sabogal)** — ejecución de todos los vectores de ataque y registro de resultados crudos.
- **Ana Gabriela Fiquitiva Poveda (Fiquitiva)** — esquema de log, consolidación, tablas, gráficas e informe.

**Antes de cambiar** una firma en `mecanismos.py`, un nombre de campo del log, o una columna del CSV: avisar. Ese es el punto donde este proyecto se rompe.

---

## 9. Trampas conocidas

- **Fail closed en el clasificador.** Un timeout de Llama Guard se trata como `unsafe`. Nunca dejar pasar por defecto.
- **Llama Guard no siempre responde en formato.** Validar la respuesta antes de interpretarla como booleano; loggear error claro si es inesperada.
- **En C4 la extracción (paso 1 del V4) sí debe funcionar.** Mínimo privilegio bloquea el uso cruzado (paso 2), no la extracción. Confundirlos invalida el análisis.
- **Encolar no es rechazar.** La aprobación humana introduce demora, que es un costo a reportar, no una caída del servicio.
- **Falsos positivos acumulados.** Con las 5 banderas activas hace falta al menos un test de petición legítima que atraviese la cadena limpia.
- **El LLM no es determinista.** Los resultados no se reproducen bit a bit; eso se declara como limitación metodológica, no se esconde.
- **Fechas.** El cronograma del proyecto corre de agosto a noviembre de **2026**. Algunas rutas del documento original de planeación dicen `2025`; usar el año correcto al crear carpetas en `/resultados/`.

---

## 10. Al terminar una tarea

- [ ] `pytest` pasa completo.
- [ ] `ruff` y `black` limpios.
- [ ] Los criterios de aceptación de la tarea de la semana están todos marcados.
- [ ] Si cambió un contrato compartido, este archivo está actualizado en el mismo commit.
- [ ] Si se resolvió un conflicto de integración, quedó en `CONFLICTOS_RESUELTOS.md`.
- [ ] El código nuevo respeta los principios de diseño de la sección 7 (puertos y adaptadores, un solo lugar
      que lee el entorno, sin duplicación) y sus pruebas de arquitectura pasan.
- [ ] Sin credenciales/tokens hardcodeados, sin `yaml.load()` sin `Loader`, sin `subprocess(shell=True)` con entrada externa, sin TLS deshabilitado (ver sección 7, "Seguridad del código").
- [ ] Commit con mensaje descriptivo y push.
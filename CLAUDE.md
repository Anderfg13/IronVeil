# CLAUDE.md — IronVeil

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
│  Cadena de mecanismos (orden fijo):         │
│   1. filtrado        (entrada)              │
│   2. delimitación    (construye prompt)     │
│   3. clasificación   (entrada)              │
│   4. mínimo privilegio                      │
│   5. aprobación humana / rate limit         │
│                                             │
│         ▼ si nada bloqueó                   │
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

- **Orden:** filtrado → delimitación → clasificación → mínimo privilegio → aprobación humana. Justificación: lo barato computacionalmente primero, lo caro (modelo clasificador) después.
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
# función pura, sin red, sin estado

def clasificar(texto: str, direccion: str) -> bool: ...
# True = unsafe. Timeout ⇒ True (fail closed, nunca fail open)

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

---

## 5. Estructura del repositorio

Esta es la estructura **objetivo**. Lo marcado `[ya existe]` está en el repo hoy; el resto es lo que se va creando a medida que avanzan las semanas — no asumas que ya está ahí sin comprobarlo.

```
/proxy/                 main.py (FastAPI) [ya existe], mecanismos.py, cola.py
/ollama/modelfiles/     Modelfile.soporte.template, Modelfile.rrhh.template [ya existen]
/tests/                 pruebas unitarias y de integración
/ataques/               variantes_ataque.md, vector4_*.py, vector5_*.py, promptfooconfig.yaml
/resultados/            resultados_template.csv, /YYYY-MM-DD/ logs crudos, /graficas/
/analisis/              consolidar.py, validar_dataset.py, análisis en Markdown
/docs/                  arquitectura.md [ya existe], FUENTE_DE_VERDAD.md [ya existe, por rellenar],
                        CONFLICTOS_RESUELTOS.md, LIMPIEZA_DATOS.md, CHECKLIST_ENTREGA.md
/informe/               main.tex, PDF compilado
docker-compose.yml [ya existe] · config.yaml · .env.example [ya existe] · README.md [ya existe]
```

Nada suelto en la raíz salvo lo listado arriba.

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

---

## 8. Coordinación del equipo

Cuatro personas trabajan sobre el mismo repo en paralelo. Reparto grueso:

- **García** — infraestructura, Docker, filtrado, clasificación, mínimo privilegio, cola + rate limit, medición de costo.
- **Piedrahita** — configuración y stubs, delimitación, cableado de mecanismos al pipeline, interfaz de aprobación, integración/conflictos, limpieza de datos, export SIEM.
- **Sabogal** — ejecución de todos los vectores de ataque y registro de resultados crudos.
- **Fiquitiva** — esquema de log, consolidación, tablas, gráficas e informe.

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
- [ ] Commit con mensaje descriptivo y push.
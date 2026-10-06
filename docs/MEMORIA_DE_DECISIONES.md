# Memoria de decisiones humanas (extensión opcional)

Cuando un humano **rechaza** una petición que un mecanismo retuvo, el proxy la **recuerda**:
la próxima vez que llegue el mismo mensaje (para el mismo modelo) se rechaza al instante, sin
pasar por la cola de revisión ni por la cadena. Es una **memoria de decisiones**, no
aprendizaje automático: es exacta, auditable y revocable.

Está **apagada por defecto** y vive en `proxy/memoria_decisiones.py`.

## Cómo se usa

1. Actívala en `.env`:
   ```
   MEMORIA_RECHAZOS=1
   ```
2. Reconstruye y levanta el proxy: `docker compose up -d --build proxy`.
3. Manda un mensaje que un mecanismo retenga (con `aprobacion_humana` activa). Queda en la cola
   (429).
4. En la consola (`/revision/ui`) **recházalo**. El diálogo avisa «Además se recordará…» y, al
   decidir, la consola confirma «Se recordó este rechazo».
5. Manda el mismo mensaje otra vez: ahora recibe un **400 inmediato**. No entra a la cola, no
   genera aviso y no llega al modelo.

**Si «no pasa nada», casi siempre es que está apagada.** Con `MEMORIA_RECHAZOS` vacío la extensión
no hace nada. Compruébalo en la pestaña **Memoria** de la consola (siempre visible: apagada,
dice «La memoria está apagada» y cómo encenderla) y en el log del proxy al arrancar
(`Memoria de decisiones: APAGADA` o `ACTIVA, N regla(s), almacen: …`). Recuerda que los cambios de `.env`
solo se aplican al recrear el contenedor (`docker compose up -d proxy`).

## Lo que ve quien revisa (la consola)

- **Pestaña Memoria**, junto a Pendientes e Historial: las reglas recordadas (más reciente
  primero), con la vista previa del mensaje, el modelo, el mecanismo que lo retuvo, quién lo
  decidió, cuándo y **cuántas veces ha bloqueado solo** desde que arrancó el proxy.
- Arriba de la lista, el **estado**: cuántas reglas hay y **dónde se guardan** («guardadas en
  SQLite (memoria.db)»), o un aviso en claro si solo están en memoria.
- Botón **Olvidar** (solo revisores, con confirmación): ese mensaje vuelve a pasar por los
  mecanismos y por la cola.
- Al **rechazar**, el diálogo avisa si esa decisión se va a recordar, y al terminar lo confirma.

## Cómo está construida (puertos y adaptadores)

Cada capa depende **solo de la de abajo**; el núcleo no conoce a sus adaptadores.

| Capa | Archivo (`proxy/memoria_decisiones/`) | Qué es | Depende de |
|---|---|---|---|
| Composición | `composicion.py` | lee el entorno **una vez** (`Configuracion`) y cablea todo | todo lo demás |
| Servicio | `servicio.py` | el caso de uso: recordar, consultar, olvidar | dominio y puerto |
| Puerto | `puerto.py` | `AlmacenMemoria`: el contrato de un almacén, y `ErrorAlmacen` | dominio |
| Registro | `registro.py` | `RegistroAlmacenes`: de la URL al adaptador | puerto |
| Adaptadores | `almacenes/jsonl.py`, `almacenes/sqlite.py` | un adaptador por archivo | dominio y puerto |
| Dominio | `dominio.py` | qué es una regla y cómo se compara (huella, normalización) | nada |

Lo que eso garantiza (y vigilan **pruebas de arquitectura** en `tests/test_memoria_servicio.py`):
- el servicio **no importa ningún almacén** ni toca archivos o bases de datos: recibe el almacén
  **inyectado**, igual que el `redactor` de credenciales y el reloj;
- **solo `composicion.py` lee el entorno**: ni el dominio, ni el servicio, ni los adaptadores saben
  que existe un `.env`;
- el registro es un **objeto**, no un diccionario global: no hay estado compartido entre pruebas ni
  entre instancias.

## Dónde se guardan las reglas (almacén intercambiable)

Las reglas se leen en memoria al arrancar (la consulta de cada petición es un diccionario) y cada
cambio se escribe **en el momento** en un **almacén**, que se elige con una URL en
`MEMORIA_RECHAZOS_ALMACEN`:

| URL | Almacén | Cuándo |
|---|---|---|
| `jsonl:///app/memoria/rechazos.jsonl` | JSON Lines (**por defecto**) | sin dependencias ni servidor; legible a simple vista |
| `sqlite:///app/memoria/memoria.db` | SQLite (biblioteca estándar) | una base real y transaccional; deja además una tabla de **auditoría** (quién olvidó cada regla y cuándo) |
| `esquema://…` | el de **tu empresa** | ver «Conectar otra base de datos» |

Ambos escriben en `./memoria` del equipo (montada en el contenedor como `/app/memoria`), **no** en
un volumen de Docker: la memoria sobrevive a apagar el contenedor, reconstruir la imagen, `docker
compose down -v` y reiniciar el equipo, y se puede ver, copiar y respaldar. **Para borrarlo todo,
borra el archivo** con el proxy apagado.

Robustez (probada con los dos almacenes, con la misma batería):
- Cada cambio se fuerza a disco antes de responder (`fsync` / `synchronous = FULL`).
- JSON Lines: un renglón dañado se **omite con un aviso** y un corte a mitad de escritura no pierde
  lo anterior. SQLite: una base corrupta no impide arrancar.
- Si el almacén no está disponible (carpeta sin permiso, base caída, URL o complemento mal
  configurados), la memoria **funciona solo en memoria y lo dice** en el log y en la consola («SOLO
  en memoria: se perderán al reiniciar»). Nunca deja de proteger por un fallo de almacenamiento ni
  tumba el proxy.
- **Una sola instancia del proxy**: las reglas se leen al arrancar, así que varias instancias contra
  la misma base no se enteran de las reglas nuevas de las otras hasta reiniciar.

### Conectar otra base de datos (PostgreSQL, MySQL, Redis…) sin editar IronVeil

Una empresa escribe su adaptador **en su propio paquete** y lo registra por configuración; no se toca
ningún archivo de IronVeil.

**1. El adaptador** cumple el contrato de `AlmacenMemoria` (cinco miembros):

```python
# mi_empresa/ironveil_postgres.py
from proxy.memoria_decisiones import ErrorAlmacen, Regla

class AlmacenPostgres:
    descripcion = "PostgreSQL (mi-empresa)"        # lo que ve la consola

    def __init__(self, destino: str) -> None: ...  # lo que sigue a «postgresql://»

    def cargar(self) -> list[Regla]: ...           # las reglas VIGENTES; deja el almacén listo
    def guardar(self, regla: Regla) -> None: ...   # persiste ANTES de volver
    def olvidar(self, huella: str, por: str, en: str) -> None: ...
    def cerrar(self) -> None: ...                  # libera la conexión; repetible

def registrar(registro) -> None:                   # el enganche que busca IronVeil
    registro.registrar("postgresql", AlmacenPostgres)
```

**2. Se activa en `.env`**, sin cambiar IronVeil:

```
MEMORIA_RECHAZOS_ADAPTADORES=mi_empresa.ironveil_postgres
MEMORIA_RECHAZOS_ALMACEN=postgresql://usuario@servidor/base
```

**3. Reglas del contrato** (lo que cualquier adaptador debe respetar):
- Cualquier fallo se lanza como **`ErrorAlmacen`** (nunca otra excepción): traduce la del controlador.
  La memoria lo captura y sigue en memoria avisando.
- `guardar` y `olvidar` **persisten antes de volver**; `olvidar` de algo inexistente **no falla**;
  guardar dos veces la misma regla **no la duplica**.
- **No necesita ser seguro entre hilos**: el servicio serializa las llamadas.
- Solo recibe **huellas y la vista previa** de la `Regla`; nunca el mensaje completo, y no debe
  guardarlo ni escribirlo en el log.
- La cadena de conexión y las claves van en `.env` (**nunca en el código**), con TLS siempre
  verificado.

**4. Pruébalo con la misma batería** que los adaptadores incluidos (`tests/contrato_almacen.py`):

```python
from contrato_almacen import ContratoAlmacen

class TestMiAlmacen(ContratoAlmacen):
    @pytest.fixture
    def nuevo(self, tmp_path):
        return lambda: AlmacenPostgres("usuario@servidor/base_de_pruebas")
```

Notas honestas:
- El módulo de `MEMORIA_RECHAZOS_ADAPTADORES` **se importa y se ejecuta con los permisos del proxy**:
  solo código de confianza, como cualquier complemento. Solo se aceptan **nombres de módulo**
  (nunca rutas ni expresiones).
- Que el módulo sea **importable dentro del contenedor** (instalarlo en la imagen o montarlo y
  añadirlo al `PYTHONPATH`) lo resuelve quien despliega: IronVeil no lo hace por ti.
- **No hay un adaptador de PostgreSQL/MySQL incluido ni verificado**: necesita un controlador
  (dependencia nueva con versión fija) y un servidor para probarlo. SQLite y JSON Lines sí están
  probados, también con la batería de contrato y con un almacén de «empresa» simulado que se
  conecta por este mismo camino.

## Qué se recuerda y qué no

- **Solo rechazos**, nunca aprobaciones: un rechazo de más falla del lado seguro; una aprobación
  de más dejaría pasar para siempre algo que un mecanismo retuvo.
- **Solo retenciones por contenido** (`filtrado`, `clasificacion`, `minimo_privilegio`). Lo
  retenido por **exceso de peticiones** no se recuerda (puede ser un «hola» legítimo), ni las
  solicitudes de herramientas.
- **Por modelo**: un rechazo de `soporte` no vale para `rrhh`.
- **Solo coincidencia exacta tras normalizar**: mayúsculas, tildes, espacios, puntuación de los
  bordes y caracteres invisibles (ceros de ancho cero) no cambian la huella.

## Límites que hay que tener claros

- **No frena paráfrasis.** Si el atacante cambia una palabra, la memoria no lo reconoce y el
  mensaje vuelve a los mecanismos y a la cola. Es un **complemento**, no una barrera: no debe
  presentarse como defensa contra variantes. Lo semántico (comparar significado, por ejemplo con
  embeddings) sería una segunda fase, más cara y probabilística.
- **Un rechazo equivocado se queda** hasta que alguien lo olvide: por eso existe **Olvidar**.
- **Solo decide el rol `revisor`**; el observador ve las reglas pero no puede olvidarlas. Revocar
  exige el token CSRF de la sesión.
- **Se guardan huellas (SHA-256), no el texto.** Solo se conserva una **vista previa de 60
  caracteres con las credenciales redactadas**, para que el revisor sepa qué está olvidando. Se
  puede apagar con `MEMORIA_RECHAZOS_VISTA_PREVIA=0` (entonces la lista solo muestra modelo,
  motivo y quién decidió).
- **Tope de reglas** (`MEMORIA_RECHAZOS_MAXIMO`, 5000): al llegar, no se agregan más y se avisa;
  nunca se descarta una regla en silencio.
- Los **aciertos** (cuántas veces actuó una regla) se cuentan **desde que arrancó el proxy**; ese
  contador no se guarda.

## Importante para el experimento

Las baterías de ataque repiten el mismo payload muchas veces. Con la memoria activa, tras el
primer rechazo el resto se bloquearía solo y **el ASR de C5 y C6 bajaría artificialmente**.
Por eso:

- **Los resultados de C0–C6 se midieron SIN la memoria** y no son comparables con una corrida que
  la tenga encendida. En el informe se presenta como **extensión aparte**: la respuesta a un
  ataque repetido pasa a ser instantánea («entre comillas», porque solo vale para el mismo
  mensaje).
- **No actives `MEMORIA_RECHAZOS` en una corrida del experimento.**
- Si se activa de todos modos, sus eventos no se confunden con el núcleo: llevan
  `es_extension: true`, `origen_decision: "memoria"` y `latencia_memoria_us`; el análisis de costo
  (`costo_por_mecanismo.py`) los excluye.

## En el log

Un rechazo por memoria se atribuye a `aprobacion_humana` (es una decisión humana recordada), así
que no aparece un sexto nombre de mecanismo y las invariantes del esquema se cumplen. Se
distingue por el campo extendido `origen_decision: "memoria"`.

## Variables (`.env`)

| Variable | Por defecto | Qué hace |
|---|---|---|
| `MEMORIA_RECHAZOS` | vacío (apagada) | `1` la enciende. Solo actúa con `aprobacion_humana` activa |
| `MEMORIA_RECHAZOS_ALMACEN` | `jsonl:///app/memoria/rechazos.jsonl` | Dónde se guardan: `jsonl://…`, `sqlite://…` u otro registrado |
| `MEMORIA_RECHAZOS_ADAPTADORES` | vacío | Módulos (separados por comas) que registran adaptadores propios, p. ej. `mi_empresa.ironveil_postgres` |
| `MEMORIA_RECHAZOS_MAXIMO` | `5000` | Tope de reglas |
| `MEMORIA_RECHAZOS_VISTA_PREVIA` | `1` | `0` guarda solo la huella, sin vista previa |

## API (la usa la consola)

- `GET /revision/memoria` — `activa`, `persistente`, `almacen`, `maximo` y las reglas; requiere
  sesión. Apagada responde `{"activa": false, "reglas": []}`.
- `DELETE /revision/memoria/{huella}` — olvida una regla; solo revisores, con token CSRF.
- `POST /revision/{id}/rechazar` — si recuerda la regla, la respuesta trae `"memoria"`:
  `recordada`, `ya_recordada`, `memoria_llena` o `recordada_sin_guardar`.

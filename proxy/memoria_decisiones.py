"""Memoria de decisiones humanas (EXTENSION opcional, apagada por defecto).

Cuando un humano **rechaza** una peticion que un mecanismo retuvo, el proxy recuerda ese
mensaje: la proxima vez que llegue el mismo (para el mismo modelo) se rechaza al
instante, sin pasar por la cola ni por la cadena. No es aprendizaje automatico: es una
memoria de decisiones, exacta y revocable.

Reglas de diseno (docs/MEMORIA_DE_DECISIONES.md):

- **Solo se recuerdan rechazos**, nunca aprobaciones: un rechazo de mas falla del lado
  seguro; una aprobacion de mas dejaria pasar para siempre algo que un mecanismo retuvo.
- **Solo coincidencia exacta tras normalizar** (mayusculas, tildes, espacios, caracteres
  invisibles). Si el atacante cambia una palabra, la memoria no lo reconoce: es un
  complemento de los mecanismos, no una barrera contra parafrasis.
- **Persistente y con almacen intercambiable.** Donde se guardan las reglas es un
  *adaptador* (`AlmacenMemoria`), igual que los clasificadores: hoy JSON Lines (por
  defecto) y SQLite; una empresa conecta su propia base de datos escribiendo un almacen
  nuevo y registrandolo en `ALMACENES`, sin tocar el resto. Las reglas se leen en
  memoria al arrancar (la consulta de cada peticion es un diccionario) y cada cambio se
  escribe en el almacen en el momento.
- **Se guardan huellas (SHA-256), no el texto.** Solo una vista previa corta, con las
  credenciales redactadas, para que el revisor sepa que esta olvidando (se puede apagar
  con MEMORIA_RECHAZOS_VISTA_PREVIA=0).
- **Revocable**: un rechazo equivocado no puede ser permanente.
- Solo se recuerdan retenciones por *contenido* (filtrado, clasificacion, minimo
  privilegio): un mensaje retenido por exceso de tasa puede ser legitimo ("hola").
- Tope de reglas (MEMORIA_RECHAZOS_MAXIMO): al llegar, no se agregan mas (nunca se
  descarta una regla en silencio).
- Una sola instancia del proxy: la memoria se lee al arrancar, asi que varias instancias
  contra la misma base no se enteran de las reglas nuevas de las otras hasta reiniciar.

Con la memoria activa los ataques repetidos se bloquean solos tras el primer rechazo:
los resultados de C0-C6 se midieron SIN ella y no son comparables. Sus eventos llevan
`origen_decision: "memoria"` y `es_extension`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import unicodedata
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import proxy.mecanismos as mecanismos

logger = logging.getLogger(__name__)

MEMORIA_RECHAZOS: bool = os.getenv("MEMORIA_RECHAZOS", "") == "1"
# Donde se guardan las reglas, como una URL: `jsonl:///ruta` o `sqlite:///ruta`.
MEMORIA_RECHAZOS_ALMACEN: str = os.getenv(
    "MEMORIA_RECHAZOS_ALMACEN", "jsonl:///app/memoria/rechazos.jsonl"
)
MEMORIA_RECHAZOS_MAXIMO: int = int(os.getenv("MEMORIA_RECHAZOS_MAXIMO", "5000"))
MEMORIA_RECHAZOS_VISTA_PREVIA: bool = (
    os.getenv("MEMORIA_RECHAZOS_VISTA_PREVIA", "1") == "1"
)

# Motivos de retencion que SI se recuerdan: los de contenido. Los de tasa y las
# herramientas no (un mensaje retenido por volumen puede ser perfectamente legitimo).
MOTIVOS_QUE_SE_RECUERDAN = frozenset({"filtrado", "clasificacion", "minimo_privilegio"})
LARGO_VISTA_PREVIA = 60
_PUNTUACION_DE_BORDE = " .,;:!?¡¿\"'"

RECORDADA = "recordada"
YA_RECORDADA = "ya_recordada"
MEMORIA_LLENA = "memoria_llena"
RECORDADA_SIN_GUARDAR = "recordada_sin_guardar"


def normalizar(texto: str) -> str:
    """Forma canonica para comparar: sin mayusculas, tildes, espacios de mas ni
    caracteres invisibles (ceros de ancho cero, marcas de direccion)."""
    t = unicodedata.normalize("NFKC", texto)
    t = "".join(c for c in t if unicodedata.category(c) != "Cf")
    t = unicodedata.normalize("NFD", t.casefold())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.split()).strip(_PUNTUACION_DE_BORDE)


def huella(modelo: str, texto: str) -> str:
    """SHA-256 del par (modelo, texto normalizado): la regla es por modelo."""
    clave = f"{modelo.strip().casefold()}\x00{normalizar(texto)}"
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()


def _vista_previa(texto: str) -> str:
    """Primeros caracteres del mensaje, con las credenciales redactadas."""
    corto = " ".join(texto.split())[:LARGO_VISTA_PREVIA]
    corto = mecanismos.PATRON_CREDENCIAL_GENERICO.sub(mecanismos.TEXTO_REDACTADO, corto)
    return corto + ("…" if len(texto.strip()) > LARGO_VISTA_PREVIA else "")


@dataclass(frozen=True)
class Regla:
    """Un rechazo recordado. Nunca lleva el mensaje completo."""

    huella: str
    modelo: str
    decidido_por: str
    decidido_en: str
    motivo: str
    vista_previa: str | None = None


# --- Almacenes: donde viven las reglas (adaptador) ---


class ErrorAlmacen(Exception):
    """El almacen no esta disponible o fallo una operacion (disco, base de datos...)."""


class AlmacenMemoria(Protocol):
    """Donde se guardan las reglas. Para usar otra base de datos se escribe uno nuevo.

    Contrato: `cargar()` devuelve las reglas VIGENTES (ya aplicado lo olvidado) y deja
    el almacen listo para escribir; `guardar` y `olvidar` persisten un cambio **antes de
    volver**. Cualquier fallo se lanza como `ErrorAlmacen` (nunca otra excepcion): la
    memoria lo captura y sigue funcionando en memoria, avisando.
    """

    descripcion: str

    def cargar(self) -> list[Regla]: ...

    def guardar(self, regla: Regla) -> None: ...

    def olvidar(self, huella: str, por: str, en: str) -> None: ...


class AlmacenJsonl:
    """Un archivo JSON Lines: un renglon por decision (`recordar` u `olvidar`).

    Sin dependencias ni servidor; legible a simple vista. Cada renglon se fuerza a disco
    (`fsync`). Un renglon danado se omite con un aviso y un corte a mitad de escritura
    no pierde lo anterior.
    """

    def __init__(self, ruta: Path) -> None:
        self._ruta = ruta
        self._lock = threading.Lock()
        self.descripcion = f"JSON Lines ({ruta.name})"

    def cargar(self) -> list[Regla]:
        try:
            self._ruta.parent.mkdir(parents=True, exist_ok=True)
            self._ruta.touch(exist_ok=True)
            if not os.access(self._ruta, os.W_OK):
                raise PermissionError("el archivo no es escribible")
            reglas: dict[str, Regla] = {}
            omitidos = 0
            with self._ruta.open(encoding="utf-8") as archivo:
                for linea in archivo:
                    if linea.strip() and not self._aplicar(linea, reglas):
                        omitidos += 1
        except OSError as exc:
            raise ErrorAlmacen(f"{type(exc).__name__}: {self._ruta}") from exc
        if omitidos:
            logger.warning(
                "memoria de decisiones: %d renglon(es) dañado(s) omitido(s) en %s.",
                omitidos,
                self._ruta,
            )
        return list(reglas.values())

    @staticmethod
    def _aplicar(linea: str, reglas: dict[str, Regla]) -> bool:
        """Aplica un renglon. False si no se entiende (se omite)."""
        try:
            dato = json.loads(linea)
            if dato["op"] == "recordar":
                regla = Regla(
                    huella=dato["huella"],
                    modelo=dato["modelo"],
                    decidido_por=dato["decidido_por"],
                    decidido_en=dato["decidido_en"],
                    motivo=dato["motivo"],
                    vista_previa=dato.get("vista_previa"),
                )
                reglas[regla.huella] = regla
            elif dato["op"] == "olvidar":
                reglas.pop(dato["huella"], None)
            return True
        except (ValueError, KeyError, TypeError):
            return False

    def _anexar(self, dato: dict[str, Any]) -> None:
        try:
            with self._lock, self._ruta.open("a", encoding="utf-8") as archivo:
                archivo.write(json.dumps(dato, ensure_ascii=False) + "\n")
                archivo.flush()
                os.fsync(archivo.fileno())
        except OSError as exc:
            raise ErrorAlmacen(f"{type(exc).__name__}: {self._ruta}") from exc

    def guardar(self, regla: Regla) -> None:
        self._anexar({"op": "recordar", **asdict(regla)})

    def olvidar(self, huella: str, por: str, en: str) -> None:
        self._anexar({"op": "olvidar", "huella": huella, "por": por, "en": en})


class AlmacenSqlite:
    """Una base SQLite (biblioteca estandar, sin servidor ni dependencias nuevas).

    Transaccional y mas robusta que un archivo de texto; ademas deja una tabla de
    **auditoria** con quien olvido cada regla y cuando. Es el modelo para conectar otra
    base de datos (PostgreSQL, MySQL...): mismas tres operaciones, otro cliente.
    """

    _ESQUEMA = (
        "CREATE TABLE IF NOT EXISTS reglas ("
        " huella TEXT PRIMARY KEY, modelo TEXT NOT NULL, decidido_por TEXT NOT NULL,"
        " decidido_en TEXT NOT NULL, motivo TEXT NOT NULL, vista_previa TEXT)",
        "CREATE TABLE IF NOT EXISTS auditoria ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, op TEXT NOT NULL,"
        " huella TEXT NOT NULL, por TEXT NOT NULL, en TEXT NOT NULL)",
    )

    def __init__(self, ruta: Path) -> None:
        self._ruta = ruta
        self._lock = threading.Lock()
        self._con: sqlite3.Connection | None = None
        self.descripcion = f"SQLite ({ruta.name})"

    def _conexion(self) -> sqlite3.Connection:
        if self._con is None:
            raise ErrorAlmacen("la base no esta abierta (falta cargar())")
        return self._con

    def cargar(self) -> list[Regla]:
        try:
            self._ruta.parent.mkdir(parents=True, exist_ok=True)
            con = sqlite3.connect(self._ruta, check_same_thread=False, timeout=10)
            con.execute("PRAGMA synchronous = FULL")  # durabilidad antes que velocidad
            for sentencia in self._ESQUEMA:
                con.execute(sentencia)
            con.commit()
            filas = con.execute(
                "SELECT huella, modelo, decidido_por, decidido_en, motivo, vista_previa"
                " FROM reglas"
            ).fetchall()
        except (OSError, sqlite3.Error) as exc:
            raise ErrorAlmacen(f"{type(exc).__name__}: {self._ruta}") from exc
        self._con = con
        return [Regla(*fila) for fila in filas]

    def _ejecutar(self, sentencias: list[tuple[str, tuple[Any, ...]]]) -> None:
        con = self._conexion()
        try:
            with self._lock:
                for sql, parametros in sentencias:
                    con.execute(sql, parametros)
                con.commit()
        except sqlite3.Error as exc:
            con.rollback()
            raise ErrorAlmacen(f"{type(exc).__name__}: {self._ruta}") from exc

    def guardar(self, regla: Regla) -> None:
        self._ejecutar(
            [
                (
                    "INSERT OR REPLACE INTO reglas VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        regla.huella,
                        regla.modelo,
                        regla.decidido_por,
                        regla.decidido_en,
                        regla.motivo,
                        regla.vista_previa,
                    ),
                ),
                (
                    "INSERT INTO auditoria (op, huella, por, en) VALUES (?, ?, ?, ?)",
                    ("recordar", regla.huella, regla.decidido_por, regla.decidido_en),
                ),
            ]
        )

    def olvidar(self, huella: str, por: str, en: str) -> None:
        self._ejecutar(
            [
                ("DELETE FROM reglas WHERE huella = ?", (huella,)),
                (
                    "INSERT INTO auditoria (op, huella, por, en) VALUES (?, ?, ?, ?)",
                    ("olvidar", huella, por, en),
                ),
            ]
        )


# Almacenes disponibles, por el esquema de la URL de MEMORIA_RECHAZOS_ALMACEN. Para
# conectar otra base de datos: escribir una clase con el contrato de `AlmacenMemoria` y
# registrarla aqui (docs/MEMORIA_DE_DECISIONES.md, "Conectar otra base de datos").
ALMACENES: dict[str, Callable[[str], AlmacenMemoria]] = {
    "jsonl": lambda ruta: AlmacenJsonl(Path(ruta)),
    "sqlite": lambda ruta: AlmacenSqlite(Path(ruta)),
}


def crear_almacen(url: str) -> AlmacenMemoria:
    """El almacen de una URL como `sqlite:///app/memoria/memoria.db`."""
    esquema, separador, ruta = url.strip().partition("://")
    fabrica = ALMACENES.get(esquema.lower())
    if not separador or not ruta or fabrica is None:
        raise ErrorAlmacen(
            f"MEMORIA_RECHAZOS_ALMACEN no es valida (esquemas disponibles: "
            f"{sorted(ALMACENES)}): se espera por ejemplo jsonl:///ruta o sqlite:///ruta."
        )
    return fabrica(ruta)


# --- La memoria ---


class MemoriaDecisiones:
    """Rechazos recordados: en memoria para consultar rapido, y en un almacen que los
    conserva entre reinicios."""

    def __init__(
        self,
        almacen: AlmacenMemoria | None,
        maximo: int = MEMORIA_RECHAZOS_MAXIMO,
        vista_previa: bool = True,
    ) -> None:
        self._almacen = almacen
        self._maximo = maximo
        self._con_vista_previa = vista_previa
        self._reglas: dict[str, Regla] = {}
        self._aciertos: dict[str, int] = {}
        self._lock = threading.RLock()
        self.persistente = False
        self.descripcion = almacen.descripcion if almacen else "solo en memoria"
        self._cargar()

    @property
    def maximo(self) -> int:
        return self._maximo

    def _cargar(self) -> None:
        """Reconstruye las reglas desde el almacen; si falla, sigue solo en memoria."""
        if self._almacen is None:
            return
        try:
            for regla in self._almacen.cargar():
                self._reglas[regla.huella] = regla
        except ErrorAlmacen as exc:
            logger.error(
                "memoria de decisiones: el almacen no esta disponible (%s); funciona "
                "SOLO en memoria y se perdera al reiniciar.",
                exc,
            )
            self.descripcion = "solo en memoria"
            return
        self.persistente = True
        logger.info(
            "memoria de decisiones: %d regla(s) cargada(s) de %s.",
            len(self._reglas),
            self.descripcion,
        )

    def _persistir(self, operacion: Callable[[], None]) -> bool:
        """Ejecuta una escritura en el almacen. False si no se pudo guardar."""
        if self._almacen is None or not self.persistente:
            return False
        try:
            operacion()
            return True
        except ErrorAlmacen as exc:
            logger.error(
                "memoria de decisiones: no se pudo guardar (%s); la regla vale hasta "
                "el proximo reinicio.",
                exc,
            )
            return False

    def coincide(self, modelo: str, texto: str) -> Regla | None:
        """La regla que rechaza este mensaje para este modelo, o None."""
        clave = huella(modelo, texto)
        with self._lock:
            regla = self._reglas.get(clave)
            if regla is not None:
                self._aciertos[clave] = self._aciertos.get(clave, 0) + 1
            return regla

    def recordar_rechazo(
        self, modelo: str, texto: str, decidido_por: str, motivo: str
    ) -> str:
        """Recuerda un rechazo humano. Devuelve RECORDADA, YA_RECORDADA, MEMORIA_LLENA o
        RECORDADA_SIN_GUARDAR (vale hasta reiniciar: no se pudo escribir en el almacen).
        """
        clave = huella(modelo, texto)
        with self._lock:
            if clave in self._reglas:
                return YA_RECORDADA
            if len(self._reglas) >= self._maximo:
                logger.warning(
                    "memoria de decisiones llena (%d reglas): no se recuerda este "
                    "rechazo; olvida alguna regla o sube MEMORIA_RECHAZOS_MAXIMO.",
                    self._maximo,
                )
                return MEMORIA_LLENA
            regla = Regla(
                huella=clave,
                modelo=modelo,
                decidido_por=decidido_por,
                decidido_en=datetime.now().astimezone().isoformat(),
                motivo=motivo,
                vista_previa=_vista_previa(texto) if self._con_vista_previa else None,
            )
            self._reglas[clave] = regla
            almacen = self._almacen
            guardada = almacen is not None and self._persistir(
                lambda: almacen.guardar(regla)
            )
        return RECORDADA if guardada else RECORDADA_SIN_GUARDAR

    def olvidar(self, clave: str, por: str) -> bool:
        """Revoca una regla. False si no existe."""
        with self._lock:
            if self._reglas.pop(clave, None) is None:
                return False
            self._aciertos.pop(clave, None)
            almacen = self._almacen
            if almacen is not None:
                en = datetime.now().astimezone().isoformat()
                self._persistir(lambda: almacen.olvidar(clave, por, en))
        return True

    def listar(self) -> list[dict[str, Any]]:
        """Las reglas, la mas reciente primero, con cuantas veces actuaron desde que
        arranco el proxy (ese contador no se guarda)."""
        with self._lock:
            reglas = sorted(
                self._reglas.values(), key=lambda r: r.decidido_en, reverse=True
            )
            return [
                {**asdict(r), "aciertos": self._aciertos.get(r.huella, 0)}
                for r in reglas
            ]

    def tamano(self) -> int:
        with self._lock:
            return len(self._reglas)


_instancia: MemoriaDecisiones | None = None
_lock_instancia = threading.Lock()


def obtener() -> MemoriaDecisiones | None:
    """La memoria compartida, o None si la extension esta apagada (por defecto)."""
    global _instancia
    if not MEMORIA_RECHAZOS:
        return None
    with _lock_instancia:
        if _instancia is None:
            try:
                almacen: AlmacenMemoria | None = crear_almacen(MEMORIA_RECHAZOS_ALMACEN)
            except ErrorAlmacen as exc:
                logger.error(
                    "memoria de decisiones: %s; funciona SOLO en memoria.", exc
                )
                almacen = None
            _instancia = MemoriaDecisiones(
                almacen, MEMORIA_RECHAZOS_MAXIMO, MEMORIA_RECHAZOS_VISTA_PREVIA
            )
        return _instancia

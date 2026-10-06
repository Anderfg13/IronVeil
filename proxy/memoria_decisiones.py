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
- **Persistente**: cada decision se anexa a un archivo JSON Lines (con `fsync`) y al
  arrancar se reconstruye, asi que sobrevive a reinicios y a recrear los contenedores.
  Un renglon dañado se omite con un aviso; nunca impide arrancar.
- **Se guardan huellas (SHA-256), no el texto.** Solo una vista previa corta, con las
  credenciales redactadas, para que el revisor sepa que esta olvidando (se puede apagar
  con MEMORIA_RECHAZOS_VISTA_PREVIA=0).
- **Revocable**: un rechazo equivocado no puede ser permanente.
- Solo se recuerdan retenciones por *contenido* (filtrado, clasificacion, minimo
  privilegio): un mensaje retenido por exceso de tasa puede ser legitimo ("hola").
- Tope de reglas (MEMORIA_RECHAZOS_MAXIMO): al llegar, no se agregan mas (nunca se
  descarta una regla en silencio).

Con la memoria activa los ataques repetidos se bloquean solos tras el primer rechazo:
los resultados de C0-C6 se midieron SIN ella y no son comparables. Sus eventos llevan
`origen_decision: "memoria"` y `es_extension`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import proxy.mecanismos as mecanismos

logger = logging.getLogger(__name__)

MEMORIA_RECHAZOS: bool = os.getenv("MEMORIA_RECHAZOS", "") == "1"
MEMORIA_RECHAZOS_ARCHIVO: str = os.getenv(
    "MEMORIA_RECHAZOS_ARCHIVO", "/app/memoria/rechazos.jsonl"
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


class MemoriaDecisiones:
    """Rechazos recordados, en memoria y en un archivo JSON Lines que los conserva."""

    def __init__(
        self,
        archivo: Path | None,
        maximo: int = MEMORIA_RECHAZOS_MAXIMO,
        vista_previa: bool = True,
    ) -> None:
        self._archivo = archivo
        self._maximo = maximo
        self._con_vista_previa = vista_previa
        self._reglas: dict[str, Regla] = {}
        self._aciertos: dict[str, int] = {}
        self._lock = threading.RLock()
        self.persistente = False
        self._cargar()

    @property
    def maximo(self) -> int:
        return self._maximo

    # --- Persistencia -----------------------------------------------------------

    def _cargar(self) -> None:
        """Reconstruye las reglas leyendo el archivo; un renglon dañado se omite."""
        if self._archivo is None:
            return
        try:
            self._archivo.parent.mkdir(parents=True, exist_ok=True)
            self._archivo.touch(exist_ok=True)
            if not os.access(self._archivo, os.W_OK):
                raise PermissionError("el archivo no es escribible")
        except OSError as exc:
            logger.error(
                "memoria de decisiones: no se puede escribir en %s (%s); funciona SOLO "
                "en memoria y se perdera al reiniciar.",
                self._archivo,
                type(exc).__name__,
            )
            return
        self.persistente = True
        omitidos = 0
        with self._archivo.open(encoding="utf-8") as archivo:
            for linea in archivo:
                if linea.strip() and not self._aplicar(linea):
                    omitidos += 1
        if omitidos:
            logger.warning(
                "memoria de decisiones: %d renglon(es) dañado(s) omitido(s) en %s.",
                omitidos,
                self._archivo,
            )
        logger.info(
            "memoria de decisiones: %d regla(s) cargada(s) desde %s.",
            len(self._reglas),
            self._archivo,
        )

    def _aplicar(self, linea: str) -> bool:
        """Aplica un renglon del archivo. False si no se entiende (se omite)."""
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
                self._reglas[regla.huella] = regla
            elif dato["op"] == "olvidar":
                self._reglas.pop(dato["huella"], None)
            return True
        except (ValueError, KeyError, TypeError):
            return False

    def _anexar(self, dato: dict[str, Any]) -> bool:
        """Anexa un renglon y lo fuerza a disco. False si no se pudo guardar."""
        if self._archivo is None or not self.persistente:
            return False
        try:
            with self._archivo.open("a", encoding="utf-8") as archivo:
                archivo.write(json.dumps(dato, ensure_ascii=False) + "\n")
                archivo.flush()
                os.fsync(archivo.fileno())
            return True
        except OSError as exc:
            logger.error(
                "memoria de decisiones: no se pudo guardar en %s (%s); la regla vale "
                "hasta el proximo reinicio.",
                self._archivo,
                type(exc).__name__,
            )
            return False

    # --- Operaciones --------------------------------------------------------------

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
        RECORDADA_SIN_GUARDAR (vale hasta reiniciar: no se pudo escribir en disco)."""
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
            guardada = self._anexar({"op": "recordar", **asdict(regla)})
        return RECORDADA if guardada else RECORDADA_SIN_GUARDAR

    def olvidar(self, clave: str, por: str) -> bool:
        """Revoca una regla. False si no existe."""
        with self._lock:
            if self._reglas.pop(clave, None) is None:
                return False
            self._aciertos.pop(clave, None)
            self._anexar(
                {
                    "op": "olvidar",
                    "huella": clave,
                    "por": por,
                    "en": datetime.now().astimezone().isoformat(),
                }
            )
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
            _instancia = MemoriaDecisiones(
                Path(MEMORIA_RECHAZOS_ARCHIVO),
                MEMORIA_RECHAZOS_MAXIMO,
                MEMORIA_RECHAZOS_VISTA_PREVIA,
            )
        return _instancia

"""La composicion: el unico lugar que lee el entorno y junta las piezas.

El dominio, el servicio y los decodificadores no saben que existe un `.env`. Aqui se lee
la configuracion en un objeto inmutable, se arma el registro (los decodificadores
incluidos mas los de `NORMALIZACION_ADAPTADORES`) y se construye el normalizador.

Variables (ver `.env.example` y `docs/NORMALIZACION_DE_ENTRADA.md`):
    NORMALIZACION_ENTRADA          `1` la enciende (apagada por defecto)
    NORMALIZACION_DECODIFICADORES  lista separada por comas (base64,hex,rot13)
    NORMALIZACION_ADAPTADORES      modulos de terceros que registran decodificadores
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass

from proxy.complementos import cargar_complementos
from proxy.normalizacion import decodificadores
from proxy.normalizacion.dominio import Resultado
from proxy.normalizacion.puerto import ErrorNormalizacion
from proxy.normalizacion.registro import RegistroDecodificadores
from proxy.normalizacion.servicio import Normalizador

logger = logging.getLogger(__name__)

DECODIFICADORES_POR_DEFECTO = ("base64", "hex", "rot13")


@dataclass(frozen=True)
class Configuracion:
    """Todo lo que se configura por entorno, ya leido en un solo sitio."""

    activa: bool = False
    decodificadores: tuple[str, ...] = DECODIFICADORES_POR_DEFECTO
    adaptadores: tuple[str, ...] = ()

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str]) -> Configuracion:
        """Lee NORMALIZACION_ENTRADA, _DECODIFICADORES y _ADAPTADORES."""
        return cls(
            activa=entorno.get("NORMALIZACION_ENTRADA", "") == "1",
            decodificadores=_lista(entorno.get("NORMALIZACION_DECODIFICADORES", ""))
            or DECODIFICADORES_POR_DEFECTO,
            adaptadores=_lista(entorno.get("NORMALIZACION_ADAPTADORES", "")),
        )


def _lista(texto: str) -> tuple[str, ...]:
    return tuple(parte.strip() for parte in texto.split(",") if parte.strip())


def construir_registro(adaptadores: tuple[str, ...] = ()) -> RegistroDecodificadores:
    """El registro con los decodificadores incluidos y los de los modulos indicados."""
    registro = RegistroDecodificadores()
    decodificadores.registrar_incluidos(registro)
    cargar_complementos(registro, adaptadores, error=ErrorNormalizacion)
    return registro


def construir(configuracion: Configuracion) -> Normalizador:
    """El normalizador de una configuracion.

    Un complemento roto o un nombre desconocido se omiten y se avisan: un fallo de
    configuracion de la extension nunca tumba el proxy.
    """
    try:
        registro = construir_registro(configuracion.adaptadores)
    except ErrorNormalizacion as exc:
        logger.error("normalizacion: %s; se usan los decodificadores incluidos.", exc)
        registro = construir_registro()
    creados = []
    for nombre in configuracion.decodificadores:
        try:
            creados += registro.crear([nombre])
        except ErrorNormalizacion as exc:
            logger.error("normalizacion: %s; se omite.", exc)
    return Normalizador(creados)


# La configuracion se lee en cada llamada (barato) para poder cambiarla sin reiniciar
# las pruebas; el normalizador solo se reconstruye si cambia.
_lock = threading.Lock()
_actual: tuple[Configuracion, Normalizador] | None = None


def obtener() -> Normalizador | None:
    """El normalizador de la configuracion vigente, o None si esta apagada.

    Apagada es el estado por defecto: el proxy se comporta como siempre.
    """
    global _actual
    configuracion = Configuracion.desde_entorno(os.environ)
    if not configuracion.activa:
        return None
    with _lock:
        if _actual is None or _actual[0] != configuracion:
            _actual = (configuracion, construir(configuracion))
        return _actual[1]


def analizar(texto: str) -> Resultado | None:
    """Normaliza `texto` si la extension esta encendida; None si esta apagada.

    Si el analisis falla (un error de programacion, no del usuario) el mensaje sigue su
    camino sin normalizar y el resultado lo marca con `error`: la extension es una capa
    MAS, y que se rompa no debe tumbar el servicio. Se registra con su traza, sin el
    texto.
    """
    normalizador = obtener()
    if normalizador is None:
        return None
    try:
        return normalizador.analizar(texto)
    except Exception:  # noqa: BLE001 -- una capa adicional no debe tumbar /chat
        logger.exception("normalizacion: fallo el analisis; el mensaje sigue igual")
        return Resultado(texto_limpio=texto, error=True)


def descripcion() -> str:
    """Una linea para el log de arranque."""
    normalizador = obtener()
    if normalizador is None:
        return "APAGADA (NORMALIZACION_ENTRADA=1 para activarla)"
    return f"ACTIVA, decodificadores: {', '.join(normalizador.decodificadores)}"

"""La composicion: el unico lugar que lee el entorno y junta las piezas.

El dominio, los formatos y los transportes no saben que existe un `.env`. Aqui se lee la
configuracion en un objeto inmutable (`Configuracion`), se arma el registro (los
adaptadores incluidos mas los de `SIEM_ADAPTADORES`) y se construye el exportador.

Variables (ver `.env.example` y `docs/SIEM.md`):
    SIEM_DESTINOS       lista separada por comas de `[formato@]esquema://destino`
    SIEM_ARCHIVO_WAZUH  forma historica: equivale a `json@archivo://<ruta>`
    SIEM_ADAPTADORES    modulos de terceros que registran formatos o transportes
    SIEM_*, AWS_*       credenciales de cada destino (nunca en la URL)
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from proxy.complementos import cargar_complementos
from proxy.siem import formatos, transportes
from proxy.siem.exportador import Destino, ExportadorSIEM
from proxy.siem.puertos import ErrorSIEM
from proxy.siem.registro import RegistroSIEM
from proxy.siem.transportes.asincrono import ConectorAsincrono

logger = logging.getLogger(__name__)

# Las variables que llegan a los conectores: las propias del SIEM y las estandar de AWS.
_PREFIJOS_DE_ENTORNO = ("SIEM_", "AWS_")


@dataclass(frozen=True)
class Configuracion:
    """Todo lo que se configura por entorno, ya leido en un solo sitio.

    `entorno` (con las credenciales) no se imprime en ningun `repr`, pero SI cuenta al
    comparar: cambiar una clave reconstruye los destinos.
    """

    destinos: tuple[str, ...] = ()
    adaptadores: tuple[str, ...] = ()
    entorno: tuple[tuple[str, str], ...] = field(default=(), repr=False)

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str]) -> Configuracion:
        """Lee SIEM_DESTINOS, SIEM_ARCHIVO_WAZUH y SIEM_ADAPTADORES."""
        destinos = _lista(entorno.get("SIEM_DESTINOS", ""))
        archivo_historico = entorno.get("SIEM_ARCHIVO_WAZUH", "").strip()
        if archivo_historico:
            destinos = (f"json@archivo://{archivo_historico}", *destinos)
        propias = tuple(
            sorted(
                (clave, valor)
                for clave, valor in entorno.items()
                if clave.startswith(_PREFIJOS_DE_ENTORNO)
            )
        )
        return cls(
            destinos=destinos,
            adaptadores=_lista(entorno.get("SIEM_ADAPTADORES", "")),
            entorno=propias,
        )


def _lista(texto: str) -> tuple[str, ...]:
    return tuple(parte.strip() for parte in texto.split(",") if parte.strip())


def construir_registro(adaptadores: tuple[str, ...] = ()) -> RegistroSIEM:
    """Registro con los formatos y transportes incluidos y los de los modulos dados."""
    registro = RegistroSIEM()
    formatos.registrar_incluidos(registro)
    transportes.registrar_incluidos(registro)
    cargar_complementos(registro, adaptadores, error=ErrorSIEM)
    return registro


def construir(configuracion: Configuracion) -> ExportadorSIEM:
    """El exportador con sus destinos. Un destino mal configurado se omite y se avisa:
    un fallo de configuracion del SIEM nunca debe tumbar el proxy."""
    try:
        registro = construir_registro(configuracion.adaptadores)
    except ErrorSIEM as exc:
        logger.exception("SIEM: %s; se usan solo los adaptadores incluidos.", exc)
        registro = construir_registro()
    entorno = dict(configuracion.entorno)
    destinos: list[Destino] = []
    for texto in configuracion.destinos:
        try:
            resuelto = registro.resolver(texto, entorno)
        except ErrorSIEM as exc:
            # Se nombra el esquema, no el texto completo: podria traer un secreto.
            logger.exception(
                "SIEM: un destino (%s) no se pudo configurar y se omite: %s",
                texto.partition("://")[0],
                exc,
            )
            continue
        conector = (
            ConectorAsincrono(resuelto.conector, nombre=resuelto.descripcion)
            if resuelto.de_red
            else resuelto.conector
        )
        destinos.append(Destino(resuelto.descripcion, resuelto.formateador, conector))
    return ExportadorSIEM(destinos)


# La configuracion se lee en cada llamada (barato) para poder cambiarla sin reiniciar
# las pruebas ni recargar modulos; el exportador solo se reconstruye si cambia.
_lock = threading.Lock()
_actual: tuple[Configuracion, ExportadorSIEM] | None = None


def obtener() -> ExportadorSIEM | None:
    """El exportador de la configuracion vigente, o None si no hay destinos (por
    defecto: la exportacion esta apagada y el proxy se comporta como siempre)."""
    global _actual
    configuracion = Configuracion.desde_entorno(os.environ)
    with _lock:
        if _actual is not None and _actual[0] == configuracion:
            return _actual[1]
        if _actual is not None:
            _actual[1].cerrar()
            _actual = None
        if not configuracion.destinos:
            return None
        exportador = construir(configuracion)
        _actual = (configuracion, exportador)
        return exportador


def exportar_evento(evento: dict[str, Any]) -> None:
    """Exporta `evento` si hay destinos configurados. No lanza."""
    exportador = obtener()
    if exportador is not None:
        exportador.exportar(evento)


def cerrar() -> None:
    """Entrega lo pendiente y libera los conectores al apagar el proxy."""
    global _actual
    with _lock:
        if _actual is not None:
            _actual[1].cerrar()
            _actual = None

"""La composicion: el unico lugar que lee el entorno y junta las piezas.

El dominio, el servicio y los adaptadores no saben que existe un `.env`. Aqui se lee la
configuracion UNA vez en un objeto inmutable (`Configuracion`), se arma el registro de
adaptadores (los incluidos mas los que traiga `MEMORIA_RECHAZOS_ADAPTADORES`) y se
construye el servicio con su almacen inyectado.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass

import proxy.mecanismos as mecanismos
from proxy.memoria_decisiones.almacenes import registrar_incluidos
from proxy.memoria_decisiones.puerto import AlmacenMemoria, ErrorAlmacen
from proxy.memoria_decisiones.registro import RegistroAlmacenes, cargar_adaptadores
from proxy.memoria_decisiones.servicio import MAXIMO_POR_DEFECTO, MemoriaDecisiones

logger = logging.getLogger(__name__)

ALMACEN_POR_DEFECTO = "jsonl:///app/memoria/rechazos.jsonl"


@dataclass(frozen=True)
class Configuracion:
    """Todo lo que se configura por entorno, ya leido y validado en un solo sitio."""

    activa: bool = False
    almacen: str = ALMACEN_POR_DEFECTO
    maximo: int = MAXIMO_POR_DEFECTO
    vista_previa: bool = True
    adaptadores: tuple[str, ...] = ()

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str]) -> Configuracion:
        """Lee MEMORIA_RECHAZOS, _ALMACEN, _MAXIMO, _VISTA_PREVIA y _ADAPTADORES."""
        modulos = tuple(
            m.strip()
            for m in entorno.get("MEMORIA_RECHAZOS_ADAPTADORES", "").split(",")
            if m.strip()
        )
        return cls(
            activa=entorno.get("MEMORIA_RECHAZOS", "") == "1",
            almacen=entorno.get("MEMORIA_RECHAZOS_ALMACEN", "").strip()
            or ALMACEN_POR_DEFECTO,
            maximo=int(
                entorno.get("MEMORIA_RECHAZOS_MAXIMO", "") or MAXIMO_POR_DEFECTO
            ),
            vista_previa=entorno.get("MEMORIA_RECHAZOS_VISTA_PREVIA", "1") == "1",
            adaptadores=modulos,
        )


def redactar_credenciales(texto: str) -> str:
    """Reemplaza las credenciales del proyecto por `[REDACTADO]` (vista previa)."""
    return mecanismos.PATRON_CREDENCIAL_GENERICO.sub(mecanismos.TEXTO_REDACTADO, texto)


def construir_registro(adaptadores: tuple[str, ...] = ()) -> RegistroAlmacenes:
    """El registro con los adaptadores incluidos y los de los modulos indicados."""
    registro = RegistroAlmacenes()
    registrar_incluidos(registro)
    cargar_adaptadores(registro, adaptadores)
    return registro


def construir(configuracion: Configuracion) -> MemoriaDecisiones:
    """El servicio con su almacen. Si el almacen no se puede crear, queda solo en
    memoria y lo dice: un fallo de configuracion nunca debe tumbar el proxy."""
    almacen: AlmacenMemoria | None
    try:
        almacen = construir_registro(configuracion.adaptadores).crear(
            configuracion.almacen
        )
    except ErrorAlmacen as exc:
        logger.error("memoria de decisiones: %s; funciona SOLO en memoria.", exc)
        almacen = None
    return MemoriaDecisiones(
        almacen,
        redactor=redactar_credenciales,
        maximo=configuracion.maximo,
        con_vista_previa=configuracion.vista_previa,
    )


# La configuracion se lee una vez, al importar; las pruebas ponen una propia.
_configuracion = Configuracion.desde_entorno(os.environ)
_instancia: MemoriaDecisiones | None = None
_lock = threading.Lock()


def esta_activa() -> bool:
    """True si la extension esta encendida (`MEMORIA_RECHAZOS=1`)."""
    return _configuracion.activa


def obtener() -> MemoriaDecisiones | None:
    """La memoria compartida, o None si la extension esta apagada (por defecto)."""
    global _instancia
    if not _configuracion.activa:
        return None
    with _lock:
        if _instancia is None:
            _instancia = construir(_configuracion)
        return _instancia


def cerrar() -> None:
    """Libera el almacen al apagar el proxy."""
    global _instancia
    with _lock:
        if _instancia is not None:
            _instancia.cerrar()
            _instancia = None

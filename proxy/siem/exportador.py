"""El servicio: exporta un evento a todos los destinos, sin poder romper nada.

No conoce ningun SIEM, ningun formato ni el entorno: recibe sus destinos ya armados
(formateador + conector) y los recorre. Cada destino esta aislado de los demas: si
Splunk esta caido, Wazuh recibe el evento igual, y si todos fallan, `/chat` ni se
entera.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from proxy.siem.puertos import (
    Cerrable,
    ConectorSIEM,
    ErrorSIEM,
    FormateadorSIEM,
    enviar_a_siem,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Destino:
    """Un SIEM concreto: como se le escribe y por donde se le entrega."""

    descripcion: str  # `formato@esquema`; sin hosts ni credenciales: va al log
    formateador: FormateadorSIEM
    conector: ConectorSIEM


class ExportadorSIEM:
    """Entrega cada evento a todos sus destinos."""

    def __init__(self, destinos: Sequence[Destino]) -> None:
        self._destinos = tuple(destinos)

    @property
    def descripcion(self) -> str:
        """Los destinos activos, para el log de arranque."""
        return ", ".join(d.descripcion for d in self._destinos) or "ninguno"

    def exportar(self, evento: dict[str, Any]) -> None:
        """Formatea y entrega `evento` a cada destino. NUNCA lanza: el SIEM es un
        consumidor adicional y su fallo no puede tumbar la peticion ni el dataset."""
        for destino in self._destinos:
            self._exportar_a(destino, evento)

    def cerrar(self) -> None:
        """Entrega lo pendiente y libera los recursos de cada conector."""
        for destino in self._destinos:
            if isinstance(destino.conector, Cerrable):
                try:
                    destino.conector.cerrar()
                except Exception:  # noqa: BLE001 -- sigue con el resto
                    logger.exception("SIEM %s: fallo al cerrar", destino.descripcion)

    @staticmethod
    def _exportar_a(destino: Destino, evento: dict[str, Any]) -> None:
        try:
            enviar_a_siem(evento, destino.formateador, destino.conector)
        except ErrorSIEM as exc:
            # El mensaje de un ErrorSIEM ya es seguro (sin claves ni contenido).
            logger.error(
                "exportacion a SIEM fallida (el evento quedo en el dataset): %s: %s",
                destino.descripcion,
                exc,
            )
        except Exception:  # noqa: BLE001 -- el conector puede ser ajeno
            logger.exception(
                "exportacion a SIEM fallida (el evento quedo en el dataset): %s",
                destino.descripcion,
            )

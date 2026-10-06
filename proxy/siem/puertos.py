"""Los puertos de la exportacion a un SIEM: lo unico que el resto del proyecto conoce.

Formato y transporte son contratos SEPARADOS a proposito: varian de forma independiente
(dos SIEM pueden compartir transporte pero no formato, o al reves). Cada contrato es
pequeno -- un metodo -- para que quien conecte un SIEM nuevo no implemente nada que no
use.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class ErrorSIEM(Exception):
    """Cualquier fallo de la exportacion (configuracion, red, respuesta del SIEM).

    Los adaptadores traducen la excepcion de su controlador a esta: el resto del
    sistema captura una sola cosa. El mensaje NUNCA lleva claves, tokens ni el
    contenido del evento: se escribe en el log del servidor.

    `reintentable` es False cuando repetir no puede cambiar el resultado (una clave
    rechazada, una peticion mal formada): quien reintenta no pierde tiempo.
    """

    def __init__(self, mensaje: str, *, reintentable: bool = True) -> None:
        super().__init__(mensaje)
        self.reintentable = reintentable


@runtime_checkable
class FormateadorSIEM(Protocol):
    """Adapter de formato: el evento interno -> el mensaje que un SIEM espera."""

    def formatear(self, evento: dict[str, Any]) -> str:
        """Recibe el dict que arma `_construir_evento()` en `proxy/main.py` y devuelve
        el mensaje ya en el formato de cable (CEF, LEEF, JSON, ECS...)."""
        ...


@runtime_checkable
class ConectorSIEM(Protocol):
    """Adapter de transporte: entrega un mensaje ya formateado al SIEM real."""

    def enviar(self, mensaje: str) -> None:
        """Entrega `mensaje`. Falla de forma explicita con `ErrorSIEM` si la entrega no
        se pudo confirmar -- nunca en silencio (CLAUDE.md, seccion 7)."""
        ...


@runtime_checkable
class Cerrable(Protocol):
    """Lo que un conector expone ademas si guarda un recurso (socket, hilo, cliente)."""

    def cerrar(self) -> None:
        """Libera el recurso. Se puede llamar mas de una vez."""
        ...


def enviar_a_siem(
    evento: dict[str, Any], formateador: FormateadorSIEM, conector: ConectorSIEM
) -> None:
    """Formatea `evento` y lo entrega, sin conocer el SIEM concreto de los dos adapters.

    enviar_a_siem(evento, FormateadorCEF(), ConectorSyslog("siem", 514, "tcp"))
    """
    conector.enviar(formateador.formatear(evento))

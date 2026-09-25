"""Andamiaje (patron Adapter) para una futura integracion con un SIEM.

IronVeil es un framework, no un producto atado a un cliente concreto: no se
sabe todavia que SIEM va a usar quien lo despliegue (Wazuh, Splunk, Elastic,
Sentinel, ...), ni siquiera si el formato de log interno de IronVeil (el
esquema de 8 campos base + extendidos, ver skill esquema-log) va a seguir
siendo el mismo dentro de un ano. Este modulo existe para que esas dos cosas
puedan cambiar de forma independiente, sin que el codigo del proxy tenga que
saber cual SIEM hay detras:

- `FormateadorSIEM`: adapta el evento interno al formato de cable que un
  SIEM concreto espera (CEF, LEEF, ECS, JSON plano, etc.).
- `ConectorSIEM`: adapta la entrega del mensaje ya formateado al transporte
  real (HTTP, syslog, un archivo que un agente vigila, etc.).

Los dos son adapters SEPARADOS a proposito: formato y transporte varian de
forma independiente (dos SIEM pueden compartir transporte pero no formato,
o viceversa). Quien conecte un SIEM real implementa las dos interfaces UNA
vez cada una, sin tocar `proxy/main.py` -- ver `enviar_a_siem()`.

IMPORTANTE -- todavia NO esta cableado a `/chat`: `_registrar_evento()` en
`proxy/main.py` sigue siendo la unica escritura real, hacia
`resultados/<fecha>/eventos.jsonl` (el dataset del experimento, protegido
por la regla 4 de CLAUDE.md -- nunca se edita a mano ni se mezcla con otra
cosa). Conectar esto de verdad a `/chat` es tarea de Piedrahita (reparto de
equipo, CLAUDE.md seccion 8, "export SIEM"): aqui solo queda la interfaz
lista para que ella (o quien sea) la use sin tener que disenarla desde cero,
decidiendo en ese momento si el envio al SIEM es sincrono, en un hilo aparte,
o en background -- una decision de esa integracion, no de este andamiaje.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FormateadorSIEM(Protocol):
    """Adapter: convierte un evento interno de IronVeil al formato de cable
    de un SIEM concreto.

    Cualquier objeto con un metodo `formatear(evento) -> str` satisface esta
    interfaz (typing estructural de `Protocol`, no hace falta heredar de
    nada) -- asi un adapter para un SIEM real puede envolver directamente el
    SDK de ese SIEM sin una capa de mas.
    """

    def formatear(self, evento: dict[str, Any]) -> str:
        """Recibe el mismo dict que ya arma `_construir_evento()` en
        `proxy/main.py` (esquema de 8 campos base + los extendidos que
        apliquen) y devuelve el mensaje ya en el formato que espera el SIEM
        destino."""
        ...


@runtime_checkable
class ConectorSIEM(Protocol):
    """Adapter: entrega un mensaje ya formateado al SIEM real."""

    def enviar(self, mensaje: str) -> None:
        """Entrega `mensaje` (ya formateado por un `FormateadorSIEM`) al
        SIEM. Debe fallar de forma explicita (excepcion), nunca en
        silencio, si la entrega no se pudo confirmar -- mismo criterio de
        "nada de pass silencioso" de CLAUDE.md seccion 7."""
        ...


def enviar_a_siem(
    evento: dict[str, Any], formateador: FormateadorSIEM, conector: ConectorSIEM
) -> None:
    """Punto de entrada unico: formatea `evento` y lo entrega, sin que quien
    llama necesite conocer el SIEM concreto detras de los dos adapters.

    Uso previsto una vez que alguien conecte un SIEM real (ejemplo, no
    implementado aqui):

        enviar_a_siem(evento, FormateadorCEF(), ConectorSyslogWazuh(host, puerto))
    """
    conector.enviar(formateador.formatear(evento))


# --- Adapters de referencia -------------------------------------------------
#
# No son solo placeholders para probar el patron: son implementaciones
# validas por si mismas (JSON plano + archivo local es exactamente como
# muchos SIEM, incluido Wazuh via su modulo de lectura de logs, ingieren
# eventos). Sirven de ejemplo minimo de como implementar las dos interfaces
# de arriba antes de que exista una integracion con un SIEM real.


class FormateadorJSON:
    """Formateador de referencia: el evento tal cual, como JSON de una linea."""

    def formatear(self, evento: dict[str, Any]) -> str:
        return json.dumps(evento, ensure_ascii=False)


class ConectorArchivoLocal:
    """Conector de referencia: agrega el mensaje a un archivo local (JSON
    Lines, una linea por evento).

    Escribe en un archivo APARTE de `resultados/<fecha>/eventos.jsonl` a
    proposito: ese archivo es el dataset crudo del experimento (regla 4 de
    CLAUDE.md), y un consumidor de SIEM es un destino distinto, no debe
    mezclarse con la evidencia cruda ni competir por el mismo lock
    (`_registro_lock` en `proxy/main.py` protege solo ese archivo).
    """

    def __init__(self, ruta: Path) -> None:
        self._ruta = ruta

    def enviar(self, mensaje: str) -> None:
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._ruta.open("a", encoding="utf-8") as f:
            f.write(mensaje + "\n")

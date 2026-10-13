"""Lectura de credenciales desde el entorno que la composicion inyecta.

Los conectores NO leen `os.environ`: reciben un mapa ya armado. Esto solo ayuda a
pedir las variables que necesitan y a fallar con un mensaje que dice CUALES faltan
(los nombres, nunca los valores).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from proxy.siem.puertos import ErrorSIEM

# host o host:puerto (nombre DNS o IPv4; los literales IPv6 no se soportan). Rechaza
# rutas, comillas, espacios y '@': lo que llegue aqui acaba dentro de una URL.
_NOMBRE_DE_HOST = r"[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?"
_HOST = re.compile(rf"^(?P<host>{_NOMBRE_DE_HOST})(?::(?P<puerto>\d{{1,5}}))?$")


def requerir(entorno: Mapping[str, str], *nombres: str) -> dict[str, str]:
    """Los valores de esas variables; `ErrorSIEM` si falta alguna o esta vacia."""
    faltan = [n for n in nombres if not entorno.get(n, "").strip()]
    if faltan:
        raise ErrorSIEM(
            f"faltan variables de entorno para este destino SIEM: {', '.join(faltan)}",
            reintentable=False,
        )
    return {n: entorno[n].strip() for n in nombres}


def separar_host_puerto(
    texto: str, *, puerto_por_defecto: int | None
) -> tuple[str, int]:
    """`host` o `host:puerto` -> (host, puerto). `ErrorSIEM` si no es un host valido."""
    coincide = _HOST.match(texto.strip())
    if coincide is None:
        raise ErrorSIEM(
            "host de destino SIEM no valido: se espera host o host:puerto",
            reintentable=False,
        )
    puerto = coincide["puerto"]
    if puerto is None:
        if puerto_por_defecto is None:
            raise ErrorSIEM("el destino SIEM necesita un puerto", reintentable=False)
        return coincide["host"], puerto_por_defecto
    if not 0 < int(puerto) <= 65535:
        raise ErrorSIEM(f"puerto fuera de rango: {puerto}", reintentable=False)
    return coincide["host"], int(puerto)

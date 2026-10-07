"""Rutas de la linea de comandos: solo se aceptan dentro del proyecto o de /tmp.

Un argumento como `--salida ../../algo` o un enlace simbolico no debe sacar a un script
de analisis fuera del repositorio (path traversal). Se resuelve la ruta real y se exige
que quede dentro de una carpeta permitida. Solo biblioteca estandar.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class ErrorRutaNoPermitida(ValueError):
    """La ruta, ya resuelta, queda fuera de las carpetas permitidas."""


def carpetas_permitidas() -> tuple[Path, ...]:
    """El repositorio y la carpeta temporal del sistema (donde escriben las pruebas)."""
    return (RAIZ, Path(tempfile.gettempdir()))


def _esta_dentro(candidata: str, base: Path) -> bool:
    raiz = os.path.realpath(base)
    try:
        return os.path.commonpath([candidata, raiz]) == raiz
    except ValueError:  # unidades distintas en Windows
        return False


def ruta_permitida(ruta: Path | str, *bases: Path) -> Path:
    """La ruta real de `ruta`, o `ErrorRutaNoPermitida` si queda fuera de `bases`.

    Sin `bases`, vale el repositorio o la carpeta temporal. No dice cual era la ruta
    pedida mas alla de lo que el usuario ya escribio.
    """
    candidata = os.path.realpath(ruta)
    if any(_esta_dentro(candidata, base) for base in bases or carpetas_permitidas()):
        return Path(candidata)
    raise ErrorRutaNoPermitida(
        f"La ruta {str(ruta)!r} queda fuera del proyecto: "
        "usa una carpeta del repositorio."
    )

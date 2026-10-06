"""Carga de complementos: modulos de terceros que registran sus propios adaptadores.

Lo comparten todos los puntos de extension de IronVeil (almacenes de la memoria de
decisiones, formatos y transportes del SIEM...): cada uno tiene su registro y su error,
pero la regla de como se importa un complemento es una sola. Un complemento expone
`registrar(registro)` y se lista por nombre de modulo en una variable de `.env`.

Solo se aceptan NOMBRES de modulo (nada de rutas ni de expresiones), y el modulo se
importa y se ejecuta con los permisos del proxy: solo codigo de confianza.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Iterable
from typing import Any

_NOMBRE_DE_MODULO = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$")


def cargar_complementos(
    registro: Any, modulos: Iterable[str], *, error: type[Exception]
) -> None:
    """Importa cada modulo y deja que registre sus adaptadores (`registrar(registro)`).

    Cualquier fallo se convierte en `error` con un mensaje que dice cual modulo y por
    que; quien llama decide que hacer (los dos usos siguen funcionando y avisan).
    """
    for nombre in modulos:
        if not _NOMBRE_DE_MODULO.match(nombre):
            raise error(f"{nombre!r} no es un nombre de modulo valido.")
        try:
            modulo = importlib.import_module(nombre)
        except ImportError as exc:
            raise error(f"no se pudo importar el modulo {nombre!r}: {exc}") from exc
        registrar = getattr(modulo, "registrar", None)
        if not callable(registrar):
            raise error(f"el modulo {nombre!r} no define registrar(registro).")
        try:
            registrar(registro)
        except error:
            raise
        except Exception as exc:  # noqa: BLE001 -- un complemento puede fallar como sea
            raise error(
                f"registrar() de {nombre!r} fallo ({type(exc).__name__}): {exc}"
            ) from exc

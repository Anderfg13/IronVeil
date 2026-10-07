"""Decodificador de Base64 (y de su variante segura para URL)."""

from __future__ import annotations

import base64
import re

from proxy.normalizacion.dominio import es_imprimible

# 12 bytes: por debajo, casi todo son palabras y no codificacion.
LARGO_MINIMO_TRAMO = 16
# Un tramo de al menos LARGO_MINIMO_TRAMO caracteres del alfabeto Base64 (estandar o
# seguro para URL), con hasta dos «=» de relleno, y sin mas caracteres del alfabeto
# pegados a los lados. El guion va aparte, al final de cada clase.
_ALFABETO = r"A-Za-z0-9+/_"
_TRAMO = re.compile(
    rf"(?<![{_ALFABETO}\-])[{_ALFABETO}\-]{{{LARGO_MINIMO_TRAMO},}}"
    rf"={{0,2}}(?![{_ALFABETO}=\-])"
)


def _decodificar_tramo(tramo: str) -> str | None:
    """El texto de un tramo Base64, o None si no es valido o no es imprimible."""
    sin_relleno = tramo.rstrip("=")
    estandar = sin_relleno.replace("-", "+").replace("_", "/")
    relleno = "=" * (-len(estandar) % 4)
    try:
        crudo = base64.b64decode(estandar + relleno, validate=True)
        texto = crudo.decode("utf-8")
    except ValueError:  # binascii.Error y UnicodeDecodeError son ValueError
        return None
    return texto if es_imprimible(texto) else None


class DecodificadorBase64:
    """Decodifica los tramos Base64 de un texto que resultan ser imprimibles."""

    nombre = "base64"

    def decodificar(self, texto: str) -> list[str]:
        decodificados = (_decodificar_tramo(t) for t in _TRAMO.findall(texto))
        return [d for d in decodificados if d is not None]

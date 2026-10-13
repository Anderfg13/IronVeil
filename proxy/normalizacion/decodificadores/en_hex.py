"""Decodificador de hexadecimal, pegado (`69676e6f`) o con separadores (`69 67 6e`)."""

from __future__ import annotations

import re

from proxy.normalizacion.dominio import es_imprimible

BYTES_MINIMOS = 8
_DIGITO = r"[0-9A-Fa-f]"
# Al menos BYTES_MINIMOS bytes: digitos seguidos, o pares separados por espacio, dos
# puntos o guion; y sin mas digitos hexadecimales pegados a los lados.
_TRAMO = re.compile(
    rf"(?<!{_DIGITO})"
    rf"(?:(?:{_DIGITO}{{2}}){{{BYTES_MINIMOS},}}"
    rf"|(?:{_DIGITO}{{2}}[ :-]){{{BYTES_MINIMOS - 1},}}{_DIGITO}{{2}})"
    rf"(?!{_DIGITO})"
)
_SEPARADORES = re.compile(r"[ :-]")


def _decodificar_tramo(tramo: str) -> str | None:
    """El texto de un tramo hexadecimal, o None si no es imprimible."""
    try:
        texto = bytes.fromhex(_SEPARADORES.sub("", tramo)).decode("utf-8")
    except ValueError:  # digitos impares o bytes que no son UTF-8
        return None
    return texto if es_imprimible(texto) else None


class DecodificadorHex:
    """Decodifica los tramos hexadecimales de un texto que son imprimibles."""

    nombre = "hex"

    def decodificar(self, texto: str) -> list[str]:
        decodificados = (_decodificar_tramo(t) for t in _TRAMO.findall(texto))
        return [d for d in decodificados if d is not None]

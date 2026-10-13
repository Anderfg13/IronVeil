"""Los decodificadores que trae IronVeil (otros se agregan: `registro.py`)."""

from __future__ import annotations

from proxy.normalizacion.decodificadores.en_base64 import DecodificadorBase64
from proxy.normalizacion.decodificadores.en_hex import DecodificadorHex
from proxy.normalizacion.decodificadores.en_rot13 import DecodificadorRot13
from proxy.normalizacion.registro import RegistroDecodificadores

__all__ = [
    "DecodificadorBase64",
    "DecodificadorHex",
    "DecodificadorRot13",
    "registrar_incluidos",
]


def registrar_incluidos(registro: RegistroDecodificadores) -> None:
    """Registra `base64`, `hex` y `rot13`."""
    for decodificador in (DecodificadorBase64, DecodificadorHex, DecodificadorRot13):
        registro.registrar(decodificador.nombre, decodificador)

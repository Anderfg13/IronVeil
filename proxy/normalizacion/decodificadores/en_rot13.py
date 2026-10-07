"""Decodificador de ROT13 sobre el mensaje completo.

ROT13 no tiene un tramo que reconocer (cualquier letra es valida), asi que se prueba con
todo el mensaje y se acepta solo si el resultado parece lenguaje natural y el original
NO lo parecia: asi un mensaje normal no genera una variante falsa.
"""

from __future__ import annotations

import codecs

from proxy.normalizacion.dominio import (
    FACTOR_MEJORA_DE_IDIOMA,
    PROPORCION_IDIOMA_MINIMA,
    puntaje_idioma,
)


class DecodificadorRot13:
    """Devuelve el ROT13 del mensaje si ese es el texto legible y el original no."""

    nombre = "rot13"

    def decodificar(self, texto: str) -> list[str]:
        rotado = codecs.encode(texto, "rot13")
        mejora = puntaje_idioma(rotado)
        if (
            rotado != texto
            and mejora >= PROPORCION_IDIOMA_MINIMA
            and mejora >= FACTOR_MEJORA_DE_IDIOMA * puntaje_idioma(texto)
        ):
            return [rotado]
        return []

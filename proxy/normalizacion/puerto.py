"""El puerto de la normalizacion: lo unico que el servicio sabe de una codificacion.

Un decodificador es un objeto con un `nombre` y un metodo: se agrega uno nuevo (otra
codificacion, la de una empresa) sin tocar el servicio ni a los demas.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class ErrorNormalizacion(Exception):
    """Un fallo de configuracion de la normalizacion (decodificador desconocido,
    complemento que no carga). El mensaje nunca lleva texto del usuario."""


@runtime_checkable
class Decodificador(Protocol):
    """Encuentra en un texto los tramos codificados y los devuelve decodificados."""

    nombre: str

    def decodificar(self, texto: str) -> list[str]:
        """Las cadenas imprimibles que salen de decodificar tramos de `texto`.

        Devuelve una lista vacia si no hay nada. Solo se devuelve lo que es UTF-8
        imprimible: un hash o un identificador decodifican a bytes al azar y no se
        devuelven. Que merezca inspeccionarse (que parezca lenguaje) lo decide el
        servicio, no el decodificador. No debe lanzar por una entrada rara.
        """
        ...

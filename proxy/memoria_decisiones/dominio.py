"""Reglas de negocio de la memoria de decisiones: que es una regla y como se compara.

Sin E/S, sin entorno y sin base de datos. Es la capa de la que depende todo lo demas y
no depende de nada del proyecto: por eso se puede probar sola y no cambia cuando cambia
donde se guardan las reglas.
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

# Motivos de retencion que SI se recuerdan: los de contenido. Los de tasa y las
# herramientas no (un mensaje retenido por volumen puede ser perfectamente legitimo).
MOTIVOS_QUE_SE_RECUERDAN = frozenset({"filtrado", "clasificacion", "minimo_privilegio"})
LARGO_VISTA_PREVIA = 60
_PUNTUACION_DE_BORDE = " .,;:!?¡¿\"'"


class Resultado(StrEnum):
    """Que paso al intentar recordar un rechazo (tambien lo ve la consola)."""

    RECORDADA = "recordada"
    YA_RECORDADA = "ya_recordada"
    MEMORIA_LLENA = "memoria_llena"
    RECORDADA_SIN_GUARDAR = "recordada_sin_guardar"  # vale hasta reiniciar


def normalizar(texto: str) -> str:
    """Forma canonica para comparar: sin mayusculas, tildes, espacios de mas ni
    caracteres invisibles (ceros de ancho cero, marcas de direccion)."""
    t = unicodedata.normalize("NFKC", texto)
    t = "".join(c for c in t if unicodedata.category(c) != "Cf")
    t = unicodedata.normalize("NFD", t.casefold())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.split()).strip(_PUNTUACION_DE_BORDE)


def huella(modelo: str, texto: str) -> str:
    """SHA-256 del par (modelo, texto normalizado): la regla es por modelo."""
    clave = f"{modelo.strip().casefold()}\x00{normalizar(texto)}"
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()


def vista_previa(texto: str, redactor: Callable[[str], str]) -> str:
    """Primeros caracteres del mensaje, ya pasados por `redactor` (que debe quitar las
    credenciales: el dominio no sabe que formato tienen).

    Se redacta ANTES de recortar: asi una credencial que el corte partiria por la mitad
    nunca queda a medias en la vista previa.
    """
    limpio = redactor(" ".join(texto.split()))
    return limpio[:LARGO_VISTA_PREVIA] + (
        "…" if len(limpio) > LARGO_VISTA_PREVIA else ""
    )


@dataclass(frozen=True)
class Regla:
    """Un rechazo recordado. Nunca lleva el mensaje completo."""

    huella: str
    modelo: str
    decidido_por: str
    decidido_en: str
    motivo: str
    vista_previa: str | None = None

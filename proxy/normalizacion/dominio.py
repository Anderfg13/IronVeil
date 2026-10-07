"""Reglas de la normalizacion de entrada: que es «invisible» y que es «texto legible».

Sin E/S, sin entorno y sin conocer ningun decodificador concreto. Lo comparten el
servicio y los decodificadores: por eso se prueba solo y no cambia cuando se agrega una
codificacion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Code points que no se ven y sirven para esconder instrucciones a quien revisa el
# mensaje. NO se tocan U+200C ni U+200D (unen letras en varios alfabetos y emojis):
# quitarlos deformaria texto legitimo; queda como limite en la guia de la extension.
_RANGOS_INVISIBLES: tuple[tuple[int, int], ...] = (
    (0xE0000, 0xE007F),  # bloque «Tags»: ASCII invisible (el probe goodside.Tag)
    (0xFE00, 0xFE0F),  # selectores de variacion
    (0xE0100, 0xE01EF),  # selectores de variacion suplementarios
    (0x200B, 0x200B),  # espacio de ancho cero
    (0x2060, 0x2064),  # word joiner e invisibles matematicos
    (0xFEFF, 0xFEFF),  # marca de orden de bytes / espacio de ancho cero
    (0x00AD, 0x00AD),  # guion blando
    (0x200E, 0x200F),  # marcas de direccion
    (0x202A, 0x202E),  # controles de direccion incrustada
    (0x2066, 0x2069),  # aislados de direccion
    (0x061C, 0x061C),  # marca de letra arabe
)
_BLOQUE_TAGS_ASCII = (0xE0020, 0xE007E)  # imprimibles ASCII codificados como «tags»
_DESPLAZAMIENTO_TAGS = 0xE0000

LARGO_MINIMO_TEXTO = 6
PROPORCION_IMPRIMIBLE_MINIMA = 0.95
PROPORCION_LETRAS_MINIMA = 0.6
PALABRAS_MINIMAS_DE_IDIOMA = 3
PROPORCION_IDIOMA_MINIMA = 0.2
FACTOR_MEJORA_DE_IDIOMA = 2.0

# Palabras muy frecuentes en espanol e ingles, incluidas las que abundan en peticiones
# a un asistente. Solo sirven para decidir si un texto «parece lenguaje natural» (p. ej.
# para saber si el ROT13 de un mensaje es legible); no clasifican nada como ataque.
_PALABRAS_EN = (
    "the and you that for with this have not are was your all any from they will what "
    "when who how can please tell show give ignore previous instructions system prompt "
    "print say follow forget reveal about into than then them these those would could "
    "should"
)
_PALABRAS_ES = (
    "el la los las un una unos unas de del que y a en es se no te lo le su por con "
    "para como mas pero sus al ya todo esta este esto estos estas son fue ser hay muy "
    "tus mis mi tu me dime muestra ignora todas todos anteriores instrucciones sistema "
    "revela olvida"
)
PALABRAS_COMUNES = frozenset((_PALABRAS_EN + " " + _PALABRAS_ES).split())
_PALABRAS = re.compile(r"[a-záéíóúüñ]+")


@dataclass(frozen=True)
class Hallazgo:
    """Una codificacion encontrada. Solo cuenta: nunca guarda texto del usuario."""

    codificacion: str
    caracteres: int  # largo del texto decodificado


@dataclass(frozen=True)
class Resultado:
    """Lo que la normalizacion saca de un mensaje."""

    texto_limpio: str  # el mensaje sin caracteres invisibles: lo que ve el modelo
    invisibles_eliminados: int = 0
    hallazgos: tuple[Hallazgo, ...] = ()
    variante: str = ""  # lo decodificado, junto: se inspecciona como un texto mas
    truncada: bool = False  # se alcanzo un limite y quedo algo sin decodificar
    error: bool = False  # el analisis fallo: el mensaje sigue sin normalizar

    def como_dict(self) -> dict[str, Any]:
        """El bloque `normalizacion` del evento: conteos, nunca texto."""
        cuenta: dict[str, int] = {}
        for hallazgo in self.hallazgos:
            cuenta[hallazgo.codificacion] = cuenta.get(hallazgo.codificacion, 0) + 1
        datos: dict[str, Any] = {
            "invisibles_eliminados": self.invisibles_eliminados,
            "decodificaciones": cuenta,
            "variante_inspeccionada": bool(self.variante),
        }
        if self.truncada:
            datos["truncada"] = True
        if self.error:
            datos["error"] = True
        return datos


def es_invisible(caracter: str) -> bool:
    """True si `caracter` es uno de los code points que no se ven."""
    punto = ord(caracter)
    return any(bajo <= punto <= alto for bajo, alto in _RANGOS_INVISIBLES)


def eliminar_invisibles(texto: str) -> tuple[str, int]:
    """(texto sin invisibles, cuantos se quitaron)."""
    visibles = [c for c in texto if not es_invisible(c)]
    return "".join(visibles), len(texto) - len(visibles)


def texto_oculto_en_tags(texto: str) -> str:
    """El ASCII que esconden los caracteres del bloque «Tags».

    Son invisibles para una persona, pero un modelo puede leerlos: cada uno es el
    caracter ASCII mas 0xE0000.
    """
    bajo, alto = _BLOQUE_TAGS_ASCII
    return "".join(
        chr(ord(c) - _DESPLAZAMIENTO_TAGS) for c in texto if bajo <= ord(c) <= alto
    )


def es_imprimible(candidato: str) -> bool:
    """True si `candidato` es una cadena imprimible de largo suficiente.

    Es lo minimo para seguir decodificando sobre un resultado: un hash o un
    identificador decodifican a bytes al azar (no UTF-8, o con caracteres de
    control), y eso se descarta aqui.
    """
    if len(candidato) < LARGO_MINIMO_TEXTO:
        return False
    imprimibles = sum(c.isprintable() or c in "\n\r\t" for c in candidato)
    return imprimibles / len(candidato) >= PROPORCION_IMPRIMIBLE_MINIMA


def parece_texto(candidato: str) -> bool:
    """True si `candidato` parece lenguaje y no una cadena de digitos o simbolos.

    Es lo que se exige para INSPECCIONAR algo decodificado (la capa intermedia de
    un Base64 dentro de un hex es una cadena de digitos: se sigue decodificando,
    pero no se inspecciona).
    """
    letras = sum(c.isalpha() or c.isspace() for c in candidato)
    return (
        es_imprimible(candidato) and letras / len(candidato) >= PROPORCION_LETRAS_MINIMA
    )


def puntaje_idioma(texto: str) -> float:
    """Fraccion de palabras comunes en espanol o ingles (0 con muy pocas palabras)."""
    palabras = _PALABRAS.findall(texto.lower())
    if len(palabras) < PALABRAS_MINIMAS_DE_IDIOMA:
        return 0.0
    return sum(p in PALABRAS_COMUNES for p in palabras) / len(palabras)

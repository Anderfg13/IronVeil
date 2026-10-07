"""El servicio: quita lo invisible y decodifica lo codificado, sin saber como.

Recibe sus decodificadores ya armados (inyectados) y es una funcion pura del texto: sin
red, sin archivos, sin entorno. Devuelve un `Resultado`; que se hace con el (bloquear,
registrar) lo decide quien lo llama.
"""

from __future__ import annotations

from collections.abc import Sequence

from proxy.normalizacion.dominio import (
    Hallazgo,
    Resultado,
    eliminar_invisibles,
    parece_texto,
    texto_oculto_en_tags,
)
from proxy.normalizacion.puerto import Decodificador

# Base64 dentro de Base64: hasta dos capas.
PROFUNDIDAD_MAXIMA = 2
# Tramos decodificados por mensaje: un tope contra mensajes hechos para saturar.
MAXIMO_DECODIFICACIONES = 64
MAXIMO_CARACTERES_VARIANTE = 50_000
_SEPARADOR_DE_VARIANTE = "\n"
CODIFICACION_TAGS = "tags_unicode"


class Normalizador:
    """Analiza un mensaje: texto limpio, texto escondido en caracteres invisibles y
    tramos codificados ya decodificados."""

    def __init__(
        self,
        decodificadores: Sequence[Decodificador],
        *,
        profundidad_maxima: int = PROFUNDIDAD_MAXIMA,
        maximo_decodificaciones: int = MAXIMO_DECODIFICACIONES,
        maximo_caracteres: int = MAXIMO_CARACTERES_VARIANTE,
    ) -> None:
        self._decodificadores = tuple(decodificadores)
        self._profundidad = profundidad_maxima
        self._maximo_decodificaciones = maximo_decodificaciones
        self._maximo_caracteres = maximo_caracteres

    @property
    def decodificadores(self) -> tuple[str, ...]:
        """Los nombres activos, para el log de arranque."""
        return tuple(d.nombre for d in self._decodificadores)

    def analizar(self, texto: str) -> Resultado:
        """El resultado de normalizar `texto`. No lanza por ningun contenido."""
        limpio, invisibles = eliminar_invisibles(texto)
        hallazgos: list[Hallazgo] = []
        variantes: list[str] = []

        oculto = texto_oculto_en_tags(texto)
        if oculto:
            hallazgos.append(Hallazgo(CODIFICACION_TAGS, len(oculto)))
            variantes.append(oculto)

        truncada = self._decodificar_en_capas(limpio, hallazgos, variantes)
        variante = _SEPARADOR_DE_VARIANTE.join(variantes)
        if len(variante) > self._maximo_caracteres:
            variante, truncada = variante[: self._maximo_caracteres], True
        return Resultado(
            texto_limpio=limpio,
            invisibles_eliminados=invisibles,
            hallazgos=tuple(hallazgos),
            variante=variante,
            truncada=truncada,
        )

    def _decodificar_en_capas(
        self, texto: str, hallazgos: list[Hallazgo], variantes: list[str]
    ) -> bool:
        """Decodifica `texto` y, hasta la profundidad maxima, lo que salga de ahi.

        Se sigue decodificando sobre cualquier resultado imprimible (la capa de en
        medio de un Base64 dentro de un hex es una cadena de digitos), pero solo lo
        que PARECE lenguaje va a las variantes que se inspeccionan. Devuelve True si
        se alcanzo el tope de decodificaciones (quedo algo sin mirar).
        """
        vistos = {texto}
        capa = [texto]
        for _ in range(self._profundidad):
            siguiente: list[str] = []
            for fuente in capa:
                for decodificador in self._decodificadores:
                    for decodificado in decodificador.decodificar(fuente):
                        if decodificado in vistos:
                            continue
                        if len(hallazgos) >= self._maximo_decodificaciones:
                            return True
                        vistos.add(decodificado)
                        hallazgos.append(
                            Hallazgo(decodificador.nombre, len(decodificado))
                        )
                        if parece_texto(decodificado):
                            variantes.append(decodificado)
                        siguiente.append(decodificado)
            if not siguiente:
                break
            capa = siguiente
        return False

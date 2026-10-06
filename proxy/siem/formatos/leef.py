"""LEEF 1.0 (IBM QRadar Log Event Extended Format).

Cabecera `LEEF:1.0|Fabricante|Producto|Version|IdEvento|` y despues atributos
`clave=valor` separados por TABULADOR. Los atributos de IronVeil viajan con su propio
nombre (LEEF admite claves propias); `cat` y `sev` son las reservadas del formato.
"""

from __future__ import annotations

from typing import Any, ClassVar

from proxy.siem.evento import (
    FABRICANTE,
    PRODUCTO,
    VERSION_PRODUCTO,
    aplanar_listas,
    clasificar_resultado,
    sin_nulos,
    validar_evento,
)

_VERSION = "1.0"
_SEPARADOR = "\t"


def _escapar_cabecera(valor: str) -> str:
    """En la cabecera LEEF la barra vertical separa campos."""
    return valor.replace("\\", "\\\\").replace("|", "\\|")


def _escapar_atributo(valor: str) -> str:
    """Un tabulador o un salto de linea romperian el atributo: se vuelven un espacio."""
    return " ".join(valor.replace("\t", " ").split())


class FormateadorLEEF:
    """Una linea LEEF 1.0 con todos los campos escalares del evento."""

    tipo_contenido: ClassVar[str] = "text/plain"

    def formatear(self, evento: dict[str, Any]) -> str:
        validar_evento(evento)
        clasificacion = clasificar_resultado(evento)
        cabecera = "|".join(
            _escapar_cabecera(parte)
            for parte in (
                f"LEEF:{_VERSION}",
                FABRICANTE,
                PRODUCTO,
                VERSION_PRODUCTO,
                clasificacion.id_firma,
            )
        )
        atributos = {
            "cat": str(evento["resultado"]),
            "sev": str(clasificacion.severidad),
        }
        for clave, valor in sin_nulos(aplanar_listas(evento)).items():
            atributos.setdefault(clave, str(valor))
        cuerpo = _SEPARADOR.join(
            f"{clave}={_escapar_atributo(valor)}" for clave, valor in atributos.items()
        )
        return f"{cabecera}|{cuerpo}"

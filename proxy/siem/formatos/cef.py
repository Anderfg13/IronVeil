"""CEF (ArcSight Common Event Format): lo entienden Sentinel, Splunk, QRadar y casi
todos los SIEM comerciales, normalmente por syslog."""

from __future__ import annotations

from typing import Any, ClassVar

from proxy.siem.evento import (
    FABRICANTE,
    PRODUCTO,
    VERSION_PRODUCTO,
    aplanar_listas,
    clasificar_resultado,
    epoch_ms,
    es_entero,
    validar_evento,
)

_VERSION = "0"

# campo del evento -> (clave CEF de usuario, etiqueta). CEF no tiene claves estandar
# para los campos de IronVeil: se usan csN (texto) y cnN (entero), cada una con su
# `...Label`. Los campos extendidos no listados aqui solo viajan en los otros formatos.
_NUMERICOS: dict[str, tuple[str, str]] = {
    "latencia_ms": ("cn1", "latencia_ms"),
    "latencia_clasificador_ms": ("cn2", "latencia_clasificador_ms"),
    "tiempo_revision_humana_ms": ("cn3", "tiempo_revision_humana_ms"),
}

_TEXTOS: dict[str, tuple[str, str]] = {
    "configuracion": ("cs1", "configuracion"),
    "vector_probado": ("cs2", "vector_probado"),
    "modelo_destino": ("cs3", "modelo_destino"),
    "mecanismo_que_bloqueo": ("cs4", "mecanismo_que_bloqueo"),
    "mecanismos_activos": ("cs5", "mecanismos_activos"),
    "tipo_variante": ("cs6", "tipo_variante"),
}


def _escapar_cabecera(valor: str) -> str:
    """En la cabecera CEF hay que escapar la barra invertida y `|`."""
    return valor.replace("\\", "\\\\").replace("|", "\\|")


def _escapar_extension(valor: str) -> str:
    """En la extension CEF hay que escapar la barra invertida, `=` y los saltos de linea
    (estos ultimos como la secuencia literal `\\n`)."""
    return (
        valor.replace("\\", "\\\\")
        .replace("=", "\\=")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )


class FormateadorCEF:
    """Una linea `CEF:0|Vendor|Product|Version|Firma|Nombre|Severidad|extension`."""

    tipo_contenido: ClassVar[str] = "text/plain"

    def formatear(self, evento: dict[str, Any]) -> str:
        validar_evento(evento)
        clasificacion = clasificar_resultado(evento)
        cabecera = "|".join(
            _escapar_cabecera(parte)
            for parte in (
                f"CEF:{_VERSION}",
                FABRICANTE,
                PRODUCTO,
                VERSION_PRODUCTO,
                clasificacion.id_firma,
                clasificacion.nombre,
                str(clasificacion.severidad),
            )
        )
        return f"{cabecera}|{' '.join(self._extension(evento))}"

    @staticmethod
    def _extension(evento: dict[str, Any]) -> list[str]:
        pares: list[str] = []
        marca_tiempo = epoch_ms(str(evento["timestamp"]))
        if marca_tiempo is not None:
            pares.append(f"rt={marca_tiempo}")
        pares.append(f"act={_escapar_extension(str(evento['resultado']))}")
        plano = aplanar_listas(evento)
        for campo, (clave, etiqueta) in _TEXTOS.items():
            if plano.get(campo) is not None:
                pares.append(f"{clave}Label={etiqueta}")
                pares.append(f"{clave}={_escapar_extension(str(plano[campo]))}")
        for campo, (clave, etiqueta) in _NUMERICOS.items():
            if es_entero(plano.get(campo)):
                pares.append(f"{clave}Label={etiqueta}")
                pares.append(f"{clave}={plano[campo]}")
        return pares

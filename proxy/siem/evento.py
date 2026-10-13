"""El dominio de la exportacion a un SIEM: que es un evento y como se clasifica.

Sin E/S, sin entorno y sin conocer ningun SIEM ni formato de cable. Lo comparten todos
los formateadores (CEF, LEEF, ECS, JSON...): lo que cambia entre ellos es la forma, no
el significado de un evento de IronVeil.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple

CAMPOS_BASE: tuple[str, ...] = (
    "timestamp",
    "configuracion",
    "mecanismos_activos",
    "vector_probado",
    "modelo_destino",
    "resultado",
    "mecanismo_que_bloqueo",
    "latencia_ms",
)

# Marca que permite a las reglas de un SIEM reconocer los eventos de IronVeil entre
# cualquier otro JSON que lea el mismo agente.
MARCA_INTEGRACION = "ironveil"
PRODUCTO = "IronVeil Proxy"
FABRICANTE = "IronVeil"
VERSION_PRODUCTO = "1.0"


class Clasificacion(NamedTuple):
    """Como se le presenta un resultado a un analista, sea cual sea el formato."""

    id_firma: str
    nombre: str
    severidad: int  # escala 0-10 de CEF: un ataque exitoso es lo primero que se mira


CLASIFICACION_POR_RESULTADO: dict[str, Clasificacion] = {
    "bloqueado": Clasificacion("IV-100", "Peticion bloqueada por un mecanismo", 5),
    "exitoso_para_atacante": Clasificacion(
        "IV-200", "Ataque exitoso para el atacante", 9
    ),
    "permitido_normal": Clasificacion("IV-300", "Peticion permitida", 1),
}


def validar_evento(evento: dict[str, Any]) -> None:
    """Falla ruidosamente si falta alguno de los 8 campos base (nada de eventos a
    medias llegando a un SIEM) o si `resultado` no es uno de los tres del contrato."""
    faltantes = [campo for campo in CAMPOS_BASE if campo not in evento]
    if faltantes:
        raise ValueError(f"evento sin campos base obligatorios: {faltantes}")
    if evento["resultado"] not in CLASIFICACION_POR_RESULTADO:
        raise ValueError(f"resultado fuera del contrato: {evento['resultado']!r}")


def clasificar_resultado(evento: dict[str, Any]) -> Clasificacion:
    """La clasificacion del `resultado` de un evento ya validado."""
    return CLASIFICACION_POR_RESULTADO[evento["resultado"]]


def aplanar_listas(evento: dict[str, Any]) -> dict[str, Any]:
    """Copia de `evento` con las listas como cadena separada por comas."""
    return {
        clave: ",".join(str(x) for x in valor) if isinstance(valor, list) else valor
        for clave, valor in evento.items()
    }


def sin_nulos(evento: dict[str, Any]) -> dict[str, Any]:
    """Copia sin los campos `null`: ausente significa lo mismo que `null` en el esquema
    interno, y varios SIEM convierten un `null` en la cadena "null"."""
    return {clave: valor for clave, valor in evento.items() if valor is not None}


def epoch_ms(timestamp_iso: str) -> int | None:
    """Epoch en milisegundos del timestamp ISO 8601, o None si no se puede leer (el
    SIEM usara entonces su hora de recepcion)."""
    try:
        return int(datetime.fromisoformat(timestamp_iso).timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def es_entero(valor: Any) -> bool:
    """True para un entero de verdad (un booleano no cuenta)."""
    return isinstance(valor, int) and not isinstance(valor, bool)

"""Los formatos que trae IronVeil (otros se agregan desde fuera: `registro.py`)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from proxy.siem.formatos.cef import FormateadorCEF
from proxy.siem.formatos.ecs import FormateadorECS
from proxy.siem.formatos.json_plano import FormateadorJSON, FormateadorWazuhJSON
from proxy.siem.formatos.leef import FormateadorLEEF
from proxy.siem.puertos import FormateadorSIEM
from proxy.siem.registro import RegistroSIEM

__all__ = [
    "FORMATOS_INCLUIDOS",
    "FORMATOS_SIEM",
    "FormateadorCEF",
    "FormateadorECS",
    "FormateadorJSON",
    "FormateadorLEEF",
    "FormateadorWazuhJSON",
    "exportar_a_siem",
    "registrar_incluidos",
]

# nombre en la configuracion -> formateador. `json` es el de Wazuh (el historico).
FORMATOS_INCLUIDOS: dict[str, Callable[[], FormateadorSIEM]] = {
    "json": FormateadorWazuhJSON,
    "cef": FormateadorCEF,
    "leef": FormateadorLEEF,
    "ecs": FormateadorECS,
}

FORMATOS_SIEM: tuple[str, ...] = tuple(FORMATOS_INCLUIDOS)


def exportar_a_siem(evento: dict[str, Any], formato: str = "json") -> str:
    """Convierte un evento al string que espera el SIEM (funcion pura: sin E/S).

    Lanza `ValueError` si falta un campo base, si `resultado` no es uno de los
    tres del contrato o si `formato` no es uno de los incluidos.
    """
    fabrica = FORMATOS_INCLUIDOS.get(formato)
    if fabrica is None:
        raise ValueError(f"formato SIEM desconocido: {formato!r} ({FORMATOS_SIEM})")
    return fabrica().formatear(evento)


def registrar_incluidos(registro: RegistroSIEM) -> None:
    """Registra json, cef, leef y ecs."""
    for nombre, fabrica in FORMATOS_INCLUIDOS.items():
        registro.registrar_formato(nombre, fabrica)

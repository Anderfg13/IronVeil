"""Pruebas unitarias del andamiaje SIEM (patron Adapter, proxy/siem.py).

No prueban ningun SIEM real (todavia no existe esa integracion) -- solo que
los dos adapters de referencia funcionan y que enviar_a_siem() los compone
correctamente sin acoplarse a ninguno en concreto.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from proxy.siem import (
    ConectorArchivoLocal,
    ConectorSIEM,
    FormateadorJSON,
    FormateadorSIEM,
    enviar_a_siem,
)

EVENTO_EJEMPLO: dict[str, Any] = {
    "timestamp": "2026-09-25T00:00:00-05:00",
    "configuracion": "C1",
    "mecanismos_activos": ["filtrado"],
    "vector_probado": "V3-A",
    "modelo_destino": "soporte",
    "resultado": "bloqueado",
    "mecanismo_que_bloqueo": "filtrado",
    "latencia_ms": 12,
}


def test_formateador_json_produce_una_linea_json_valida() -> None:
    formateador = FormateadorJSON()

    mensaje = formateador.formatear(EVENTO_EJEMPLO)

    assert json.loads(mensaje) == EVENTO_EJEMPLO
    assert "\n" not in mensaje


def test_conector_archivo_local_agrega_una_linea_por_envio(tmp_path: Path) -> None:
    ruta = tmp_path / "siem" / "eventos_siem.jsonl"
    conector = ConectorArchivoLocal(ruta)

    conector.enviar('{"a": 1}')
    conector.enviar('{"a": 2}')

    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert lineas == ['{"a": 1}', '{"a": 2}']


def test_conector_archivo_local_crea_el_directorio_si_no_existe(tmp_path: Path) -> None:
    ruta = tmp_path / "no_existe_todavia" / "eventos_siem.jsonl"
    conector = ConectorArchivoLocal(ruta)

    conector.enviar('{"a": 1}')

    assert ruta.is_file()


def test_enviar_a_siem_compone_formateador_y_conector(tmp_path: Path) -> None:
    ruta = tmp_path / "eventos_siem.jsonl"

    enviar_a_siem(EVENTO_EJEMPLO, FormateadorJSON(), ConectorArchivoLocal(ruta))

    linea = ruta.read_text(encoding="utf-8").strip()
    assert json.loads(linea) == EVENTO_EJEMPLO


def test_enviar_a_siem_no_conoce_el_adapter_concreto() -> None:
    """Cualquier objeto con formatear()/enviar() sirve -- typing
    estructural de Protocol, no hace falta heredar de FormateadorSIEM ni
    ConectorSIEM. Esto es lo que permite envolver el SDK de un SIEM real
    sin una capa de mas."""

    class _FormateadorFalso:
        def formatear(self, evento: dict[str, Any]) -> str:
            return f"CUSTOM:{evento['resultado']}"

    class _ConectorFalso:
        def __init__(self) -> None:
            self.recibidos: list[str] = []

        def enviar(self, mensaje: str) -> None:
            self.recibidos.append(mensaje)

    formateador: FormateadorSIEM = _FormateadorFalso()
    conector = _ConectorFalso()

    enviar_a_siem(EVENTO_EJEMPLO, formateador, conector)

    assert conector.recibidos == ["CUSTOM:bloqueado"]
    # Confirma tambien que ConectorSIEM (Protocol) no exige heredar.
    assert isinstance(conector, ConectorSIEM)

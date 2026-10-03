"""Pruebas de los scripts de analisis de la extension del 17 de octubre:
validar_formato_siem.py y consolidar_excessive_agency.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from analisis.consolidar_excessive_agency import (
    COL_EJECUCION,
    COL_INVOCACION,
    COL_REVISION,
    cargar_eventos_v7,
    tabla_por_configuracion,
)
from analisis.validar_formato_siem import elegir_muestra, validar_evento

BASE: dict[str, Any] = {
    "timestamp": "2026-09-05T17:47:43-05:00",
    "configuracion": "C1",
    "mecanismos_activos": ["filtrado"],
    "vector_probado": "V2-E",
    "modelo_destino": "rrhh",
    "resultado": "bloqueado",
    "mecanismo_que_bloqueo": "filtrado",
    "latencia_ms": 3,
}


def test_validar_evento_real_pasa_las_reglas() -> None:
    assert validar_evento(BASE).valido


def test_validar_evento_acepta_nulls_y_listas_vacias() -> None:
    evento = {
        **BASE,
        "configuracion": "C0",
        "mecanismos_activos": [],
        "vector_probado": None,
        "resultado": "permitido_normal",
        "mecanismo_que_bloqueo": None,
    }
    assert validar_evento(evento).valido


def test_elegir_muestra_cubre_los_tres_resultados() -> None:
    eventos = [
        {**BASE, "resultado": "bloqueado"},
        {**BASE, "resultado": "bloqueado", "configuracion": "C3"},
        {**BASE, "resultado": "exitoso_para_atacante", "configuracion": "C0"},
        {**BASE, "resultado": "permitido_normal", "configuracion": "C0"},
    ]
    muestra = elegir_muestra(eventos, 4)
    assert {e["resultado"] for e in muestra} == {
        "bloqueado",
        "exitoso_para_atacante",
        "permitido_normal",
    }
    assert len(muestra) == 4


def _escribir_v7(tmp_path: Path, eventos: list[dict[str, Any]]) -> Path:
    carpeta = tmp_path / "2026-10-02"
    carpeta.mkdir()
    archivo = carpeta / "vector7_excessive_agency_C0_120000.jsonl"
    archivo.write_text("".join(json.dumps(e) + "\n" for e in eventos), encoding="utf-8")
    return tmp_path


def _evento_v7(config: str, invocada: bool, ejecutada: bool) -> dict[str, Any]:
    return {
        **BASE,
        "configuracion": config,
        "vector_probado": "V7-A",
        "herramienta_invocada": invocada,
        "herramienta_ejecutada": ejecutada,
        "mecanismo_que_bloqueo": (
            "aprobacion_humana" if invocada and not ejecutada else None
        ),
        "es_extension": True,
    }


def test_tabla_excessive_agency_calcula_tasas(tmp_path: Path) -> None:
    directorio = _escribir_v7(
        tmp_path,
        [
            _evento_v7("C0", True, True),
            _evento_v7("C0", False, False),
            _evento_v7("C5", True, False),
            _evento_v7("C5", True, False),
        ],
    )

    tabla = tabla_por_configuracion(cargar_eventos_v7(directorio))
    c0 = tabla[tabla["Configuración"] == "C0"].iloc[0]
    c5 = tabla[tabla["Configuración"] == "C5"].iloc[0]

    assert c0[COL_INVOCACION] == 50.0
    assert c0[COL_EJECUCION] == 50.0
    assert c5[COL_INVOCACION] == 100.0
    assert c5[COL_EJECUCION] == 0.0
    assert c5[COL_REVISION] == 2


def test_cargar_eventos_v7_falla_si_no_hay_datos(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        cargar_eventos_v7(tmp_path)

"""Pruebas de analisis/validar_formato_siem.py (no necesitan Wazuh)."""

from __future__ import annotations

import json
from typing import Any

from analisis import validar_formato_siem as val
from proxy.siem import exportar_a_siem

EVENTO: dict[str, Any] = {
    "timestamp": "2026-09-25T07:42:14-05:00",
    "configuracion": "C6",
    "mecanismos_activos": ["filtrado", "aprobacion_humana"],
    "vector_probado": None,
    "modelo_destino": "soporte",
    "resultado": "bloqueado",
    "mecanismo_que_bloqueo": "aprobacion_humana",
    "latencia_ms": 15098,
}


def test_salida_de_exportar_a_siem_pasa_todas_las_comprobaciones_json() -> None:
    comprobaciones = val.validar_salida_json(EVENTO, exportar_a_siem(EVENTO))

    assert all(comprobaciones.values()), comprobaciones


def test_una_salida_con_lista_o_null_se_detecta_como_invalida() -> None:
    con_lista = json.dumps({"integration": "ironveil", "mecanismos_activos": ["a"]})
    con_null = json.dumps({"integration": "ironveil", "resultado": None})

    assert val.validar_salida_json(EVENTO, con_lista)["solo_escalares"] is False
    assert val.validar_salida_json(EVENTO, con_null)["sin_null"] is False


def test_salida_que_no_es_json_se_marca_invalida() -> None:
    assert val.validar_salida_json(EVENTO, "no es json") == {"json_valido": False}


def test_cef_valido_y_cef_roto() -> None:
    assert all(val.validar_salida_cef(exportar_a_siem(EVENTO, "cef")).values())
    assert not all(val.validar_salida_cef("CEF:0|solo|tres|campos").values())


def test_la_muestra_real_por_defecto_es_valida() -> None:
    resultados = val.validar_muestra(list(val.MUESTRA_DEFECTO))

    assert len(resultados) == 5
    assert all(r.valido for r in resultados), [
        (r.origen, [k for k, ok in r.comprobaciones.items() if not ok])
        for r in resultados
        if not r.valido
    ]

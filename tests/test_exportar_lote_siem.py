"""Pruebas de analisis/exportar_lote_siem.py (sin Wazuh, sin red)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analisis import exportar_lote_siem as lote
from proxy.siem import CAMPOS_BASE


def test_lote_de_ejemplo_cubre_los_tres_resultados_y_v7() -> None:
    eventos = lote.eventos_de_ejemplo()

    assert {e["resultado"] for e in eventos} == {
        "bloqueado",
        "exitoso_para_atacante",
        "permitido_normal",
    }
    assert any(e["vector_probado"].startswith("V7") for e in eventos)
    assert all(e["sintetico"] is True for e in eventos)
    assert all(campo in e for e in eventos for campo in CAMPOS_BASE)


def test_exportar_lote_escribe_una_linea_json_por_evento(tmp_path: Path) -> None:
    salida = lote.RAIZ / "docs" / "siem" / "exportados" / "_prueba_test_lote.json"
    try:
        exportados, rechazados = lote.exportar_lote(
            lote.eventos_de_ejemplo(), salida, "json"
        )
        lineas = salida.read_text(encoding="utf-8").splitlines()
    finally:
        salida.unlink(missing_ok=True)

    assert (exportados, rechazados) == (7, 0)
    assert len(lineas) == 7
    assert all(json.loads(linea)["integration"] == "ironveil" for linea in lineas)


def test_exportar_lote_rechaza_eventos_incompletos_sin_abortar() -> None:
    salida = lote.RAIZ / "docs" / "siem" / "exportados" / "_prueba_test_lote2.json"
    eventos = lote.eventos_de_ejemplo()
    del eventos[0]["latencia_ms"]
    try:
        exportados, rechazados = lote.exportar_lote(eventos, salida, "cef")
    finally:
        salida.unlink(missing_ok=True)

    assert (exportados, rechazados) == (6, 1)


def test_salida_fuera_del_repo_se_rechaza(tmp_path: Path) -> None:
    eventos = lote.eventos_de_ejemplo()

    with pytest.raises(ValueError, match="fuera de"):
        lote.exportar_lote(eventos, tmp_path / "x.json", "json")


def test_leer_eventos_cuenta_lineas_invalidas(tmp_path: Path) -> None:
    ruta = tmp_path / "eventos.jsonl"
    ruta.write_text('{"a": 1}\nno es json\n\n[1, 2]\n{"b": 2}\n', encoding="utf-8")

    eventos, invalidas = lote.leer_eventos(ruta)

    assert eventos == [{"a": 1}, {"b": 2}]
    assert invalidas == 2

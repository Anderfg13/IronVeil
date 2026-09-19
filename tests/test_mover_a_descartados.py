"""Pruebas unitarias de analisis/mover_a_descartados.py (regla 4 de CLAUDE.md)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from analisis.mover_a_descartados import mover_a_descartados

COLUMNAS = ["timestamp", "configuracion", "vector_probado", "resultado"]


def _escribir_csv(ruta: Path, filas: list[dict[str, str]]) -> None:
    with ruta.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        escritor.writeheader()
        escritor.writerows(filas)


def _leer_csv(ruta: Path) -> list[dict[str, str]]:
    with ruta.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(autouse=True)
def _redirigir_rutas(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, Path]:
    import analisis.mover_a_descartados as modulo

    resultados = tmp_path / "resultados_template.csv"
    descartados = tmp_path / "descartados.csv"
    monkeypatch.setattr(modulo, "RESULTADOS_CSV", resultados)
    monkeypatch.setattr(modulo, "DESCARTADOS_CSV", descartados)
    return resultados, descartados


def test_mueve_solo_las_configuraciones_pedidas(
    _redirigir_rutas: tuple[Path, Path],
) -> None:
    resultados, descartados = _redirigir_rutas
    _escribir_csv(
        resultados,
        [
            {
                "timestamp": "t1",
                "configuracion": "C3",
                "vector_probado": "V1-A",
                "resultado": "r",
            },
            {
                "timestamp": "t2",
                "configuracion": "C4",
                "vector_probado": "V1-A",
                "resultado": "r",
            },
            {
                "timestamp": "t3",
                "configuracion": "C6",
                "vector_probado": "V1-A",
                "resultado": "r",
            },
        ],
    )

    movidas = mover_a_descartados(["C3", "C6"], razon="prueba")

    assert movidas == 2
    restantes = _leer_csv(resultados)
    assert [f["configuracion"] for f in restantes] == ["C4"]
    en_descartados = _leer_csv(descartados)
    assert {f["configuracion"] for f in en_descartados} == {"C3", "C6"}
    assert all(f["razon_descarte"] == "prueba" for f in en_descartados)
    assert all(f["fecha_descarte"] for f in en_descartados)


def test_no_pierde_ninguna_columna_original(
    _redirigir_rutas: tuple[Path, Path],
) -> None:
    resultados, descartados = _redirigir_rutas
    _escribir_csv(
        resultados,
        [
            {
                "timestamp": "t1",
                "configuracion": "C3",
                "vector_probado": "V1-A",
                "resultado": "r",
            }
        ],
    )

    mover_a_descartados(["C3"], razon="prueba")

    fila = _leer_csv(descartados)[0]
    for columna in COLUMNAS:
        assert columna in fila


def test_configuracion_sin_coincidencias_no_modifica_nada(
    _redirigir_rutas: tuple[Path, Path],
) -> None:
    resultados, descartados = _redirigir_rutas
    _escribir_csv(
        resultados,
        [
            {
                "timestamp": "t1",
                "configuracion": "C4",
                "vector_probado": "V1-A",
                "resultado": "r",
            }
        ],
    )

    movidas = mover_a_descartados(["C3"], razon="prueba")

    assert movidas == 0
    assert not descartados.exists()
    assert len(_leer_csv(resultados)) == 1


def test_agrega_sin_borrar_descartados_previos(
    _redirigir_rutas: tuple[Path, Path],
) -> None:
    resultados, descartados = _redirigir_rutas
    _escribir_csv(
        resultados,
        [
            {
                "timestamp": "t1",
                "configuracion": "C3",
                "vector_probado": "V1-A",
                "resultado": "r",
            },
            {
                "timestamp": "t2",
                "configuracion": "C6",
                "vector_probado": "V1-A",
                "resultado": "r",
            },
        ],
    )

    mover_a_descartados(["C3"], razon="primera razon")
    mover_a_descartados(["C6"], razon="segunda razon")

    en_descartados = _leer_csv(descartados)
    assert len(en_descartados) == 2
    razones = {f["configuracion"]: f["razon_descarte"] for f in en_descartados}
    assert razones == {"C3": "primera razon", "C6": "segunda razon"}

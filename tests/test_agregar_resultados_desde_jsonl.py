"""Pruebas unitarias de analisis/agregar_resultados_desde_jsonl.py."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from analisis.agregar_resultados_desde_jsonl import (
    COLUMNAS_MAESTRAS,
    agregar_desde_jsonl,
)


def _escribir_jsonl(ruta: Path, eventos: list[dict[str, object]]) -> None:
    with ruta.open("w", encoding="utf-8") as f:
        for evento in eventos:
            f.write(json.dumps(evento) + "\n")


def _leer_csv(ruta: Path) -> list[dict[str, str]]:
    with ruta.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(autouse=True)
def _redirigir_csv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    import analisis.agregar_resultados_desde_jsonl as modulo

    destino = tmp_path / "resultados_template.csv"
    monkeypatch.setattr(modulo, "RESULTADOS_CSV", destino)
    return destino


def test_agrega_filas_con_las_14_columnas_maestras(_redirigir_csv: Path) -> None:
    jsonl = _redirigir_csv.parent / "evento.jsonl"
    _escribir_jsonl(
        jsonl,
        [
            {
                "timestamp": "t1",
                "configuracion": "C6",
                "mecanismos_activos": ["filtrado", "clasificacion"],
                "vector_probado": "V1-A",
                "modelo_destino": "soporte",
                "resultado": "bloqueado",
                "mecanismo_que_bloqueo": "filtrado",
                "latencia_ms": 12,
                "fuga_confirmada": False,
                "observaciones": "campo extra, no es del esquema maestro",
            }
        ],
    )

    agregadas = agregar_desde_jsonl([jsonl])

    assert agregadas == 1
    filas = _leer_csv(_redirigir_csv)
    assert len(filas) == 1
    assert set(filas[0].keys()) == set(COLUMNAS_MAESTRAS)
    assert filas[0]["mecanismos_activos"] == "filtrado,clasificacion"
    assert filas[0]["mecanismo_que_bloqueo"] == "filtrado"
    # Los campos extra del JSONL (fuga_confirmada, observaciones) no se
    # copian al CSV maestro -- no se pierden (siguen en el JSONL crudo),
    # solo no se duplican aqui.
    assert "fuga_confirmada" not in filas[0]
    assert "observaciones" not in filas[0]


def test_campos_ausentes_quedan_vacios_no_inventados(_redirigir_csv: Path) -> None:
    jsonl = _redirigir_csv.parent / "evento.jsonl"
    _escribir_jsonl(
        jsonl,
        [
            {
                "timestamp": "t1",
                "configuracion": "C3",
                "mecanismos_activos": ["clasificacion"],
                "vector_probado": "V1-A",
                "modelo_destino": "soporte",
                "resultado": "permitido_normal",
                "mecanismo_que_bloqueo": None,
                "latencia_ms": 5,
            }
        ],
    )

    agregar_desde_jsonl([jsonl])

    fila = _leer_csv(_redirigir_csv)[0]
    assert fila["mecanismo_que_bloqueo"] == ""
    assert fila["nivel_carga"] == ""
    assert fila["tipo_variante"] == ""


def test_agrega_varios_archivos_en_una_sola_llamada(_redirigir_csv: Path) -> None:
    jsonl1 = _redirigir_csv.parent / "e1.jsonl"
    jsonl2 = _redirigir_csv.parent / "e2.jsonl"
    _escribir_jsonl(jsonl1, [{"timestamp": "t1", "vector_probado": "V1-A"}])
    _escribir_jsonl(jsonl2, [{"timestamp": "t2", "vector_probado": "V4-A"}])

    agregadas = agregar_desde_jsonl([jsonl1, jsonl2])

    assert agregadas == 2
    assert len(_leer_csv(_redirigir_csv)) == 2


def test_agregar_no_borra_filas_existentes(_redirigir_csv: Path) -> None:
    with _redirigir_csv.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(COLUMNAS_MAESTRAS))
        escritor.writeheader()
        escritor.writerow({"timestamp": "existente", "vector_probado": "V0-X"})

    jsonl = _redirigir_csv.parent / "evento.jsonl"
    _escribir_jsonl(jsonl, [{"timestamp": "nuevo", "vector_probado": "V1-A"}])

    agregar_desde_jsonl([jsonl])

    filas = _leer_csv(_redirigir_csv)
    assert len(filas) == 2
    assert filas[0]["timestamp"] == "existente"
    assert filas[1]["timestamp"] == "nuevo"


def test_sin_archivos_no_modifica_nada(_redirigir_csv: Path) -> None:
    agregadas = agregar_desde_jsonl([])

    assert agregadas == 0
    assert not _redirigir_csv.exists()

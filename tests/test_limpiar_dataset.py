"""Pruebas unitarias de analisis/limpiar_dataset.py."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analisis.limpiar_dataset import (
    corregir_mecanismo_desconocido,
    mover_duplicados_exactos,
)

COLUMNAS = (
    "timestamp",
    "configuracion",
    "mecanismos_activos",
    "vector_probado",
    "modelo_destino",
    "resultado",
    "mecanismo_que_bloqueo",
    "latencia_ms",
)


def _fila(**overrides: str) -> dict[str, str]:
    base = {
        "timestamp": "2026-09-05T14:32:11-05:00",
        "configuracion": "C3",
        "mecanismos_activos": "clasificacion",
        "vector_probado": "V3-A",
        "modelo_destino": "soporte",
        "resultado": "bloqueado",
        "mecanismo_que_bloqueo": "desconocido (ver eventos.jsonl del proxy)",
        "latencia_ms": "812",
    }
    base.update(overrides)
    return base


def _df(filas: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(filas, columns=COLUMNAS)


def test_corrige_mecanismo_desconocido_con_un_solo_activo() -> None:
    df = _df([_fila()])

    corregido, corregidas, sin_tocar = corregir_mecanismo_desconocido(df)

    assert corregidas == 1
    assert sin_tocar == 0
    assert corregido.at[0, "mecanismo_que_bloqueo"] == "clasificacion"


def test_no_corrige_cuando_hay_mas_de_un_mecanismo_activo() -> None:
    df = _df([_fila(mecanismos_activos="filtrado,clasificacion")])

    corregido, corregidas, sin_tocar = corregir_mecanismo_desconocido(df)

    assert corregidas == 0
    assert sin_tocar == 1
    assert corregido.at[0, "mecanismo_que_bloqueo"].startswith("desconocido")


def test_no_toca_filas_sin_el_problema() -> None:
    df = _df([_fila(mecanismo_que_bloqueo="clasificacion")])

    corregido, corregidas, sin_tocar = corregir_mecanismo_desconocido(df)

    assert corregidas == 0
    assert sin_tocar == 0
    assert corregido.at[0, "mecanismo_que_bloqueo"] == "clasificacion"


def test_mueve_duplicados_exactos_a_descartados(tmp_path: Path) -> None:
    fila = _fila(mecanismo_que_bloqueo="clasificacion")
    df = _df(
        [
            fila,
            dict(fila),
            _fila(vector_probado="V3-B", mecanismo_que_bloqueo="clasificacion"),
        ]
    )
    ruta_descartados = tmp_path / "descartados.csv"

    restante, movidas = mover_duplicados_exactos(df, ruta_descartados)

    assert movidas == 1
    assert len(restante) == 2
    assert ruta_descartados.is_file()
    descartados = pd.read_csv(ruta_descartados, dtype=str, keep_default_na=False)
    assert len(descartados) == 1
    assert descartados.at[0, "razon_descarte"].startswith("duplicado exacto")
    assert descartados.at[0, "fecha_descarte"] != ""


def test_sin_duplicados_no_escribe_descartados(tmp_path: Path) -> None:
    df = _df([_fila(), _fila(vector_probado="V3-B")])
    ruta_descartados = tmp_path / "descartados.csv"

    restante, movidas = mover_duplicados_exactos(df, ruta_descartados)

    assert movidas == 0
    assert len(restante) == 2
    assert not ruta_descartados.exists()


def test_mover_duplicados_hace_append_si_descartados_ya_existe(tmp_path: Path) -> None:
    ruta_descartados = tmp_path / "descartados.csv"
    ruta_descartados.write_text(
        ",".join([*COLUMNAS, "razon_descarte", "fecha_descarte"]) + "\n",
        encoding="utf-8",
    )

    fila = _fila(mecanismo_que_bloqueo="clasificacion")
    df = _df([fila, dict(fila)])

    _, movidas = mover_duplicados_exactos(df, ruta_descartados)

    assert movidas == 1
    descartados = pd.read_csv(ruta_descartados, dtype=str, keep_default_na=False)
    assert len(descartados) == 1

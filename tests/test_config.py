"""Pruebas unitarias de cargar_config() (proxy/mecanismos.py)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from proxy.mecanismos import CONFIG_PATH, FLAGS_REQUERIDAS, cargar_config


def _escribir_config(tmp_path: Path, contenido: str) -> Path:
    ruta = tmp_path / "config.yaml"
    ruta.write_text(textwrap.dedent(contenido), encoding="utf-8")
    return ruta


def test_cargar_config_valido(tmp_path: Path) -> None:
    ruta = _escribir_config(
        tmp_path,
        """\
        filtrado: true
        delimitacion: false
        clasificacion: false
        minimo_privilegio: true
        aprobacion_humana: false
        """,
    )

    config = cargar_config(ruta)

    assert config == {
        "filtrado": True,
        "delimitacion": False,
        "clasificacion": False,
        "minimo_privilegio": True,
        "aprobacion_humana": False,
    }
    assert set(config) == set(FLAGS_REQUERIDAS)


def test_cargar_config_clave_faltante(tmp_path: Path) -> None:
    ruta = _escribir_config(
        tmp_path,
        """\
        filtrado: false
        delimitacion: false
        clasificacion: false
        minimo_privilegio: false
        """,
    )

    with pytest.raises(ValueError, match="aprobacion_humana"):
        cargar_config(ruta)


def test_cargar_config_archivo_inexistente(tmp_path: Path) -> None:
    ruta = tmp_path / "no_existe.yaml"

    with pytest.raises(FileNotFoundError, match="no_existe.yaml"):
        cargar_config(ruta)


def test_cargar_config_valor_no_booleano(tmp_path: Path) -> None:
    ruta = _escribir_config(
        tmp_path,
        """\
        filtrado: "si"
        delimitacion: false
        clasificacion: false
        minimo_privilegio: false
        aprobacion_humana: false
        """,
    )

    with pytest.raises(ValueError, match="filtrado"):
        cargar_config(ruta)


def test_config_yaml_real_del_proyecto_es_valido() -> None:
    config = cargar_config(CONFIG_PATH)

    assert set(config) == set(FLAGS_REQUERIDAS)
    assert all(valor is False for valor in config.values())

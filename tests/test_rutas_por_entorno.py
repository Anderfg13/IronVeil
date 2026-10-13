"""Rutas alternativas por entorno para una segunda instancia del proxy."""

from __future__ import annotations

from pathlib import Path

import pytest

import proxy.main as main
import proxy.mecanismos as mecanismos
from proxy.mecanismos import ruta_configurable

POR_DEFECTO = Path("/por/defecto")


def test_sin_la_variable_se_usa_la_ruta_de_siempre(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("IRONVEIL_PRUEBA", raising=False)

    assert ruta_configurable("IRONVEIL_PRUEBA", POR_DEFECTO) == POR_DEFECTO


@pytest.mark.parametrize("valor", ["", "   "])
def test_una_variable_vacia_no_cambia_nada(
    monkeypatch: pytest.MonkeyPatch, valor: str
) -> None:
    monkeypatch.setenv("IRONVEIL_PRUEBA", valor)

    assert ruta_configurable("IRONVEIL_PRUEBA", POR_DEFECTO) == POR_DEFECTO


def test_con_la_variable_se_usa_esa_ruta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IRONVEIL_PRUEBA", " /otra/ruta ")

    assert ruta_configurable("IRONVEIL_PRUEBA", POR_DEFECTO) == Path("/otra/ruta")


def test_en_esta_maquina_las_rutas_siguen_siendo_las_del_proyecto() -> None:
    raiz = Path(mecanismos.__file__).resolve().parent.parent

    assert mecanismos.CONFIG_PATH == raiz / "config.yaml"
    assert main.RESULTADOS_DIR == raiz / "resultados"

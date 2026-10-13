"""Rutas de la linea de comandos: dentro del proyecto o de /tmp, nunca fuera."""

from __future__ import annotations

from pathlib import Path

import pytest

from analisis import rutas
from analisis.rutas import ErrorRutaNoPermitida, ruta_permitida


def test_una_ruta_del_repositorio_se_acepta() -> None:
    assert (
        ruta_permitida(rutas.RAIZ / "analisis" / "salida.md").parent.name == "analisis"
    )


def test_una_ruta_temporal_se_acepta(tmp_path: Path) -> None:
    assert ruta_permitida(tmp_path / "informe.md").name == "informe.md"


def test_salirse_con_puntos_se_rechaza() -> None:
    with pytest.raises(ErrorRutaNoPermitida):
        # base explicita: el repo puede estar clonado dentro de /tmp
        ruta_permitida(
            rutas.RAIZ / "analisis" / ".." / ".." / "otra_carpeta" / "x.md", rutas.RAIZ
        )


def test_una_ruta_absoluta_ajena_se_rechaza() -> None:
    ajena = Path(rutas.RAIZ.anchor) / "una_carpeta_ajena_al_proyecto" / "x.md"
    with pytest.raises(ErrorRutaNoPermitida):
        ruta_permitida(ajena)


def test_un_enlace_simbolico_que_sale_se_rechaza(tmp_path: Path) -> None:
    carpeta_ajena = tmp_path / "ajena"
    carpeta_ajena.mkdir()
    enlace = tmp_path / "enlace"
    try:
        enlace.symlink_to(carpeta_ajena, target_is_directory=True)
    except OSError:
        pytest.skip("este sistema no permite crear enlaces simbolicos")
    base = tmp_path / "permitida"
    base.mkdir()
    with pytest.raises(ErrorRutaNoPermitida):
        ruta_permitida(base / ".." / "enlace" / "x.md", base)


def test_con_bases_explicitas_solo_valen_esas(tmp_path: Path) -> None:
    base = tmp_path / "solo_aqui"
    base.mkdir()
    assert ruta_permitida(base / "x.md", base).name == "x.md"
    with pytest.raises(ErrorRutaNoPermitida):
        ruta_permitida(rutas.RAIZ / "x.md", base)


def test_el_mensaje_de_error_no_revela_mas_que_lo_pedido() -> None:
    with pytest.raises(ErrorRutaNoPermitida, match="queda fuera del proyecto"):
        ruta_permitida(Path(rutas.RAIZ.anchor) / "ajena" / "x.md")

"""Pruebas de scripts/seleccionar_config.py: las 7 configuraciones del experimento."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent


def _cargar() -> ModuleType:
    ruta = RAIZ / "scripts" / "seleccionar_config.py"
    especificacion = importlib.util.spec_from_file_location("seleccionar_config", ruta)
    assert especificacion is not None
    assert especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


sc = _cargar()


def _banderas(nombre: str) -> dict[str, bool]:
    return yaml.safe_load(sc.construir_config(nombre))


def test_c0_es_el_baseline_con_todo_apagado() -> None:
    assert not any(_banderas("C0").values())


@pytest.mark.parametrize("numero", range(1, 6))
def test_c1_a_c5_activan_exactamente_un_mecanismo(numero: int) -> None:
    banderas = _banderas(f"C{numero}")
    assert [m for m, activo in banderas.items() if activo] == [
        sc.MECANISMOS[numero - 1]
    ]


def test_c6_activa_los_cinco() -> None:
    assert all(_banderas("C6").values())


def test_siempre_estan_las_cinco_claves_que_exige_cargar_config() -> None:
    for nombre in sc.CONFIGURACIONES:
        assert set(_banderas(nombre)) == set(sc.MECANISMOS)


def test_una_configuracion_desconocida_falla_con_mensaje_claro() -> None:
    with pytest.raises(ValueError, match="C9"):
        sc.construir_config("C9")


def test_escribir_config_escribe_el_archivo_pedido(tmp_path: Path) -> None:
    destino = tmp_path / "config.yaml"
    sc.escribir_config(destino, "C2")
    assert yaml.safe_load(destino.read_text(encoding="utf-8"))["delimitacion"] is True


def test_main_escribe_solo_el_config_del_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    destino = tmp_path / "config.yaml"
    monkeypatch.setattr(sc, "RUTA_CONFIG", destino)
    assert sc.main(["C3"]) == 0
    assert yaml.safe_load(destino.read_text(encoding="utf-8"))["clasificacion"] is True

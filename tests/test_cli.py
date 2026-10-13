"""Pruebas de la linea de comandos `ironveil` (proxy/cli.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import proxy.cli as cli
from proxy.configuraciones import CONFIGURACIONES, MECANISMOS


def test_config_escribe_las_cinco_banderas(tmp_path: Path) -> None:
    destino = tmp_path / "config.yaml"

    codigo = cli.main(["config", "C4", "--salida", str(destino)])

    banderas = yaml.safe_load(destino.read_text(encoding="utf-8"))
    assert codigo == 0
    assert banderas == {m: m == "minimo_privilegio" for m in MECANISMOS}


@pytest.mark.parametrize("nombre", sorted(CONFIGURACIONES))
def test_config_acepta_las_siete_configuraciones(nombre: str, tmp_path: Path) -> None:
    destino = tmp_path / "config.yaml"

    assert cli.main(["config", nombre, "--salida", str(destino)]) == 0


def test_config_rechaza_una_configuracion_desconocida() -> None:
    with pytest.raises(SystemExit):
        cli.main(["config", "C9"])


def test_serve_sin_config_falla_con_mensaje_claro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("IRONVEIL_CONFIG", raising=False)

    codigo = cli.main(["serve"])

    assert codigo == 2
    assert "ironveil config" in capsys.readouterr().err


def test_serve_usa_el_directorio_actual_y_no_site_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "config.yaml").write_text("x: 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("IRONVEIL_CONFIG", raising=False)
    monkeypatch.delenv("IRONVEIL_RESULTADOS", raising=False)
    llamadas: list[dict[str, object]] = []
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: llamadas.append(kw))

    codigo = cli.main(["serve", "--puerto", "9001"])

    assert codigo == 0
    assert llamadas == [{"host": "127.0.0.1", "port": 9001, "server_header": False}]
    assert Path(__import__("os").environ["IRONVEIL_RESULTADOS"]) == (
        tmp_path / "resultados"
    )
    monkeypatch.delenv("IRONVEIL_CONFIG")
    monkeypatch.delenv("IRONVEIL_RESULTADOS")

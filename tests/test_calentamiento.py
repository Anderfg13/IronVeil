"""Pruebas del calentamiento de modelos al arrancar el proxy (ver
proxy/main.py: _calentar_modelos(), _calentar_modelo_ollama(),
_calentar_clasificador(), _lifespan()).

Objetivo del calentamiento: pagar el costo de arranque en frio (carga de
un modelo en memoria) al iniciar el proceso, no en la primera peticion
real de un usuario o de la demo en vivo. Estas pruebas verifican que (1)
se calienta lo correcto segun config.yaml, y (2) un fallo en un
calentamiento nunca bloquea ni hace fallar a los demas.

No se usa pytest-asyncio (no es dependencia del proyecto): cada funcion
async se corre con `asyncio.run()` dentro de un test sincrono normal.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import proxy.main as main
import proxy.mecanismos as mecanismos


class _RespuestaFalsa:
    def raise_for_status(self) -> None:
        return None


class _ClienteOllamaFalso:
    def __init__(self, *, falla: bool = False) -> None:
        self.falla = falla
        self.modelos_llamados: list[str] = []
        self.ultimo_payload: dict[str, object] | None = None

    async def __aenter__(self) -> _ClienteOllamaFalso:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def post(self, *args: object, **kwargs: object) -> _RespuestaFalsa:
        payload = kwargs.get("json", {})
        self.ultimo_payload = payload  # type: ignore[assignment]
        self.modelos_llamados.append(payload["model"])  # type: ignore[index]
        if self.falla:
            raise RuntimeError("Ollama no disponible (simulado)")
        return _RespuestaFalsa()


def _escribir_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **flags: bool
) -> None:
    base = {
        "filtrado": False,
        "delimitacion": False,
        "clasificacion": False,
        "minimo_privilegio": False,
        "aprobacion_humana": False,
    }
    base.update(flags)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(f"{clave}: {str(valor).lower()}" for clave, valor in base.items()),
        encoding="utf-8",
    )
    monkeypatch.setattr(mecanismos, "CONFIG_PATH", config_path)


def test_calentar_modelo_ollama_llama_con_el_modelo_correcto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cliente_falso = _ClienteOllamaFalso()
    monkeypatch.setattr(main, "_obtener_cliente_http", lambda: cliente_falso)

    asyncio.run(main._calentar_modelo_ollama("soporte"))

    assert cliente_falso.modelos_llamados == ["soporte"]
    assert cliente_falso.ultimo_payload is not None
    assert cliente_falso.ultimo_payload["keep_alive"] == main.KEEP_ALIVE_OLLAMA


def test_calentar_clasificador_llama_clasificar_en_entrada_y_salida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[tuple[str, str]] = []

    def _clasificar_falso(texto: str, direccion: str) -> bool:
        llamadas.append((texto, direccion))
        return False

    monkeypatch.setattr(mecanismos, "clasificar", _clasificar_falso)

    asyncio.run(main._calentar_clasificador())

    direcciones = {direccion for _, direccion in llamadas}
    assert direcciones == {"entrada", "salida"}


def test_calentar_modelos_siempre_calienta_soporte_y_rrhh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _escribir_config(tmp_path, monkeypatch, clasificacion=False)
    cliente_falso = _ClienteOllamaFalso()
    monkeypatch.setattr(main, "_obtener_cliente_http", lambda: cliente_falso)

    def _clasificar_no_deberia_llamarse(*args: object, **kwargs: object) -> bool:
        raise AssertionError("clasificar() no deberia llamarse con clasificacion=false")

    monkeypatch.setattr(mecanismos, "clasificar", _clasificar_no_deberia_llamarse)

    asyncio.run(main._calentar_modelos())

    assert set(cliente_falso.modelos_llamados) == {"soporte", "rrhh"}


def test_calentar_modelos_calienta_clasificador_si_esta_activo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _escribir_config(tmp_path, monkeypatch, clasificacion=True)
    cliente_falso = _ClienteOllamaFalso()
    monkeypatch.setattr(main, "_obtener_cliente_http", lambda: cliente_falso)

    llamadas: list[str] = []
    monkeypatch.setattr(
        mecanismos,
        "clasificar",
        lambda texto, direccion: llamadas.append(direccion) or False,
    )

    asyncio.run(main._calentar_modelos())

    assert set(llamadas) == {"entrada", "salida"}


def test_calentar_modelos_no_propaga_excepcion_si_un_calentamiento_falla(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _escribir_config(tmp_path, monkeypatch, clasificacion=True)
    cliente_falso = _ClienteOllamaFalso(falla=True)
    monkeypatch.setattr(main, "_obtener_cliente_http", lambda: cliente_falso)

    def _clasificador_falla(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("HF_TOKEN ausente (simulado)")

    monkeypatch.setattr(mecanismos, "clasificar", _clasificador_falla)

    asyncio.run(main._calentar_modelos())  # no debe lanzar nada


def test_lifespan_llama_a_calentar_modelos(monkeypatch: pytest.MonkeyPatch) -> None:
    llamado = False

    async def _calentar_falso() -> None:
        nonlocal llamado
        llamado = True

    monkeypatch.setattr(main, "_calentar_modelos", _calentar_falso)

    async def _entrar_y_salir() -> None:
        async with main._lifespan(main.app):
            pass

    asyncio.run(_entrar_y_salir())

    assert llamado

"""Pruebas unitarias del mecanismo de clasificacion (proxy/mecanismos.py).

Todas mockean httpx.Client: no requieren Llama Guard corriendo ni el stack
levantado.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

import proxy.mecanismos as mecanismos
from proxy.mecanismos import clasificar


class _RespuestaFalsa:
    def __init__(self, contenido: str) -> None:
        self._contenido = contenido

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"message": {"role": "assistant", "content": self._contenido}}


class _ClienteLlamaGuardFalso:
    """Reemplaza httpx.Client: registra el payload enviado, sin red real."""

    def __init__(
        self, contenido: str | None = None, excepcion: Exception | None = None
    ) -> None:
        self._contenido = contenido
        self._excepcion = excepcion
        self.ultimo_payload: dict[str, Any] | None = None

    def __enter__(self) -> _ClienteLlamaGuardFalso:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def post(self, *args: object, **kwargs: object) -> _RespuestaFalsa:
        self.ultimo_payload = kwargs.get("json")  # type: ignore[assignment]
        if self._excepcion is not None:
            raise self._excepcion
        assert self._contenido is not None
        return _RespuestaFalsa(self._contenido)


def _mockear_cliente(
    monkeypatch: pytest.MonkeyPatch,
    contenido: str | None = None,
    excepcion: Exception | None = None,
) -> _ClienteLlamaGuardFalso:
    cliente_falso = _ClienteLlamaGuardFalso(contenido, excepcion)
    monkeypatch.setattr(mecanismos.httpx, "Client", lambda *a, **k: cliente_falso)
    return cliente_falso


# --- Casos que deben bloquear (unsafe) -------------------------------------


@pytest.mark.parametrize(
    ("direccion", "contenido_respuesta"),
    [
        ("entrada", "unsafe\nS2"),
        ("entrada", "unsafe\nS9,S13"),
        ("salida", "unsafe"),
    ],
)
def test_clasificar_devuelve_true_para_entrada_maliciosa(
    monkeypatch: pytest.MonkeyPatch, direccion: str, contenido_respuesta: str
) -> None:
    _mockear_cliente(monkeypatch, contenido=contenido_respuesta)

    assert clasificar("texto que Llama Guard marcaria como unsafe", direccion) is True


# --- Casos legitimos (safe), no deben bloquear -----------------------------


@pytest.mark.parametrize(
    ("direccion", "contenido_respuesta"),
    [
        ("entrada", "safe"),
        ("salida", "safe"),
        ("entrada", "  Safe  \n"),
    ],
)
def test_clasificar_devuelve_false_para_texto_legitimo(
    monkeypatch: pytest.MonkeyPatch, direccion: str, contenido_respuesta: str
) -> None:
    _mockear_cliente(monkeypatch, contenido=contenido_respuesta)

    assert clasificar("hola, como estas?", direccion) is False


# --- Rol de chat enviado segun direccion (formato Llama Guard 3) -----------


def test_clasificar_envia_rol_user_en_entrada(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente_falso = _mockear_cliente(monkeypatch, contenido="safe")

    clasificar("texto de entrada", "entrada")

    assert cliente_falso.ultimo_payload is not None
    assert cliente_falso.ultimo_payload["messages"][0]["role"] == "user"
    assert cliente_falso.ultimo_payload["model"] == mecanismos.MODELO_CLASIFICADOR


def test_clasificar_envia_rol_assistant_en_salida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cliente_falso = _mockear_cliente(monkeypatch, contenido="safe")

    clasificar("texto de salida", "salida")

    assert cliente_falso.ultimo_payload is not None
    assert cliente_falso.ultimo_payload["messages"][0]["role"] == "assistant"


# --- Fail closed ante error/timeout -----------------------------------------


def test_clasificar_timeout_es_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _mockear_cliente(monkeypatch, excepcion=httpx.TimeoutException("timeout simulado"))

    assert clasificar("cualquier texto", "entrada") is True


def test_clasificar_error_de_conexion_es_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mockear_cliente(
        monkeypatch, excepcion=httpx.ConnectError("conexion rechazada simulada")
    )

    assert clasificar("cualquier texto", "entrada") is True


# --- Respuesta malformada: fail closed, no un default silencioso -----------


def test_clasificar_respuesta_sin_safe_ni_unsafe_es_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mockear_cliente(monkeypatch, contenido="no tengo idea de que responder")

    assert clasificar("cualquier texto", "entrada") is True


def test_clasificar_respuesta_vacia_es_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mockear_cliente(monkeypatch, contenido="")

    assert clasificar("cualquier texto", "entrada") is True


def test_clasificar_direccion_invalida_lanza_value_error() -> None:
    with pytest.raises(ValueError, match="direccion invalida"):
        clasificar("cualquier texto", "lateral")

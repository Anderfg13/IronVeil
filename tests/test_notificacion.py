"""Pruebas de la notificacion de revision humana (proxy/notificacion.py).

Sin receptor real: httpx.post se reemplaza por dobles. Cubren el caso que
notifica, el caso desactivado (sin URL) y el caso de error, que nunca debe
propagarse (criterio de aceptacion: "su fallo no bloquea el resto del
sistema").
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

import proxy.notificacion as notificacion

PETICION: dict[str, Any] = {
    "id": "abc123",
    "modelo": "rrhh",
    "mensaje": "texto con RRHH-DEMO-0000 que no debe salir",
    "vector_probado": "V7-A",
    "motivo": "invocacion_herramienta",
    "herramienta": "enviar_correo",
}


class _RespuestaOk:
    def raise_for_status(self) -> None:
        return None


def test_construir_notificacion_incluye_campos_pedidos_sin_el_mensaje() -> None:
    cuerpo = notificacion.construir_notificacion(PETICION, "C5")

    assert cuerpo["mecanismo_que_detecto"] == "invocacion_herramienta"
    assert cuerpo["configuracion"] == "C5"
    assert cuerpo["vector_probado"] == "V7-A"
    assert cuerpo["id_revision"] == "abc123"
    assert "T" in cuerpo["timestamp"]  # ISO 8601
    assert "mensaje" not in cuerpo
    assert "DEMO" not in str(cuerpo)


def test_enviar_notificacion_exitosa(monkeypatch: pytest.MonkeyPatch) -> None:
    enviados: list[dict[str, Any]] = []

    def _post(url: str, json: dict[str, Any], timeout: float) -> _RespuestaOk:
        enviados.append({"url": url, "json": json})
        return _RespuestaOk()

    monkeypatch.setattr(notificacion.httpx, "post", _post)

    assert notificacion.enviar_notificacion("http://receptor.test/", {"a": 1})
    assert enviados == [{"url": "http://receptor.test/", "json": {"a": 1}}]


def test_enviar_notificacion_fallo_de_red_no_propaga(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _post(*args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("receptor caido")

    monkeypatch.setattr(notificacion.httpx, "post", _post)

    assert notificacion.enviar_notificacion("http://receptor.test/", {}) is False


def test_enviar_notificacion_error_inesperado_no_propaga(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _post(*args: object, **kwargs: object) -> None:
        raise RuntimeError("cualquier cosa")

    monkeypatch.setattr(notificacion.httpx, "post", _post)

    assert notificacion.enviar_notificacion("http://receptor.test/", {}) is False


def test_notificar_sin_url_no_hace_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notificacion, "WEBHOOK_URL", "")
    assert notificacion.notificar_en_revision(PETICION, "C5") is None


def test_notificar_corre_en_segundo_plano(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notificacion.httpx, "post", lambda *a, **k: _RespuestaOk())

    futuro = notificacion.notificar_en_revision(PETICION, "C5", url="http://r.test/")

    assert futuro is not None
    assert futuro.result(timeout=5) is True

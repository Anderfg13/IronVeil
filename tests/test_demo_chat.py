"""Pruebas de la pantalla de chat de la demo (proxy/demo_chat.py).

La pantalla solo se sirve en `GET /demo`; el chat usa `POST /chat`, que no cambia.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import proxy.auth as auth
import proxy.demo_chat as demo_chat
import proxy.main as main

# Cuenta ficticia: solo sirve para activar el login.
_CUENTA = "ana:revisor:" + auth.hashear_clave("clave-de-prueba-123")


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv(auth.ENV_USUARIOS, raising=False)
    return TestClient(main.app)


def test_la_demo_esta_apagada_por_defecto(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(demo_chat.ENV_DEMO, raising=False)

    assert cliente.get("/demo").status_code == 404


@pytest.mark.parametrize("valor", ["", "0", "true", "si"])
def test_solo_el_valor_1_activa_la_demo(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch, valor: str
) -> None:
    monkeypatch.setenv(demo_chat.ENV_DEMO, valor)

    assert cliente.get("/demo").status_code == 404


def test_con_la_demo_activa_se_sirve_la_pantalla_con_cabeceras_de_seguridad(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(demo_chat.ENV_DEMO, "1")

    respuesta = cliente.get("/demo")

    assert respuesta.status_code == 200
    assert "text/html" in respuesta.headers["content-type"]
    assert "default-src 'none'" in respuesta.headers["content-security-policy"]
    assert 'id="mensaje"' in respuesta.text


def test_con_login_activo_sin_sesion_redirige_al_login(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(demo_chat.ENV_DEMO, "1")
    monkeypatch.setenv(auth.ENV_USUARIOS, _CUENTA)

    respuesta = cliente.get("/demo", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/revision/login"


def test_la_demo_no_agrega_endpoints_al_pipeline(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El chat de la demo usa /chat tal cual: no hay un /demo/chat paralelo."""
    monkeypatch.setenv(demo_chat.ENV_DEMO, "1")

    for ruta in ("/demo/chat", "/demo/estado"):
        assert cliente.post(ruta, json={}).status_code in (404, 405)
        assert cliente.get(ruta).status_code == 404

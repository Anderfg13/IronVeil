"""Pruebas de la autenticacion opcional de POST /chat (proxy/auth.py, exigir_cliente).

Las claves se generan en cada ejecucion con `secrets`: no hay credenciales escritas
en el codigo.
"""

from __future__ import annotations

import base64
import secrets

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import proxy.auth as auth
import proxy.main as main

USUARIO = "ana"


@pytest.fixture
def clave() -> str:
    return secrets.token_urlsafe(14)


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, clave: str) -> TestClient:
    """Cuenta valida, autenticacion del chat encendida y limite de intentos limpio."""
    monkeypatch.setenv(
        auth.ENV_USUARIOS, f"{USUARIO}:revisor:{auth.hashear_clave(clave)}"
    )
    monkeypatch.setenv(auth.ENV_CHAT_AUTENTICACION, "1")
    auth.limitador.reiniciar("chat-usuario:" + USUARIO)
    auth.limitador.reiniciar("chat-ip:testclient")
    return TestClient(main.app)


def _basic(usuario: str, clave: str) -> dict[str, str]:
    token = base64.b64encode(f"{usuario}:{clave}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _enviar(
    cliente: TestClient, cabeceras: dict[str, str] | None = None
):  # noqa: ANN202
    return cliente.post(
        "/chat", json={"modelo": "soporte", "mensaje": "hola"}, headers=cabeceras
    )


def _peticion(cabeceras: dict[str, str] | None = None) -> Request:
    crudo = [(k.lower().encode(), v.encode()) for k, v in (cabeceras or {}).items()]
    return Request(
        {"type": "http", "method": "POST", "headers": crudo, "client": ("1.2.3.4", 1)}
    )


def test_apagada_por_defecto_no_pide_credenciales(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(auth.ENV_CHAT_AUTENTICACION, raising=False)
    monkeypatch.delenv(auth.ENV_USUARIOS, raising=False)

    assert auth.exigir_cliente(_peticion()) is None


def test_sin_credenciales_responde_401_con_desafio_basic(cliente: TestClient) -> None:
    respuesta = _enviar(cliente)

    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"].startswith("Basic")


def test_clave_incorrecta_responde_401(cliente: TestClient, clave: str) -> None:
    respuesta = _enviar(cliente, _basic(USUARIO, clave + "x"))

    assert respuesta.status_code == 401


def test_usuario_inexistente_responde_401(cliente: TestClient, clave: str) -> None:
    respuesta = _enviar(cliente, _basic("nadie", clave))

    assert respuesta.status_code == 401


def test_cabecera_basic_mal_formada_responde_401(cliente: TestClient) -> None:
    respuesta = _enviar(cliente, {"Authorization": "Basic %%%no-es-base64"})

    assert respuesta.status_code == 401


def test_credenciales_validas_devuelven_la_identidad(
    cliente: TestClient, clave: str
) -> None:
    identidad = auth.exigir_cliente(_peticion(_basic(USUARIO, clave) | {"x": "y"}))

    assert identidad is not None
    assert identidad.usuario == USUARIO


def test_demasiados_fallos_bloquean_con_429(cliente: TestClient, clave: str) -> None:
    for _ in range(auth.INTENTOS_FALLIDOS_MAXIMOS):
        _enviar(cliente, _basic(USUARIO, "mala-" + clave))

    respuesta = _enviar(cliente, _basic(USUARIO, clave))

    assert respuesta.status_code == 429


def test_falla_cerrada_si_esta_encendida_y_no_hay_cuentas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(auth.ENV_CHAT_AUTENTICACION, "1")
    monkeypatch.delenv(auth.ENV_USUARIOS, raising=False)
    cliente = TestClient(main.app)

    respuesta = _enviar(cliente)

    assert respuesta.status_code == 503


@pytest.mark.parametrize("valor", ["", "0", "true", "si"])
def test_solo_el_valor_1_enciende_la_autenticacion(
    monkeypatch: pytest.MonkeyPatch, valor: str
) -> None:
    monkeypatch.setenv(auth.ENV_CHAT_AUTENTICACION, valor)

    assert auth.chat_auth_requerida() is False


def test_el_estado_de_la_revision_tambien_la_exige(cliente: TestClient) -> None:
    respuesta = cliente.get("/chat/revision/abc123")

    assert respuesta.status_code == 401


def test_la_sesion_de_la_demo_con_csrf_pasa_y_sin_csrf_no(
    cliente: TestClient, clave: str
) -> None:
    identidad = auth.Identidad(USUARIO, auth.ROL_REVISOR)
    token, sesion = auth.sesiones.crear(identidad)
    cookie = {auth.NOMBRE_COOKIE: token}

    sin_csrf = cliente.post(
        "/chat", json={"modelo": "soporte", "mensaje": "hola"}, cookies=cookie
    )
    con_csrf_en_get = cliente.get("/chat/revision/abc123", cookies=cookie)

    assert sin_csrf.status_code == 403
    assert con_csrf_en_get.status_code != 401
    assert sesion.csrf

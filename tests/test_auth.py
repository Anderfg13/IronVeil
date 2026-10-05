"""Pruebas de proxy/auth.py (hash, proveedor local, sesiones y limite de intentos).

Las claves de prueba se generan en cada ejecucion con `secrets`: no hay
credenciales escritas en el codigo.
"""

from __future__ import annotations

import secrets

import pytest

import proxy.auth as auth


def _clave() -> str:
    return secrets.token_urlsafe(14)


# --- Hash -----------------------------------------------------------------------


def test_hash_y_verificacion_de_ida_y_vuelta() -> None:
    clave = _clave()
    almacenado = auth.hashear_clave(clave)

    assert auth.verificar_clave(clave, almacenado)
    assert not auth.verificar_clave(clave + "x", almacenado)


def test_cada_hash_lleva_su_propia_sal() -> None:
    clave = _clave()

    assert auth.hashear_clave(clave) != auth.hashear_clave(clave)


def test_el_hash_es_seguro_para_un_env() -> None:
    almacenado = auth.hashear_clave(_clave())

    assert almacenado.startswith("scrypt.")
    assert not any(c in almacenado for c in "$;|:, \"'")


@pytest.mark.parametrize("roto", ["", "scrypt", "md5.1.2.3.a.b", "scrypt.x.y.z.a.b"])
def test_un_hash_mal_formado_nunca_verifica(roto: str) -> None:
    assert auth.verificar_clave("lo-que-sea", roto) is False


def test_una_clave_demasiado_larga_se_rechaza_sin_calcular() -> None:
    almacenado = auth.hashear_clave(_clave())

    assert (
        auth.verificar_clave("a" * (auth.LONGITUD_MAXIMA_CLAVE + 1), almacenado)
        is False
    )


# --- Proveedor local ------------------------------------------------------------


def _proveedor(clave: str) -> auth.ProveedorLocal:
    hash_clave = auth.hashear_clave(clave)
    return auth.ProveedorLocal.desde_texto(
        f"Ana:revisor:{hash_clave},luis:observador:{hash_clave}"
    )


def test_el_proveedor_autentica_con_rol_y_sin_distinguir_mayusculas_en_el_usuario() -> (
    None
):
    clave = _clave()
    proveedor = _proveedor(clave)

    assert proveedor.autenticar("ANA", clave) == auth.Identidad("ana", "revisor")
    assert proveedor.autenticar("luis", clave).puede_decidir is False  # type: ignore[union-attr]


def test_clave_incorrecta_o_usuario_inexistente_devuelven_none() -> None:
    clave = _clave()
    proveedor = _proveedor(clave)

    assert proveedor.autenticar("ana", clave + "x") is None
    assert proveedor.autenticar("fantasma", clave) is None


@pytest.mark.parametrize(
    "texto",
    [
        "ana:revisor",
        "ana:admin:scrypt.1.2.3.a.b",
        "ana:revisor:md5.x",
        ":revisor:scrypt.a",
    ],
)
def test_una_cuenta_mal_escrita_falla_ruidosamente(texto: str) -> None:
    with pytest.raises(ValueError):
        auth.ProveedorLocal.desde_texto(texto)


def test_la_auth_se_activa_solo_si_hay_cuentas_o_un_proveedor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(auth.ENV_USUARIOS, raising=False)
    assert auth.auth_habilitada() is False

    monkeypatch.setenv(auth.ENV_USUARIOS, "ana:revisor:" + auth.hashear_clave(_clave()))
    assert auth.auth_habilitada() is True


def test_un_proveedor_registrado_reemplaza_al_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Empresa:
        def autenticar(self, usuario: str, clave: str) -> auth.Identidad | None:
            return auth.Identidad(usuario, "revisor") if clave == "ok" else None

    monkeypatch.delenv(auth.ENV_USUARIOS, raising=False)
    auth.registrar_proveedor(_Empresa())
    try:
        assert auth.auth_habilitada() is True
        assert auth.obtener_proveedor().autenticar("sofia", "ok") == auth.Identidad(
            "sofia", "revisor"
        )
    finally:
        auth.registrar_proveedor(None)


# --- Limite de intentos ---------------------------------------------------------


def test_el_limitador_bloquea_tras_los_fallos_y_se_reinicia() -> None:
    limitador = auth.LimitadorIntentos(maximo=3, ventana_s=60)
    for _ in range(2):
        limitador.registrar_fallo("u:ana")
    assert limitador.bloqueado("u:ana") is False

    limitador.registrar_fallo("u:ana")
    assert limitador.bloqueado("u:ana") is True
    assert limitador.bloqueado("u:otra") is False

    limitador.reiniciar("u:ana")
    assert limitador.bloqueado("u:ana") is False


def test_los_fallos_viejos_salen_de_la_ventana(monkeypatch: pytest.MonkeyPatch) -> None:
    reloj = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: reloj[0])
    limitador = auth.LimitadorIntentos(maximo=2, ventana_s=60)
    limitador.registrar_fallo("x")
    limitador.registrar_fallo("x")
    assert limitador.bloqueado("x") is True

    reloj[0] += 61

    assert limitador.bloqueado("x") is False


# --- Sesiones -------------------------------------------------------------------


def test_la_sesion_se_crea_se_renueva_y_se_cierra() -> None:
    gestor = auth.GestorSesiones()
    token, sesion = gestor.crear(auth.Identidad("ana", "revisor"))

    assert gestor.obtener(token) is sesion
    assert gestor.obtener("otro-token") is None
    assert gestor.obtener(None) is None
    assert len(sesion.csrf) >= 24

    gestor.cerrar(token)
    assert gestor.obtener(token) is None


def test_la_sesion_expira_por_inactividad(monkeypatch: pytest.MonkeyPatch) -> None:
    reloj = [5000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: reloj[0])
    monkeypatch.setenv(auth.ENV_SESION_MINUTOS, "10")
    gestor = auth.GestorSesiones()
    token, _ = gestor.crear(auth.Identidad("ana", "revisor"))

    reloj[0] += 9 * 60
    assert gestor.obtener(token) is not None  # renueva la actividad
    reloj[0] += 11 * 60

    assert gestor.obtener(token) is None


def test_hay_un_tope_de_sesiones_abiertas() -> None:
    gestor = auth.GestorSesiones()
    primero, _ = gestor.crear(auth.Identidad("a", "revisor"))
    for _ in range(auth.MAXIMO_SESIONES):
        gestor.crear(auth.Identidad("b", "revisor"))

    assert gestor.obtener(primero) is None


def test_cookie_secure_por_defecto_y_desactivable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(auth.ENV_COOKIE_SECURE, raising=False)
    assert auth.cookie_secure() is True

    monkeypatch.setenv(auth.ENV_COOKIE_SECURE, "0")
    assert auth.cookie_secure() is False

"""Consola en tiempo real (canal SSE `/revision/eventos`) y cuenta de demo.

El canal es un flujo sin fin, asi que se prueba el generador (`flujo_eventos`)
directamente, con un `Request` falso, y no por HTTP: un cliente de pruebas se
quedaria esperando eternamente el final de la respuesta.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import proxy.auth as auth
import proxy.main as main
import proxy.revision_panel as panel
from proxy.cola import ColaRevision

RAPIDO = 0.05  # latido corto para que las pruebas no esperen 15 s


class _PeticionFalsa:
    """Lo unico que `flujo_eventos` usa de un Request."""

    def __init__(self, desconectada: bool = False) -> None:
        self.desconectada = desconectada
        self.cookies: dict[str, str] = {}

    async def is_disconnected(self) -> bool:
        return self.desconectada


def _flujo(
    cola_revision: ColaRevision,
    token: str | None = None,
    latido_s: float = 5.0,
    desconectada: bool = False,
) -> Any:
    peticion = _PeticionFalsa(desconectada)
    return panel.flujo_eventos(peticion, cola_revision, token, latido_s)  # type: ignore[arg-type]


def _correr(corrutina: Any) -> Any:
    return asyncio.run(corrutina)


def _peticion() -> dict[str, Any]:
    return {"modelo": "soporte", "mensaje": "hola", "motivo": "filtrado"}


@pytest.fixture(autouse=True)
def _sin_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(auth.ENV_USUARIOS, raising=False)
    monkeypatch.setattr(panel, "_flujos_abiertos", 0)


# --- La cola avisa de sus cambios ---------------------------------------------


def test_la_cola_avisa_al_encolar_y_al_retirar() -> None:
    avisos: list[int] = []
    c = ColaRevision()
    c.suscribir(lambda: avisos.append(1))

    c.encolar({"id": "a"})
    c.retirar("a")

    assert len(avisos) == 2


def test_la_cola_no_avisa_si_no_cambio_nada() -> None:
    avisos: list[int] = []
    c = ColaRevision(tamano_maximo=1)
    c.encolar({"id": "a"})
    c.suscribir(lambda: avisos.append(1))

    assert c.encolar({"id": "b"}) is False  # cola llena: no cambia
    with pytest.raises(KeyError):
        c.retirar("no-existe")

    assert avisos == []


def test_un_oyente_roto_no_impide_encolar_ni_avisa_a_los_demas() -> None:
    avisos: list[int] = []
    c = ColaRevision()

    def roto() -> None:
        raise RuntimeError("falla a proposito")

    c.suscribir(roto)
    c.suscribir(lambda: avisos.append(1))

    assert c.encolar({"id": "a"}) is True
    assert avisos == [1]
    assert c.tamano() == 1


def test_cancelar_deja_de_avisar_y_es_idempotente() -> None:
    avisos: list[int] = []
    c = ColaRevision()
    aviso: Callable[[], None] = lambda: avisos.append(1)  # noqa: E731
    c.suscribir(aviso)
    c.cancelar(aviso)
    c.cancelar(aviso)

    c.encolar({"id": "a"})

    assert avisos == []


# --- El generador del canal ---------------------------------------------------


def test_al_conectar_manda_el_reintento_y_luego_avisa_cada_cambio() -> None:
    async def escenario() -> list[bytes]:
        c = ColaRevision()
        flujo = _flujo(c)
        recibidos = [await anext(flujo)]
        c.encolar(_peticion())
        recibidos.append(await anext(flujo))
        await flujo.aclose()
        return recibidos

    recibidos = _correr(escenario())

    assert recibidos[0] == b"retry: 3000\n\n"
    assert recibidos[1] == b"event: cambio\ndata: {}\n\n"


def test_el_aviso_no_lleva_datos_de_la_peticion() -> None:
    async def escenario() -> bytes:
        c = ColaRevision()
        flujo = _flujo(c)
        await anext(flujo)
        c.encolar({"id": "x", "mensaje": "SPT-DEMO-0000 secreto", "motivo": "filtrado"})
        aviso = await anext(flujo)
        await flujo.aclose()
        return aviso

    aviso = _correr(escenario())

    assert b"SPT-DEMO" not in aviso
    assert b"secreto" not in aviso
    assert aviso.endswith(b"data: {}\n\n")


def test_varios_cambios_seguidos_se_funden_en_un_solo_aviso() -> None:
    async def escenario() -> list[bytes]:
        c = ColaRevision()
        flujo = _flujo(c, latido_s=RAPIDO)
        await anext(flujo)
        for _ in range(5):
            c.encolar(_peticion())
        recibidos = [await anext(flujo), await anext(flujo)]
        await flujo.aclose()
        return recibidos

    recibidos = _correr(escenario())

    assert recibidos[0] == b"event: cambio\ndata: {}\n\n"
    assert (
        recibidos[1] == b": latido\n\n"
    )  # el siguiente ya es un latido, no otro cambio


def test_sin_cambios_manda_un_latido() -> None:
    async def escenario() -> bytes:
        flujo = _flujo(ColaRevision(), latido_s=RAPIDO)
        await anext(flujo)
        latido = await anext(flujo)
        await flujo.aclose()
        return latido

    assert _correr(escenario()) == b": latido\n\n"


def test_si_el_navegador_se_fue_el_flujo_termina_sin_esperar_mas() -> None:
    async def escenario() -> list[bytes]:
        flujo = panel.flujo_eventos(
            _PeticionFalsa(desconectada=True), ColaRevision(), None, latido_s=RAPIDO  # type: ignore[arg-type]
        )
        return [parte async for parte in flujo]

    assert _correr(escenario()) == [b"retry: 3000\n\n"]


def test_al_terminar_deja_de_escuchar_y_libera_su_cupo() -> None:
    async def escenario() -> tuple[int, int, int, int]:
        c = ColaRevision()
        flujo = _flujo(c)
        await anext(flujo)
        durante = (len(c._suscriptores), panel.flujos_en_vivo())
        await flujo.aclose()
        return (*durante, len(c._suscriptores), panel.flujos_en_vivo())

    assert _correr(escenario()) == (1, 1, 0, 0)


def test_sin_cupo_avisa_que_esta_lleno_y_no_escucha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(panel, "MAXIMO_FLUJOS_EN_VIVO", 1)

    async def escenario() -> tuple[list[bytes], int]:
        c = ColaRevision()
        primero = _flujo(c)
        await anext(primero)
        segundo = [parte async for parte in _flujo(c)]
        suscriptores = len(c._suscriptores)
        await primero.aclose()
        return segundo, suscriptores

    segundo, suscriptores = _correr(escenario())

    assert segundo == [b"event: lleno\ndata: {}\n\n"]
    assert suscriptores == 1  # solo el primero


# --- Sesion --------------------------------------------------------------------


def test_con_login_y_sin_sesion_el_canal_avisa_y_se_cierra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(auth.ENV_USUARIOS, "ana:revisor:" + auth.hashear_clave("x" * 12))

    async def escenario() -> list[bytes]:
        flujo = _flujo(ColaRevision(), "token-ajeno")
        return [parte async for parte in flujo]

    assert _correr(escenario()) == [b"retry: 3000\n\n", b"event: sesion\ndata: {}\n\n"]


def test_el_canal_avisa_cuando_la_sesion_vence_a_mitad_de_conexion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(auth.ENV_USUARIOS, "ana:revisor:" + auth.hashear_clave("x" * 12))
    token, sesion = auth.sesiones.crear(auth.Identidad("ana", auth.ROL_REVISOR))

    async def escenario() -> list[bytes]:
        c = ColaRevision()
        flujo = _flujo(c, token, RAPIDO)
        recibidos = [await anext(flujo)]
        sesion.ultima_actividad -= 10 * 3600  # simula una sesion inactiva
        recibidos += [parte async for parte in flujo]
        return recibidos

    try:
        recibidos = _correr(escenario())
    finally:
        auth.sesiones.vaciar()

    assert recibidos[-1] == b"event: sesion\ndata: {}\n\n"


def test_consultar_la_sesion_sin_actualizar_no_la_mantiene_viva() -> None:
    token, sesion = auth.sesiones.crear(auth.Identidad("ana", auth.ROL_REVISOR))
    try:
        sesion.ultima_actividad -= (
            100  # hace "mucho": no depende de la resolucion del reloj
        )
        antes = sesion.ultima_actividad
        assert auth.sesiones.obtener(token, False) is sesion
        assert sesion.ultima_actividad == antes

        assert auth.sesiones.obtener(token) is sesion  # el uso normal si la renueva
        assert sesion.ultima_actividad > antes
    finally:
        auth.sesiones.vaciar()


def test_el_endpoint_exige_sesion_cuando_el_login_esta_activo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(auth.ENV_USUARIOS, "ana:revisor:" + auth.hashear_clave("x" * 12))

    respuesta = TestClient(main.app).get("/revision/eventos")

    assert respuesta.status_code == 401


def test_el_endpoint_responde_como_flujo_de_eventos_con_cabeceras_de_seguridad() -> (
    None
):
    async def escenario() -> Any:
        respuesta = await panel.eventos_en_vivo(_PeticionFalsa(), None)  # type: ignore[arg-type]
        await respuesta.body_iterator.aclose()  # type: ignore[attr-defined]
        return respuesta

    respuesta = _correr(escenario())

    assert respuesta.media_type == "text/event-stream"
    assert respuesta.headers["cache-control"] == "no-store"
    assert respuesta.headers["x-accel-buffering"] == "no"  # sin buffer en proxies
    assert "default-src 'none'" in respuesta.headers["content-security-policy"]


# --- Cliente de la consola -----------------------------------------------------

JS = (panel.DIRECTORIO_ESTATICO / "revision.js").read_text(encoding="utf-8")


def test_la_consola_se_conecta_al_canal_y_recarga_con_cada_aviso() -> None:
    assert 'new EventSource("/revision/eventos")' in JS
    assert re.search(r'addEventListener\("cambio", \(\) => cargar\(\)\)', JS)


def test_si_la_sesion_vence_el_canal_lleva_al_login() -> None:
    assert re.search(r'addEventListener\("sesion".*?/revision/login', JS)


def test_el_sondeo_queda_solo_como_respaldo() -> None:
    assert "!estado.enVivo || Date.now() - estado.ultimaCarga > RESPALDO_MS" in JS
    assert "RESPALDO_MS = 30000" in JS


def test_los_avisos_seguidos_no_lanzan_una_carga_por_aviso() -> None:
    assert "if (cargando) { recargar = true; return; }" in JS


def test_el_encabezado_dice_tiempo_real_solo_si_el_canal_esta_vivo() -> None:
    assert 'estado.enVivo ? " · tiempo real"' in JS


# --- Cuenta de demo ------------------------------------------------------------


def _clave_guardada(directorio: Path) -> str:
    texto = (directorio / auth.ARCHIVO_CLAVE_DEMO).read_text(encoding="utf-8")
    return texto.split("Clave: ")[1].strip()


def test_la_cuenta_de_demo_se_crea_con_clave_aleatoria_que_funciona(
    tmp_path: Path,
) -> None:
    env = tmp_path / auth.ARCHIVO_ENV
    env.write_text("BASE_MODEL=llama3.2\nNOTIFICAR_X=1\n", encoding="utf-8")

    usuario = auth.crear_cuenta_demo(tmp_path)

    assert usuario == "admin"
    lineas = env.read_text(encoding="utf-8").splitlines()
    assert "BASE_MODEL=llama3.2" in lineas  # el resto del .env sigue igual
    assert "NOTIFICAR_X=1" in lineas
    entrada = next(x for x in lineas if x.startswith("REVISION_USUARIOS="))
    clave = _clave_guardada(tmp_path)
    proveedor = auth.ProveedorLocal.desde_texto(entrada.split("=", 1)[1])
    identidad = proveedor.autenticar("admin", clave)
    assert identidad is not None
    assert identidad.rol == auth.ROL_REVISOR
    assert proveedor.autenticar("admin", clave + "x") is None


def test_cada_cuenta_de_demo_tiene_una_clave_distinta(tmp_path: Path) -> None:
    claves = set()
    for i in range(3):
        directorio = tmp_path / f"d{i}"
        directorio.mkdir()
        auth.crear_cuenta_demo(directorio)
        claves.add(_clave_guardada(directorio))

    assert len(claves) == 3
    assert min(len(c) for c in claves) >= 12


def test_la_funcion_no_acepta_rutas_de_archivo_sino_solo_un_directorio(
    tmp_path: Path,
) -> None:
    """Los nombres de archivo son fijos: ningun argumento puede apuntar a otro lado."""
    auth.crear_cuenta_demo(tmp_path)

    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [auth.ARCHIVO_ENV, auth.ARCHIVO_CLAVE_DEMO]
    )


def test_no_pisa_cuentas_existentes_sin_forzar(tmp_path: Path) -> None:
    env = tmp_path / auth.ARCHIVO_ENV
    env.write_text("REVISION_USUARIOS=ana:revisor:hash-ajeno\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        auth.crear_cuenta_demo(tmp_path)

    assert "ana:revisor:hash-ajeno" in env.read_text(encoding="utf-8")
    assert not (tmp_path / auth.ARCHIVO_CLAVE_DEMO).exists()


def test_con_forzar_reemplaza_las_cuentas_existentes(tmp_path: Path) -> None:
    env = tmp_path / auth.ARCHIVO_ENV
    env.write_text("REVISION_USUARIOS=ana:revisor:hash-ajeno\n", encoding="utf-8")

    auth.crear_cuenta_demo(tmp_path, forzar=True)

    assert "ana:revisor:hash-ajeno" not in env.read_text(encoding="utf-8")


def test_una_linea_vacia_de_cuentas_se_reemplaza_sin_duplicarla(
    tmp_path: Path,
) -> None:
    env = tmp_path / auth.ARCHIVO_ENV
    env.write_text("A=1\r\nREVISION_USUARIOS=\r\nB=2\r\n", encoding="utf-8", newline="")

    auth.crear_cuenta_demo(tmp_path)

    crudo = env.read_bytes().decode("utf-8")
    assert crudo.count("REVISION_USUARIOS=") == 1
    assert crudo.startswith("A=1\r\n")
    assert crudo.rstrip().endswith("B=2")


def test_el_env_conserva_los_saltos_de_linea_crlf(tmp_path: Path) -> None:
    env = tmp_path / auth.ARCHIVO_ENV
    env.write_text("A=1\r\nB=2\r\n", encoding="utf-8", newline="")

    auth.crear_cuenta_demo(tmp_path)

    crudo = env.read_bytes().decode("utf-8")
    assert "\r\n" in crudo
    assert "\n" not in crudo.replace("\r\n", "")  # ningun salto suelto


def test_el_comando_no_imprime_la_clave(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    codigo = auth.cli(["--demo"])
    salida = capsys.readouterr()

    assert codigo == 0
    secreto = _clave_guardada(tmp_path)
    assert secreto not in salida.out + salida.err
    assert auth.ARCHIVO_CLAVE_DEMO in salida.out


def test_la_clave_de_demo_no_esta_en_el_repositorio() -> None:
    ignorado = (Path(__file__).resolve().parent.parent / ".gitignore").read_text(
        encoding="utf-8"
    )

    assert auth.ARCHIVO_CLAVE_DEMO in ignorado

"""La entrega desacoplada: un SIEM lento o caido no puede frenar ni romper el chat."""

from __future__ import annotations

import threading
import time

import pytest

from proxy.siem import ConectorAsincrono, ErrorSIEM


class _Destino:
    """Un conector falso: registra lo recibido y falla las veces que se le pida."""

    def __init__(self, fallos: list[ErrorSIEM] | None = None) -> None:
        self.recibidos: list[str] = []
        self.intentos = 0
        self.cerrado = False
        self._fallos = list(fallos or [])

    def enviar(self, mensaje: str) -> None:
        self.intentos += 1
        if self._fallos:
            raise self._fallos.pop(0)
        self.recibidos.append(mensaje)

    def cerrar(self) -> None:
        self.cerrado = True


class _Bloqueado:
    """Un destino que no responde hasta que se le libera."""

    def __init__(self) -> None:
        self.liberar = threading.Event()
        self.entro = threading.Event()
        self.recibidos: list[str] = []

    def enviar(self, mensaje: str) -> None:
        self.entro.set()
        self.liberar.wait(5)
        self.recibidos.append(mensaje)


def _asincrono(destino: object, **kwargs: float) -> ConectorAsincrono:
    return ConectorAsincrono(destino, espera_base=0, **kwargs)  # type: ignore[arg-type]


def test_entrega_en_orden_y_cerrar_vacia_lo_pendiente() -> None:
    destino = _Destino()
    conector = _asincrono(destino)

    for numero in range(5):
        conector.enviar(f"evento-{numero}")
    conector.cerrar()

    assert destino.recibidos == [f"evento-{n}" for n in range(5)]
    assert conector.enviados == 5
    assert destino.cerrado


def test_enviar_no_espera_a_un_destino_lento() -> None:
    destino = _Bloqueado()
    conector = _asincrono(destino)

    inicio = time.perf_counter()
    conector.enviar("uno")
    conector.enviar("dos")
    espera = time.perf_counter() - inicio
    destino.liberar.set()
    conector.cerrar()

    assert espera < 0.5  # el chat no depende del SIEM
    assert destino.recibidos == ["uno", "dos"]


def test_un_fallo_pasajero_se_reintenta_y_se_entrega() -> None:
    destino = _Destino(fallos=[ErrorSIEM("caido"), ErrorSIEM("caido")])
    conector = _asincrono(destino, intentos=3)

    conector.enviar("evento")
    conector.cerrar()

    assert destino.recibidos == ["evento"]
    assert destino.intentos == 3
    assert conector.fallidos == 0


def test_un_fallo_que_no_cambia_no_se_reintenta(
    caplog: pytest.LogCaptureFixture,
) -> None:
    destino = _Destino(fallos=[ErrorSIEM("clave rechazada", reintentable=False)])
    conector = _asincrono(destino, intentos=3)

    with caplog.at_level("ERROR"):
        conector.enviar("evento")
        conector.cerrar()

    assert destino.intentos == 1
    assert conector.fallidos == 1
    assert "clave rechazada" in caplog.text
    assert "evento" not in caplog.text.replace("evento no entregado", "")


def test_tras_agotar_los_intentos_cuenta_el_fallo_y_sigue_con_el_siguiente() -> None:
    destino = _Destino(fallos=[ErrorSIEM("a"), ErrorSIEM("b")])
    conector = _asincrono(destino, intentos=2)

    conector.enviar("perdido")
    conector.enviar("llega")
    conector.cerrar()

    assert destino.recibidos == ["llega"]
    assert conector.fallidos == 1
    assert conector.enviados == 1


def test_un_error_inesperado_de_un_conector_ajeno_no_mata_el_hilo(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Roto:
        llamadas = 0

        def enviar(self, mensaje: str) -> None:
            Roto.llamadas += 1
            if Roto.llamadas == 1:
                raise RuntimeError("falla del conector ajeno")

    conector = _asincrono(Roto())

    with caplog.at_level("ERROR"):
        conector.enviar("uno")
        conector.enviar("dos")
        conector.cerrar()

    assert Roto.llamadas == 2
    assert conector.fallidos == 1
    assert conector.enviados == 1


def test_si_la_cola_se_llena_descarta_lo_nuevo_y_lo_cuenta(
    caplog: pytest.LogCaptureFixture,
) -> None:
    destino = _Bloqueado()
    conector = ConectorAsincrono(destino, capacidad=2, espera_base=0)  # type: ignore[arg-type]
    conector.enviar("en-curso")
    assert destino.entro.wait(2)  # el hilo ya lo tomo: la cola esta vacia

    with caplog.at_level("WARNING"):
        for numero in range(5):
            conector.enviar(f"e{numero}")  # caben 2; los otros 3 se descartan

    assert conector.descartados == 3
    assert "cola llena" in caplog.text
    destino.liberar.set()
    conector.cerrar()
    assert destino.recibidos == ["en-curso", "e0", "e1"]


def test_cerrar_dos_veces_no_falla() -> None:
    destino = _Destino()
    conector = _asincrono(destino)

    conector.cerrar()
    conector.cerrar()

    assert destino.cerrado


def test_un_destino_sin_cerrar_tambien_sirve() -> None:
    class SinCerrar:
        def enviar(self, mensaje: str) -> None:
            pass

    conector = _asincrono(SinCerrar())

    conector.cerrar()  # no debe fallar aunque el destino no tenga cerrar()

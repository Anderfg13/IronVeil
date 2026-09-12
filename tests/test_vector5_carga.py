"""Pruebas unitarias de las funciones puras de ataques/vector5_carga.py.

Solo cubre la parte sin red (generacion de mensaje, validaciones y
clasificacion de resultado). La rafaga concurrente real contra un proxy
vivo se corre manualmente contra el stack del equipo, no en esta suite.
"""

from __future__ import annotations

import pytest

from ataques.vector5_carga import (
    clasificar_resultado,
    generar_mensaje,
    validar_configuracion_consistente,
    validar_host_laboratorio_propio,
)


def test_generar_mensaje_distinto_para_mismo_indice() -> None:
    a = generar_mensaje(1)
    b = generar_mensaje(1)

    assert a != b
    assert "1" in a


def test_generar_mensaje_respeta_plantilla_custom() -> None:
    mensaje = generar_mensaje(7, plantilla="ticket {i} / {nonce}")

    assert mensaje.startswith("ticket 7 / ")


@pytest.mark.parametrize(
    ("host", "permitir_remoto", "debe_fallar"),
    [
        ("localhost", False, False),
        ("127.0.0.1", False, False),
        ("proxy", False, False),
        ("ataque.example.com", False, True),
        ("ataque.example.com", True, False),
    ],
)
def test_validar_host_laboratorio_propio(
    host: str, permitir_remoto: bool, debe_fallar: bool
) -> None:
    url = f"http://{host}:8000/chat"

    if debe_fallar:
        with pytest.raises(ValueError, match=host):
            validar_host_laboratorio_propio(url, permitir_remoto)
    else:
        validar_host_laboratorio_propio(url, permitir_remoto)


def test_validar_configuracion_c0_exige_todo_apagado() -> None:
    validar_configuracion_consistente("C0", [])

    with pytest.raises(ValueError, match="C0"):
        validar_configuracion_consistente("C0", ["filtrado"])


def test_validar_configuracion_c6_exige_los_cinco() -> None:
    cinco = [
        "filtrado",
        "delimitacion",
        "clasificacion",
        "minimo_privilegio",
        "aprobacion_humana",
    ]
    validar_configuracion_consistente("C6", cinco)

    with pytest.raises(ValueError, match="C6"):
        validar_configuracion_consistente("C6", ["filtrado"])


def test_validar_configuracion_c1_solo_filtrado() -> None:
    validar_configuracion_consistente("C1", ["filtrado"])

    with pytest.raises(ValueError, match="C1"):
        validar_configuracion_consistente("C1", ["delimitacion"])

    with pytest.raises(ValueError, match="C1"):
        validar_configuracion_consistente("C1", ["filtrado", "clasificacion"])


def test_clasificar_resultado_permitido_normal() -> None:
    resultado, mecanismo = clasificar_resultado([], status_code=200, excepcion=None)

    assert resultado == "permitido_normal"
    assert mecanismo is None


def test_clasificar_resultado_exitoso_para_atacante_por_5xx() -> None:
    resultado, mecanismo = clasificar_resultado([], status_code=503, excepcion=None)

    assert resultado == "exitoso_para_atacante"
    assert mecanismo is None


def test_clasificar_resultado_exitoso_para_atacante_por_excepcion() -> None:
    resultado, mecanismo = clasificar_resultado(
        [], status_code=None, excepcion=TimeoutError("timeout")
    )

    assert resultado == "exitoso_para_atacante"
    assert mecanismo is None


def test_clasificar_resultado_bloqueado_con_mecanismo_activo() -> None:
    resultado, mecanismo = clasificar_resultado(
        ["aprobacion_humana"], status_code=429, excepcion=None
    )

    assert resultado == "bloqueado"
    assert mecanismo == "aprobacion_humana"


def test_clasificar_resultado_bloqueo_sin_mecanismo_activo_es_anomalia() -> None:
    with pytest.raises(ValueError, match="aprobacion_humana"):
        clasificar_resultado([], status_code=429, excepcion=None)


def test_clasificar_resultado_status_bloqueo_configurable() -> None:
    resultado, mecanismo = clasificar_resultado(
        ["aprobacion_humana"], status_code=503, excepcion=None, status_bloqueo=503
    )

    assert resultado == "bloqueado"
    assert mecanismo == "aprobacion_humana"

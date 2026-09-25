"""Pruebas unitarias de las funciones puras de ataques/vector5_carga.py.

Solo cubre la parte sin red (generacion de mensaje, validaciones y
clasificacion de resultado). La rafaga concurrente real contra un proxy
vivo se corre manualmente contra el stack del equipo, no en esta suite.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest

from ataques.vector5_carga import (
    _REPO_ROOT,
    clasificar_resultado,
    ejecutar_rafaga,
    generar_mensaje,
    validar_configuracion_consistente,
    validar_host_laboratorio_propio,
    validar_ruta_salida_segura,
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


# --- ejecutar_rafaga() revalida el host (CWE-918, SSRF) -------------------


def test_ejecutar_rafaga_rechaza_host_fuera_del_laboratorio_antes_de_la_red() -> None:
    """No debe llegar a abrir ningun socket: falla en la validacion, antes
    de `async with httpx.AsyncClient()`."""
    with pytest.raises(ValueError, match="laboratorio propio"):
        asyncio.run(
            ejecutar_rafaga(
                url="http://ataque.example.com:8000/chat",
                modelo="soporte",
                concurrencia=1,
                duracion_s=1.0,
                mecanismos_activos=[],
                configuracion="C0",
                vector="V5-D",
                plantilla="hola {i} {nonce}",
                timeout_peticion=1.0,
                status_bloqueo=429,
                salida=io.StringIO(),
            )
        )


# --- validar_ruta_salida_segura() (CWE-22, path traversal) ---------------


def test_validar_ruta_salida_segura_acepta_ruta_dentro_del_repo() -> None:
    ruta = _REPO_ROOT / "resultados" / "2026-01-01" / "archivo.jsonl"

    resuelta = validar_ruta_salida_segura(ruta)

    assert resuelta == ruta.resolve()


def test_validar_ruta_salida_segura_rechaza_ruta_fuera_del_repo() -> None:
    ruta_fuera = _REPO_ROOT / ".." / "fuera_del_repo" / "archivo.jsonl"

    with pytest.raises(ValueError, match="fuera de"):
        validar_ruta_salida_segura(ruta_fuera)


def test_validar_ruta_salida_segura_rechaza_traversal_con_puntos() -> None:
    ruta_traversal = _REPO_ROOT / "resultados" / ".." / ".." / "etc" / "passwd"

    with pytest.raises(ValueError, match="fuera de"):
        validar_ruta_salida_segura(ruta_traversal)


def test_validar_ruta_salida_segura_respeta_base_custom(tmp_path: Path) -> None:
    dentro = tmp_path / "sub" / "archivo.jsonl"

    resuelta = validar_ruta_salida_segura(dentro, base=tmp_path)

    assert resuelta == dentro.resolve()


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

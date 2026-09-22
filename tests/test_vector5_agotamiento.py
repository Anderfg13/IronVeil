"""Pruebas unitarias de las funciones puras de ataques/vector5_agotamiento.py.

Solo cubre resumir() y detectar_degradacion() (agregacion y la heuristica
de degradacion). Las rafagas reales via ejecutar_niveles() se corren
manualmente contra el stack del equipo, no en esta suite -- ejecutar_rafaga
en si ya esta probada donde vive, en test_vector5_carga.py.
"""

from __future__ import annotations

from ataques.vector5_agotamiento import (
    FACTOR_DEGRADACION_P95,
    ResumenNivel,
    detectar_degradacion,
    resumir,
)
from ataques.vector5_carga import ResultadoPeticion


def _peticion(resultado: str, latencia_ms: int) -> ResultadoPeticion:
    return ResultadoPeticion(
        timestamp="2026-09-22T00:00:00+00:00",
        configuracion="C0",
        mecanismos_activos=[],
        vector_probado="V5-D",
        modelo_destino="soporte",
        resultado=resultado,
        mecanismo_que_bloqueo="aprobacion_humana" if resultado == "bloqueado" else None,
        latencia_ms=latencia_ms,
        nivel_carga=10,
    )


# --- resumir() ---------------------------------------------------------


def test_resumir_cuenta_cada_resultado_por_separado() -> None:
    resultados = [
        _peticion("permitido_normal", 100),
        _peticion("permitido_normal", 200),
        _peticion("bloqueado", 5),
        _peticion("exitoso_para_atacante", 30000),
    ]

    resumen = resumir(10, resultados)

    assert resumen.nivel_carga == 10
    assert resumen.total == 4
    assert resumen.permitidos == 2
    assert resumen.bloqueados == 1
    assert resumen.exitosos_atacante == 1


def test_resumir_calcula_percentiles_de_latencia() -> None:
    resultados = [_peticion("permitido_normal", ms) for ms in (100, 200, 300, 400, 500)]

    resumen = resumir(10, resultados)

    assert resumen.max_ms == 500
    assert resumen.p50_ms <= resumen.p95_ms <= resumen.max_ms


def test_resumir_lista_vacia_no_falla() -> None:
    resumen = resumir(100, [])

    assert resumen.total == 0
    assert resumen.p50_ms == 0
    assert resumen.max_ms == 0


# --- detectar_degradacion() ---------------------------------------------


def test_detectar_degradacion_sin_resumenes() -> None:
    hubo, explicacion = detectar_degradacion([])

    assert hubo is False
    assert "sin datos" in explicacion


def test_detectar_degradacion_por_exitoso_para_atacante() -> None:
    resumenes = [
        ResumenNivel(
            10,
            total=10,
            bloqueados=0,
            exitosos_atacante=0,
            permitidos=10,
            p50_ms=100,
            p95_ms=150,
            max_ms=200,
        ),
        ResumenNivel(
            100,
            total=10,
            bloqueados=0,
            exitosos_atacante=3,
            permitidos=7,
            p50_ms=110,
            p95_ms=160,
            max_ms=210,
        ),
    ]

    hubo, explicacion = detectar_degradacion(resumenes)

    assert hubo is True
    assert (
        "exitoso_para_atacante" in explicacion.lower()
        or "timeout" in explicacion.lower()
    )


def test_detectar_degradacion_por_p95_disparado() -> None:
    resumenes = [
        ResumenNivel(
            10,
            total=10,
            bloqueados=0,
            exitosos_atacante=0,
            permitidos=10,
            p50_ms=100,
            p95_ms=150,
            max_ms=200,
        ),
        ResumenNivel(
            100,
            total=10,
            bloqueados=0,
            exitosos_atacante=0,
            permitidos=10,
            p50_ms=8000,
            p95_ms=150 * FACTOR_DEGRADACION_P95,
            max_ms=20000,
        ),
    ]

    hubo, explicacion = detectar_degradacion(resumenes)

    assert hubo is True
    assert "p95" in explicacion


def test_detectar_degradacion_no_se_activa_por_bloqueados() -> None:
    # aprobacion_humana encolando muchas peticiones (bloqueado) no es
    # degradacion -- es justo lo que se espera que haga bien (CLAUDE.md
    # seccion 9: "encolar no es rechazar").
    resumenes = [
        ResumenNivel(
            10,
            total=10,
            bloqueados=2,
            exitosos_atacante=0,
            permitidos=8,
            p50_ms=100,
            p95_ms=150,
            max_ms=200,
        ),
        ResumenNivel(
            100,
            total=100,
            bloqueados=90,
            exitosos_atacante=0,
            permitidos=10,
            p50_ms=110,
            p95_ms=160,
            max_ms=220,
        ),
    ]

    hubo, explicacion = detectar_degradacion(resumenes)

    assert hubo is False
    assert "sin señal" in explicacion.lower()


def test_detectar_degradacion_latencia_estable_no_se_marca() -> None:
    resumenes = [
        ResumenNivel(
            10,
            total=10,
            bloqueados=0,
            exitosos_atacante=0,
            permitidos=10,
            p50_ms=100,
            p95_ms=150,
            max_ms=200,
        ),
        ResumenNivel(
            50,
            total=10,
            bloqueados=0,
            exitosos_atacante=0,
            permitidos=10,
            p50_ms=105,
            p95_ms=155,
            max_ms=210,
        ),
        ResumenNivel(
            100,
            total=10,
            bloqueados=0,
            exitosos_atacante=0,
            permitidos=10,
            p50_ms=120,
            p95_ms=200,
            max_ms=250,
        ),
    ]

    hubo, _explicacion = detectar_degradacion(resumenes)

    assert hubo is False

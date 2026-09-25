"""Pruebas de analisis/comparar_v5_c0_c5.py (consolidacion de V5, C0 vs. C5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analisis.comparar_v5_c0_c5 import (
    HARDWARE_COLAB,
    HARDWARE_LOCAL,
    calcular_punto_degradacion,
    calcular_tabla_comparativa,
    calcular_tabla_por_nivel,
    cargar_corridas_v5,
)


def _escribir(
    directorio: Path,
    nombre: str,
    config: str,
    nivel: int,
    eventos: list[tuple[str, int]],
) -> None:
    lineas = [
        json.dumps(
            {
                "configuracion": config,
                "resultado": resultado,
                "latencia_ms": latencia,
                "nivel_carga": nivel,
            }
        )
        for resultado, latencia in eventos
    ]
    (directorio / nombre).write_text("\n".join(lineas) + "\n", encoding="utf-8")


@pytest.fixture
def corrida(tmp_path: Path) -> Path:
    """Nivel 2: ambas sanas. Nivel 4: C0 cae por timeout, C5 bloquea (429)."""
    _escribir(
        tmp_path,
        "vector5_agotamiento_C0_c2.jsonl",
        "C0",
        2,
        [("permitido_normal", 1000), ("permitido_normal", 1200)],
    )
    _escribir(
        tmp_path,
        "vector5_agotamiento_C5_c2.jsonl",
        "C5",
        2,
        [("permitido_normal", 1000), ("permitido_normal", 1100)],
    )
    _escribir(
        tmp_path,
        "vector5_agotamiento_C0_c4.jsonl",
        "C0",
        4,
        [("exitoso_para_atacante", 90000), ("permitido_normal", 3000)],
    )
    _escribir(
        tmp_path,
        "vector5_agotamiento_C5_c4.jsonl",
        "C5",
        4,
        [
            ("bloqueado", 20),
            ("bloqueado", 30),
            ("bloqueado", 25),
            ("permitido_normal", 1500),
        ],
    )
    # Mismo nivel en otra corrida (_colab): no debe mezclarse con la local.
    _escribir(
        tmp_path,
        "vector5_agotamiento_C0_colab_c2.jsonl",
        "C0",
        2,
        [("permitido_normal", 500)],
    )
    (tmp_path / "vector5_agotamiento_C0_resumen.json").write_text(
        "{}", encoding="utf-8"
    )
    return tmp_path


def test_cargar_corridas_separa_hardware_por_sufijo(corrida: Path) -> None:
    df = cargar_corridas_v5(corrida)

    assert set(df["hardware"]) == {HARDWARE_LOCAL, HARDWARE_COLAB}
    assert len(df[df["hardware"] == HARDWARE_COLAB]) == 1
    assert len(df) == 11  # el *_resumen.json no se lee


def test_cargar_corridas_falla_si_el_nivel_no_coincide_con_el_archivo(
    tmp_path: Path,
) -> None:
    _escribir(
        tmp_path,
        "vector5_agotamiento_C0_c10.jsonl",
        "C0",
        50,
        [("permitido_normal", 1)],
    )

    with pytest.raises(ValueError, match="no coincide"):
        cargar_corridas_v5(tmp_path)


def test_cargar_corridas_falla_con_resultado_fuera_de_esquema(tmp_path: Path) -> None:
    _escribir(tmp_path, "vector5_agotamiento_C0_c2.jsonl", "C0", 2, [("caido", 1)])

    with pytest.raises(ValueError, match="fuera de esquema"):
        cargar_corridas_v5(tmp_path)


def test_cargar_corridas_falla_sin_archivos(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        cargar_corridas_v5(tmp_path)


def test_tabla_comparativa_pone_c0_y_c5_lado_a_lado(corrida: Path) -> None:
    por_nivel = calcular_tabla_por_nivel(cargar_corridas_v5(corrida))
    local = por_nivel[por_nivel["hardware"] == HARDWARE_LOCAL]

    comparativa = calcular_tabla_comparativa(local).set_index("Nivel (concurrencia)")

    assert comparativa.loc[4, "C0 ASR (%)"] == 50.0
    assert comparativa.loc[4, "C0 timeouts/total"] == "1/2"
    assert comparativa.loc[4, "C5 ASR (%)"] == 0.0
    assert comparativa.loc[4, "C5 bloqueados (429)"] == 3


def test_tabla_comparativa_falla_si_falta_una_configuracion(corrida: Path) -> None:
    por_nivel = calcular_tabla_por_nivel(cargar_corridas_v5(corrida))

    with pytest.raises(ValueError, match="Falta C0 o C5"):
        calcular_tabla_comparativa(por_nivel)  # la corrida colab solo tiene C0


def test_punto_de_degradacion_por_configuracion(corrida: Path) -> None:
    por_nivel = calcular_tabla_por_nivel(cargar_corridas_v5(corrida))

    tabla = calcular_punto_degradacion(por_nivel).set_index(
        ["Hardware", "Configuración"]
    )

    c0 = tabla.loc[(HARDWARE_LOCAL, "C0")]
    c5 = tabla.loc[(HARDWARE_LOCAL, "C5")]
    assert c0["Primer nivel con timeout/5xx"] == "4"
    assert c0["Primer nivel con rate limit activo"] == ""  # nunca, no "0"
    assert c0["Primer nivel con p95 ≥ 2× nivel base"] == "4"  # 90000 vs 1200
    assert c5["Primer nivel con timeout/5xx"] == ""
    assert c5["Primer nivel con rate limit activo"] == "4"
    assert c0["Timeouts totales"] == 1

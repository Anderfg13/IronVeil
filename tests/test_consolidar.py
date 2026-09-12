"""Pruebas unitarias de analisis/consolidar.py (calculo de ASR)."""

from __future__ import annotations

import pandas as pd
import pytest

from analisis.consolidar import calcular_asr, extraer_vector_base


def _df(filas: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(filas)


def test_calcular_asr_dos_de_cuatro_da_50_por_ciento() -> None:
    df = _df(
        [
            {
                "configuracion": "C1",
                "vector_probado": "V3-A",
                "resultado": "exitoso_para_atacante",
            },
            {
                "configuracion": "C1",
                "vector_probado": "V3-B",
                "resultado": "exitoso_para_atacante",
            },
            {"configuracion": "C1", "vector_probado": "V3-C", "resultado": "bloqueado"},
            {
                "configuracion": "C1",
                "vector_probado": "V3-D",
                "resultado": "permitido_normal",
            },
        ]
    )

    tabla = calcular_asr(df)

    assert len(tabla) == 1
    fila = tabla.iloc[0]
    assert fila["Configuración"] == "C1"
    assert fila["Vector"] == "V3"
    assert fila["ASR (%)"] == 50.0
    assert fila["Número de intentos"] == 4


def test_calcular_asr_distingue_por_configuracion_y_vector() -> None:
    df = _df(
        [
            {
                "configuracion": "C0",
                "vector_probado": "V2-A",
                "resultado": "exitoso_para_atacante",
            },
            {
                "configuracion": "C0",
                "vector_probado": "V2-B",
                "resultado": "exitoso_para_atacante",
            },
            {"configuracion": "C0", "vector_probado": "V3-A", "resultado": "bloqueado"},
            {"configuracion": "C0", "vector_probado": "V3-B", "resultado": "bloqueado"},
            {"configuracion": "C1", "vector_probado": "V2-A", "resultado": "bloqueado"},
        ]
    )

    tabla = calcular_asr(df)

    filas = {(f["Configuración"], f["Vector"]): f for _, f in tabla.iterrows()}
    assert filas[("C0", "V2")]["ASR (%)"] == 100.0
    assert filas[("C0", "V3")]["ASR (%)"] == 0.0
    assert filas[("C1", "V2")]["ASR (%)"] == 0.0
    # No debe colapsar todo en un solo promedio general que oculte diferencias.
    assert len(tabla) == 3


def test_calcular_asr_con_cero_intentos_no_divide_por_cero() -> None:
    df = _df(
        [
            {
                "configuracion": "C0",
                "vector_probado": "V1-A",
                "resultado": "permitido_normal",
            },
        ]
    )

    tabla = calcular_asr(df)

    assert tabla.iloc[0]["ASR (%)"] == 0.0
    assert tabla.iloc[0]["Número de intentos"] == 1


def test_calcular_asr_rechaza_resultado_fuera_de_esquema() -> None:
    df = _df(
        [
            {
                "configuracion": "C0",
                "vector_probado": "V1-A",
                "resultado": "algo_invalido",
            },
        ]
    )

    with pytest.raises(ValueError, match="fuera del esquema"):
        calcular_asr(df)


@pytest.mark.parametrize(
    ("vector_probado", "esperado"),
    [
        ("V1-A", "V1"),
        ("V3-C", "V3"),
        ("V4-A-paso1", "V4"),
        ("V4-A-paso2", "V4"),
        ("V10-Z", "V10"),
    ],
)
def test_extraer_vector_base(vector_probado: str, esperado: str) -> None:
    assert extraer_vector_base(vector_probado) == esperado


def test_extraer_vector_base_falla_ruidosamente_con_formato_inesperado() -> None:
    with pytest.raises(ValueError, match="formato inesperado"):
        extraer_vector_base("no-es-un-vector")

"""Pruebas unitarias de analisis/tabla_maestra.py."""

from __future__ import annotations

import pandas as pd
import pytest

from analisis.tabla_maestra import (
    _escapar_latex,
    asr_promedio_por_config,
    calcular_tabla_maestra,
    generar_latex,
    latencia_extra_por_config,
    mecanismos_activos_por_config,
)


def _df(filas: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(filas)


# --- mecanismos_activos_por_config() -------------------------------------


def test_mecanismos_activos_por_config_c0_sin_mecanismos() -> None:
    df = _df(
        [
            {
                "configuracion": "C0",
                "mecanismos_activos": "",
                "vector_probado": "V1-A",
                "resultado": "permitido_normal",
                "latencia_ms": "10",
            }
        ]
    )

    resultado = mecanismos_activos_por_config(df)

    assert resultado["C0"] == set()


def test_mecanismos_activos_por_config_c6_los_cinco() -> None:
    df = _df(
        [
            {
                "configuracion": "C6",
                "mecanismos_activos": (
                    "filtrado,delimitacion,clasificacion,"
                    "minimo_privilegio,aprobacion_humana"
                ),
                "vector_probado": "V1-A",
                "resultado": "bloqueado",
                "latencia_ms": "10",
            }
        ]
    )

    resultado = mecanismos_activos_por_config(df)

    assert resultado["C6"] == {
        "filtrado",
        "delimitacion",
        "clasificacion",
        "minimo_privilegio",
        "aprobacion_humana",
    }


def test_mecanismos_activos_por_config_falla_si_hay_inconsistencia() -> None:
    """Invariante 3 del esquema de log: una misma configuracion no puede
    traer dos conjuntos distintos de mecanismos_activos en el CSV.
    """
    df = _df(
        [
            {
                "configuracion": "C1",
                "mecanismos_activos": "filtrado",
                "vector_probado": "V1-A",
                "resultado": "bloqueado",
                "latencia_ms": "10",
            },
            {
                "configuracion": "C1",
                "mecanismos_activos": "filtrado,delimitacion",
                "vector_probado": "V1-B",
                "resultado": "bloqueado",
                "latencia_ms": "10",
            },
        ]
    )

    with pytest.raises(ValueError, match="mas de un conjunto"):
        mecanismos_activos_por_config(df)


# --- asr_promedio_por_config() -------------------------------------------


def test_asr_promedio_por_config_promedia_sin_ponderar_entre_vectores() -> None:
    """2 vectores con ASR 0% y 100% deben promediar 50%, sin importar que
    uno tenga muchos mas intentos que el otro (no ponderado por conteo).
    """
    tabla_asr = pd.DataFrame(
        [
            {"Configuración": "C0", "Vector": "V1", "ASR (%)": 0.0},
            {"Configuración": "C0", "Vector": "V5", "ASR (%)": 100.0},
        ]
    )

    resultado = asr_promedio_por_config(tabla_asr)

    assert resultado["C0"] == 50.0


# --- latencia_extra_por_config() -----------------------------------------


def test_latencia_extra_por_config_excluye_v5() -> None:
    df = _df(
        [
            {
                "configuracion": "C0",
                "mecanismos_activos": "",
                "vector_probado": "V1-A",
                "resultado": "permitido_normal",
                "latencia_ms": "100",
            },
            {
                "configuracion": "C0",
                "mecanismos_activos": "",
                "vector_probado": "V5-D",
                "resultado": "permitido_normal",
                "latencia_ms": "999999",
            },
        ]
    )

    resultado = latencia_extra_por_config(df)

    assert resultado["C0"] == 100.0


def test_latencia_extra_por_config_excluye_filas_vacias() -> None:
    df = _df(
        [
            {
                "configuracion": "C0",
                "mecanismos_activos": "",
                "vector_probado": "V1-A",
                "resultado": "permitido_normal",
                "latencia_ms": "",
            },
            {
                "configuracion": "C0",
                "mecanismos_activos": "",
                "vector_probado": "V1-B",
                "resultado": "permitido_normal",
                "latencia_ms": "50",
            },
        ]
    )

    resultado = latencia_extra_por_config(df)

    assert resultado["C0"] == 50.0


def test_latencia_extra_por_config_usa_mediana_no_media() -> None:
    """La distribucion real esta sesgada por cargas en frio -- la mediana
    debe ser robusta a un outlier grande, a diferencia de la media.
    """
    df = _df(
        [
            {
                "configuracion": "C0",
                "mecanismos_activos": "",
                "vector_probado": "V1-A",
                "resultado": "permitido_normal",
                "latencia_ms": str(v),
            }
            for v in [10, 20, 30, 100000]
        ]
    )

    resultado = latencia_extra_por_config(df)

    assert (
        resultado["C0"] == 25.0
    )  # mediana de [10,20,30,100000], no ~25007 de la media


# --- calcular_tabla_maestra() (integracion de las 3 funciones de arriba) -


def test_calcular_tabla_maestra_columnas_y_orden() -> None:
    df = _df(
        [
            {
                "configuracion": "C0",
                "mecanismos_activos": "",
                "vector_probado": "V1-A",
                "resultado": "exitoso_para_atacante",
                "latencia_ms": "100",
            },
            {
                "configuracion": "C6",
                "mecanismos_activos": (
                    "filtrado,delimitacion,clasificacion,"
                    "minimo_privilegio,aprobacion_humana"
                ),
                "vector_probado": "V1-A",
                "resultado": "bloqueado",
                "latencia_ms": "50",
            },
        ]
    )

    tabla = calcular_tabla_maestra(df)

    assert list(tabla["Configuración"]) == ["C0", "C6"]
    assert "ASR promedio (%)" in tabla.columns
    assert "Falsos positivos" in tabla.columns
    assert "Latencia mediana (ms)" in tabla.columns
    assert "Costo (líneas/horas)" in tabla.columns
    fila_c6 = tabla[tabla["Configuración"] == "C6"].iloc[0]
    assert fila_c6["Filt."] == "✓"
    assert fila_c6["Del."] == "✓"
    assert (
        "baseline"
        in tabla[tabla["Configuración"] == "C0"].iloc[0]["Latencia mediana (ms)"]
    )
    assert "vs. C0" in fila_c6["Latencia mediana (ms)"]


# --- generar_latex() / _escapar_latex() ----------------------------------


def test_escapar_latex_traduce_checkmark_y_guion() -> None:
    assert _escapar_latex("✓") == r"\checkmark"
    assert _escapar_latex("—") == "--"
    assert _escapar_latex("50%") == r"50\%"
    assert _escapar_latex("a_b") == r"a\_b"


def test_generar_latex_produce_tabular_valido() -> None:
    tabla = pd.DataFrame(
        [{"Configuración": "C0", "Filt.": "—", "ASR promedio (%)": 64.4}]
    )

    tex = generar_latex(tabla)

    assert r"\begin{tabular}" in tex
    assert r"\end{tabular}" in tex
    assert r"\toprule" in tex
    assert "C0 & -- & 64.4" in tex

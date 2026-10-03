"""Pruebas unitarias de analisis/matriz_real_vs_hipotesis.py."""

from __future__ import annotations

import pandas as pd
import pytest

from analisis.matriz_real_vs_hipotesis import (
    HIPOTESIS_SECCION_6_5,
    SIN_DATOS,
    VECTORES_CON_HIPOTESIS,
    aplicar_guarda_de_significancia,
    calcular_v4_ataque_completo,
    clasificar_efecto,
    construir_matriz_hipotesis,
    construir_matriz_pvalores,
    construir_matriz_real,
    fisher_exacto_dos_colas,
)


def _fila_asr(config: str, vector: str, asr: float, intentos: int = 10) -> dict:
    return {
        "Configuración": config,
        "Vector": vector,
        "ASR (%)": asr,
        "Número de intentos": intentos,
    }


def test_clasificar_efecto_directo_con_reduccion_grande() -> None:
    assert clasificar_efecto(100.0, 0.0) == "Sí (directo)"
    assert clasificar_efecto(80.0, 20.0) == "Sí (directo)"


def test_clasificar_efecto_parcial_con_reduccion_pequena() -> None:
    assert clasificar_efecto(100.0, 87.5) == "Parcial"
    assert clasificar_efecto(80.0, 60.0) == "Parcial"


def test_clasificar_efecto_na_sin_cambio() -> None:
    assert clasificar_efecto(100.0, 100.0) == "N/A"


def test_clasificar_efecto_na_si_asr_aumenta() -> None:
    assert clasificar_efecto(0.0, 40.0) == "N/A"


def test_construir_matriz_real_marca_sin_datos_si_no_se_probo() -> None:
    tabla = pd.DataFrame(
        [
            _fila_asr("C0", "V1", 0.0),
            _fila_asr("C1", "V1", 0.0),
            # C2..C5 nunca probaron V1 en esta tabla de prueba.
        ]
    )

    matriz = construir_matriz_real(tabla)

    fila_v1 = matriz[matriz["Vector"] == "V1"].iloc[0]
    assert fila_v1["Delimitación"] == SIN_DATOS
    assert fila_v1["Clasificación"] == SIN_DATOS


def test_construir_matriz_real_etiqueta_y_muestra_porcentajes() -> None:
    tabla = pd.DataFrame(
        [
            _fila_asr("C0", "V3", 100.0),
            _fila_asr("C1", "V3", 87.5),
            _fila_asr("C3", "V3", 0.0),
        ]
    )

    matriz = construir_matriz_real(tabla)

    fila_v3 = matriz[matriz["Vector"] == "V3"].iloc[0]
    assert fila_v3["Filtrado"] == "Parcial (100.0%→87.5%, 10/10→9/10)"
    assert fila_v3["Clasificación"] == "Sí (directo) (100.0%→0.0%, 10/10→0/10)"
    assert fila_v3["Delimitación"] == SIN_DATOS


def test_construir_matriz_real_ordena_vectores_numericamente() -> None:
    tabla = pd.DataFrame(
        [
            _fila_asr("C0", "V5", 50.0),
            _fila_asr("C0", "V1", 0.0),
            _fila_asr("C0", "V2", 10.0),
        ]
    )

    matriz = construir_matriz_real(tabla)

    assert list(matriz["Vector"]) == ["V1", "V2", "V5"]


def test_hipotesis_tiene_los_5_vectores_y_5_mecanismos() -> None:
    assert set(HIPOTESIS_SECCION_6_5) == set(VECTORES_CON_HIPOTESIS)
    columnas_esperadas = {
        "Filtrado",
        "Delimitación",
        "Clasificación",
        "Mín. Privilegio",
        "Aprob. Humana",
    }
    for vector, fila in HIPOTESIS_SECCION_6_5.items():
        assert set(fila) == columnas_esperadas, vector


def test_construir_matriz_hipotesis_v3_coincide_con_la_cita_textual_ya_existente() -> (
    None
):
    # Esta fila ya estaba citada textualmente en analisis/analisis_parcial_C0-C2.md
    # antes de esta tarea -- confirma que no se introdujo una regresion al
    # transcribir la matriz completa.
    matriz = construir_matriz_hipotesis()

    fila_v3 = matriz[matriz["Vector"] == "V3"].iloc[0]
    assert fila_v3["Filtrado"] == "Sí"
    assert fila_v3["Delimitación"] == "Sí"
    assert fila_v3["Clasificación"] == "Sí"
    assert fila_v3["Mín. Privilegio"] == "N/A"
    assert fila_v3["Aprob. Humana"] == "Parcial"


def test_construir_matriz_hipotesis_v4_mecanismo_disenado_es_minimo_privilegio() -> (
    None
):
    # Ya citado por separado en analisis/analisis_C0_C4_vector4.md antes de
    # esta tarea: "el efecto directo que la Seccion 6.5/6.6 ... anticipa
    # para minimo_privilegio x V4".
    matriz = construir_matriz_hipotesis()

    fila_v4 = matriz[matriz["Vector"] == "V4"].iloc[0]
    assert fila_v4["Mín. Privilegio"] == "Sí (directo)"
    assert fila_v4["Filtrado"] == "N/A"


def test_fisher_exacto_sin_diferencia_da_p_1() -> None:
    assert fisher_exacto_dos_colas(8, 20, 8, 20) == pytest.approx(1.0)


def test_fisher_exacto_diferencia_grande_da_p_chico() -> None:
    # 8/24 vs 0/24: la diferencia mas clara de la re-corrida GPU de V4.
    assert fisher_exacto_dos_colas(8, 24, 0, 24) == pytest.approx(0.0040, abs=5e-4)


def test_pvalores_marca_sin_datos_si_no_se_probo() -> None:
    tabla = pd.DataFrame(
        [_fila_asr("C0", "V1", 40.0, 20), _fila_asr("C1", "V1", 40.0, 20)]
    )

    matriz = construir_matriz_pvalores(tabla)

    fila = matriz[matriz["Vector"] == "V1"].iloc[0]
    assert fila["Filtrado"] == "1.000"
    assert fila["Delimitación"] == SIN_DATOS


def test_v4_ataque_completo_separa_los_dos_pasos() -> None:
    def fila(config: str, vector: str, resultado: str) -> dict[str, str]:
        return {
            "configuracion": config,
            "vector_probado": vector,
            "resultado": resultado,
        }

    df = pd.DataFrame(
        [
            fila("C4", "V4-A-paso1", "exitoso_para_atacante"),
            fila("C4", "V4-A-paso2", "bloqueado"),
            fila("C0", "V4-A-paso1", "exitoso_para_atacante"),
            fila("C0", "V4-A-paso2", "exitoso_para_atacante"),
        ]
    )

    tabla = calcular_v4_ataque_completo(df).set_index("Configuración")

    assert tabla.loc["C4", "Paso 1 exitoso (extracción)"] == 1
    assert tabla.loc["C4", "Paso 2 bloqueado"] == 1
    assert tabla.loc["C4", "Ataque completo"] == 0
    assert tabla.loc["C0", "Ataque completo"] == 1


def test_guarda_de_significancia_degrada_efectos_no_significativos() -> None:
    real = pd.DataFrame(
        [
            {
                "Vector": "V3",
                "Filtrado": "Parcial (6.2%→4.2%, 3/48→2/48)",
                "Delimitación": "Sí (directo) (80.0%→0.0%, 8/10→0/10)",
                "Clasificación": SIN_DATOS,
            },
        ]
    )
    pvalores = pd.DataFrame(
        [
            {
                "Vector": "V3",
                "Filtrado": "1.000",
                "Delimitación": "0.002",
                "Clasificación": SIN_DATOS,
            }
        ]
    )

    resultado = aplicar_guarda_de_significancia(real, pvalores)

    assert resultado.at[0, "Filtrado"] == "N/A (n.s.)"
    assert resultado.at[0, "Delimitación"].startswith("Sí (directo)")
    assert resultado.at[0, "Clasificación"] == SIN_DATOS

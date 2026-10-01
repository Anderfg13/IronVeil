"""Pruebas unitarias de analisis/fusionar_latencia_clasificador.py."""

from __future__ import annotations

import pandas as pd

from analisis.fusionar_latencia_clasificador import (
    fusionar_latencia_clasificador,
)

COLUMNAS = (
    "timestamp",
    "configuracion",
    "vector_probado",
    "modelo_destino",
    "resultado",
    "mecanismo_que_bloqueo",
    "latencia_ms",
    "latencia_clasificador_ms",
)


def _fila_csv(**overrides: str) -> dict[str, str]:
    base = {
        "timestamp": "2026-09-07T19:51:16.569172-05:00",
        "configuracion": "C3",
        "vector_probado": "V2-B",
        "modelo_destino": "soporte",
        "resultado": "bloqueado",
        "mecanismo_que_bloqueo": "clasificacion",
        "latencia_ms": "1000",
        "latencia_clasificador_ms": "",
    }
    base.update(overrides)
    return base


def _df(filas: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(filas, columns=COLUMNAS)


def _evento(**overrides: object) -> dict[str, object]:
    base = {
        "timestamp": "2026-09-07T19:51:16.569172-05:00",
        "configuracion": "C3",
        "vector_probado": "V2-B",
        "modelo_destino": "soporte",
        "mecanismo_que_bloqueo": "clasificacion",
        "latencia_clasificador_ms": 996,
    }
    base.update(overrides)
    return base


def _eventos_df(filas: list[dict[str, object]]) -> pd.DataFrame:
    columnas = (
        "timestamp",
        "configuracion",
        "vector_probado",
        "modelo_destino",
        "mecanismo_que_bloqueo",
        "latencia_clasificador_ms",
    )
    df = pd.DataFrame(filas, columns=columnas)
    if df.empty:
        df["fecha"] = pd.Series(dtype=str)
        return df
    df["fecha"] = df["timestamp"].apply(
        lambda t: pd.Timestamp(t).tz_convert("UTC").date().isoformat()
    )
    return df


def test_fusiona_cuando_conteo_y_mecanismo_coinciden() -> None:
    df = _df([_fila_csv()])
    eventos = _eventos_df([_evento()])

    fusionado, resumen = fusionar_latencia_clasificador(df, eventos)

    assert fusionado.at[0, "latencia_clasificador_ms"] == "996"
    assert resumen.filas_fusionadas == 1
    assert resumen.filas_conteo_no_coincide == 0
    assert resumen.filas_mecanismo_no_coincide == 0


def test_no_fusiona_si_no_hay_evento_para_esa_clave() -> None:
    df = _df([_fila_csv()])
    eventos = _eventos_df([])

    fusionado, resumen = fusionar_latencia_clasificador(df, eventos)

    assert fusionado.at[0, "latencia_clasificador_ms"] == ""
    assert resumen.filas_sin_evento_proxy == 1
    assert resumen.filas_fusionadas == 0


def test_no_fusiona_si_el_conteo_de_grupo_no_coincide() -> None:
    df = _df([_fila_csv(), _fila_csv(timestamp="2026-09-07T19:52:16-05:00")])
    eventos = _eventos_df([_evento()])  # solo 1 evento, 2 filas CSV

    fusionado, resumen = fusionar_latencia_clasificador(df, eventos)

    assert (fusionado["latencia_clasificador_ms"] == "").all()
    assert resumen.filas_conteo_no_coincide == 2
    assert resumen.filas_fusionadas == 0


def test_no_fusiona_si_mecanismo_que_bloqueo_no_coincide() -> None:
    df = _df([_fila_csv(mecanismo_que_bloqueo="", resultado="permitido_normal")])
    eventos = _eventos_df([_evento(mecanismo_que_bloqueo="clasificacion")])

    fusionado, resumen = fusionar_latencia_clasificador(df, eventos)

    assert fusionado.at[0, "latencia_clasificador_ms"] == ""
    assert resumen.filas_mecanismo_no_coincide == 1
    assert resumen.indices_mecanismo_no_coincide == [0]
    assert resumen.filas_fusionadas == 0


def test_no_toca_filas_v5_d() -> None:
    df = _df(
        [
            _fila_csv(
                vector_probado="V5-D",
                mecanismo_que_bloqueo="",
                resultado="permitido_normal",
            )
        ]
    )
    eventos = _eventos_df([])

    fusionado, resumen = fusionar_latencia_clasificador(df, eventos)

    assert fusionado.at[0, "latencia_clasificador_ms"] == ""
    assert resumen.filas_sin_evento_proxy == 0
    assert resumen.filas_fusionadas == 0


def test_no_toca_filas_que_ya_tienen_latencia() -> None:
    df = _df([_fila_csv(latencia_clasificador_ms="500")])
    eventos = _eventos_df([_evento(latencia_clasificador_ms=996)])

    fusionado, resumen = fusionar_latencia_clasificador(df, eventos)

    assert fusionado.at[0, "latencia_clasificador_ms"] == "500"
    assert resumen.filas_fusionadas == 0


def test_empareja_por_posicion_ordenando_por_timestamp() -> None:
    df = _df(
        [
            _fila_csv(
                timestamp="2026-09-07T19:52:00-05:00",
                vector_probado="V3-C",
                mecanismo_que_bloqueo="",
                resultado="permitido_normal",
            ),
            _fila_csv(
                timestamp="2026-09-07T19:51:00-05:00",
                vector_probado="V3-C",
                mecanismo_que_bloqueo="clasificacion",
            ),
        ]
    )
    eventos = _eventos_df(
        [
            _evento(
                timestamp="2026-09-07T19:51:00.100000-05:00",
                vector_probado="V3-C",
                mecanismo_que_bloqueo="clasificacion",
                latencia_clasificador_ms=111,
            ),
            _evento(
                timestamp="2026-09-07T19:52:00.100000-05:00",
                vector_probado="V3-C",
                mecanismo_que_bloqueo="",
                latencia_clasificador_ms=222,
            ),
        ]
    )

    fusionado, resumen = fusionar_latencia_clasificador(df, eventos)

    assert resumen.filas_fusionadas == 2
    fila_temprana = fusionado[fusionado["timestamp"].str.startswith("2026-09-07T19:51")]
    fila_tardia = fusionado[fusionado["timestamp"].str.startswith("2026-09-07T19:52")]
    assert fila_temprana.iloc[0]["latencia_clasificador_ms"] == "111"
    assert fila_tardia.iloc[0]["latencia_clasificador_ms"] == "222"

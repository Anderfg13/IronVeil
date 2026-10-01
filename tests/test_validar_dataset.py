"""Pruebas unitarias de analisis/validar_dataset.py."""

from __future__ import annotations

import pandas as pd

from analisis.validar_dataset import (
    generar_reporte,
    validar,
    verificar_campos_base_vacios,
    verificar_filas_duplicadas,
    verificar_invariante_configuracion_mecanismos,
    verificar_invariante_mecanismo_activo,
    verificar_invariante_resultado_mecanismo,
    verificar_modelo_destino_dominio,
    verificar_nombres_configuracion,
    verificar_nombres_mecanismo,
    verificar_resultado_dominio,
    verificar_timestamps,
)

COLUMNAS = (
    "timestamp",
    "configuracion",
    "mecanismos_activos",
    "vector_probado",
    "modelo_destino",
    "resultado",
    "mecanismo_que_bloqueo",
    "latencia_ms",
    "latencia_clasificador_ms",
    "tiempo_revision_humana_ms",
    "tipo_variante",
    "paso_bloqueado",
    "nivel_carga",
    "es_extension",
)


def _fila(**overrides: str) -> dict[str, str]:
    base = {
        "timestamp": "2026-09-05T14:32:11-05:00",
        "configuracion": "C1",
        "mecanismos_activos": "filtrado",
        "vector_probado": "V3-A",
        "modelo_destino": "soporte",
        "resultado": "bloqueado",
        "mecanismo_que_bloqueo": "filtrado",
        "latencia_ms": "812",
        "latencia_clasificador_ms": "",
        "tiempo_revision_humana_ms": "",
        "tipo_variante": "",
        "paso_bloqueado": "",
        "nivel_carga": "",
        "es_extension": "",
    }
    base.update(overrides)
    return base


def _df(filas: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(filas, columns=COLUMNAS)


def test_dataset_limpio_no_produce_hallazgos() -> None:
    df = _df(
        [
            _fila(),
            _fila(
                configuracion="C0",
                mecanismos_activos="",
                resultado="permitido_normal",
                mecanismo_que_bloqueo="",
            ),
        ]
    )

    assert validar(df) == []
    assert "limpio" in generar_reporte(validar(df), len(df))


def test_campo_base_vacio_se_reporta() -> None:
    df = _df([_fila(modelo_destino="")])

    hallazgos = verificar_campos_base_vacios(df)

    assert any(h.categoria == "campo_base_vacio" for h in hallazgos)


def test_mecanismos_activos_vacio_fuera_de_c0_es_error() -> None:
    df = _df([_fila(configuracion="C1", mecanismos_activos="")])

    hallazgos = verificar_campos_base_vacios(df)

    assert any("mecanismos_activos" in h.descripcion for h in hallazgos)


def test_nombre_configuracion_con_minuscula_o_espacios_se_reporta() -> None:
    df = _df(
        [
            _fila(configuracion="c1"),
            _fila(configuracion="C1 "),
            _fila(configuracion="C 1"),
        ]
    )

    hallazgos = verificar_nombres_configuracion(df)

    assert len(hallazgos) == 1
    assert hallazgos[0].filas_afectadas == 3


def test_nombre_mecanismo_no_canonico_en_activos_se_reporta() -> None:
    df = _df([_fila(mecanismos_activos="filtrado,clasificcion")])

    hallazgos = verificar_nombres_mecanismo(df)

    assert any("clasificcion" in h.descripcion for h in hallazgos)


def test_mecanismo_que_bloqueo_no_canonico_se_reporta() -> None:
    df = _df([_fila(mecanismo_que_bloqueo="desconocido (ver eventos.jsonl)")])

    hallazgos = verificar_nombres_mecanismo(df)

    assert any("mecanismo_que_bloqueo" in h.descripcion for h in hallazgos)


def test_timestamp_no_parseable_se_reporta() -> None:
    df = _df([_fila(timestamp="no-es-una-fecha")])

    hallazgos = verificar_timestamps(df)

    assert any(h.categoria == "timestamp_invalido" for h in hallazgos)


def test_timestamp_sin_offset_se_reporta() -> None:
    df = _df([_fila(timestamp="2026-09-05T14:32:11")])

    hallazgos = verificar_timestamps(df)

    assert any(h.categoria == "timestamp_invalido" for h in hallazgos)


def test_timestamp_fuera_de_orden_es_advertencia() -> None:
    df = _df(
        [
            _fila(timestamp="2026-09-05T14:32:11-05:00"),
            _fila(timestamp="2026-09-04T14:32:11-05:00"),
        ]
    )

    hallazgos = verificar_timestamps(df)

    desordenado = [h for h in hallazgos if h.categoria == "timestamp_desordenado"]
    assert len(desordenado) == 1
    assert desordenado[0].severidad == "advertencia"


def test_resultado_fuera_de_dominio_se_reporta() -> None:
    df = _df([_fila(resultado="bloqueado_parcial")])

    hallazgos = verificar_resultado_dominio(df)

    assert len(hallazgos) == 1


def test_invariante_bloqueado_sin_mecanismo_se_reporta() -> None:
    df = _df([_fila(resultado="bloqueado", mecanismo_que_bloqueo="")])

    hallazgos = verificar_invariante_resultado_mecanismo(df)

    assert any("vacio" in h.descripcion for h in hallazgos)


def test_invariante_no_bloqueado_con_mecanismo_se_reporta() -> None:
    df = _df([_fila(resultado="permitido_normal", mecanismo_que_bloqueo="filtrado")])

    hallazgos = verificar_invariante_resultado_mecanismo(df)

    assert any("no esta vacio" in h.descripcion for h in hallazgos)


def test_mecanismo_que_bloqueo_fuera_de_activos_se_reporta() -> None:
    df = _df(
        [
            _fila(
                mecanismos_activos="delimitacion",
                mecanismo_que_bloqueo="filtrado",
                resultado="bloqueado",
            )
        ]
    )

    hallazgos = verificar_invariante_mecanismo_activo(df)

    assert len(hallazgos) == 1


def test_configuracion_con_set_de_mecanismos_inesperado_se_reporta() -> None:
    df = _df([_fila(configuracion="C1", mecanismos_activos="filtrado,delimitacion")])

    hallazgos = verificar_invariante_configuracion_mecanismos(df)

    assert len(hallazgos) == 1


def test_modelo_destino_invalido_fuera_de_v1_se_reporta() -> None:
    df = _df([_fila(vector_probado="V3-A", modelo_destino="inventado")])

    hallazgos = verificar_modelo_destino_dominio(df)

    assert len(hallazgos) == 1


def test_modelo_destino_proxy_o_noexiste_en_v1_no_se_reporta() -> None:
    df = _df(
        [
            _fila(
                vector_probado="V1-A",
                modelo_destino="proxy",
                resultado="permitido_normal",
                mecanismo_que_bloqueo="",
            ),
            _fila(
                vector_probado="V1-D",
                modelo_destino="noexiste",
                resultado="permitido_normal",
                mecanismo_que_bloqueo="",
            ),
        ]
    )

    assert verificar_modelo_destino_dominio(df) == []


def test_filas_duplicadas_exactas_se_reportan() -> None:
    fila = _fila()
    df = _df([fila, dict(fila), _fila(vector_probado="V3-B")])

    hallazgos = verificar_filas_duplicadas(df)

    assert len(hallazgos) == 1
    assert hallazgos[0].filas_afectadas == 2

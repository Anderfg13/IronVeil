"""Pruebas unitarias de analisis/costo_mecanismos.py."""

from __future__ import annotations

import pytest

from analisis.costo_mecanismos import (
    COSTO_POR_MECANISMO,
    ORDEN_MECANISMOS,
    costo_por_configuracion,
    tabla_costo_por_mecanismo,
)


def test_los_5_mecanismos_canonicos_tienen_costo_definido() -> None:
    """Mismos 5 nombres canonicos que proxy.mecanismos.FLAGS_REQUERIDAS /
    config.yaml -- para que tabla_maestra.py pueda cruzarlos sin traducir
    nada (ver tarea de la semana).
    """
    assert set(ORDEN_MECANISMOS) == {
        "filtrado",
        "delimitacion",
        "clasificacion",
        "minimo_privilegio",
        "aprobacion_humana",
    }
    assert set(COSTO_POR_MECANISMO) == set(ORDEN_MECANISMOS)


def test_cada_mecanismo_tiene_los_campos_requeridos() -> None:
    for nombre, datos in COSTO_POR_MECANISMO.items():
        assert datos["lineas_produccion"] > 0, nombre
        assert datos["lineas_tests"] > 0, nombre
        assert datos["horas"] > 0, nombre
        assert datos["complejidad"] in {"Alta", "Media", "Baja"}, nombre
        assert len(datos["justificacion"]) > 0, nombre


def test_costo_por_configuracion_c0_sin_mecanismos_es_cero() -> None:
    lineas, horas = costo_por_configuracion(set())

    assert lineas == 0
    assert horas == 0


def test_costo_por_configuracion_un_solo_mecanismo() -> None:
    lineas, horas = costo_por_configuracion({"filtrado"})

    datos = COSTO_POR_MECANISMO["filtrado"]
    assert lineas == datos["lineas_produccion"] + datos["lineas_tests"]
    assert horas == datos["horas"]


def test_costo_por_configuracion_c6_suma_los_5() -> None:
    lineas, horas = costo_por_configuracion(set(ORDEN_MECANISMOS))

    lineas_esperadas = sum(
        d["lineas_produccion"] + d["lineas_tests"] for d in COSTO_POR_MECANISMO.values()
    )
    horas_esperadas = sum(d["horas"] for d in COSTO_POR_MECANISMO.values())
    assert lineas == lineas_esperadas
    assert horas == horas_esperadas


def test_costo_por_configuracion_mecanismo_desconocido_lanza_error() -> None:
    with pytest.raises(ValueError, match="desconocido"):
        costo_por_configuracion({"mecanismo_inventado"})


def test_tabla_costo_por_mecanismo_tiene_las_columnas_esperadas() -> None:
    tabla = tabla_costo_por_mecanismo()

    assert list(tabla["Mecanismo"]) == list(ORDEN_MECANISMOS)
    for columna in (
        "Líneas de código (producción)",
        "Líneas de código (tests)",
        "Líneas de código (total)",
        "Horas estimadas",
        "Complejidad relativa",
        "Justificación",
    ):
        assert columna in tabla.columns


def test_tabla_costo_lineas_total_es_produccion_mas_tests() -> None:
    tabla = tabla_costo_por_mecanismo()

    for _, fila in tabla.iterrows():
        assert (
            fila["Líneas de código (total)"]
            == fila["Líneas de código (producción)"] + fila["Líneas de código (tests)"]
        )

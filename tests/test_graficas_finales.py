"""Pruebas unitarias de analisis/graficas_finales.py."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analisis.graficas_finales import (
    DPI_FINAL,
    _etiqueta_corta,
    _valor_heatmap,
    graficar_heatmap_cobertura,
    graficar_latencia_por_config,
)
from analisis.matriz_real_vs_hipotesis import SIN_DATOS


def test_valor_heatmap_si_directo() -> None:
    assert _valor_heatmap("Sí (directo) (80.0%→0.0%)") == 2
    assert _valor_heatmap("Sí") == 2


def test_valor_heatmap_parcial() -> None:
    assert _valor_heatmap("Parcial (100.0%→87.5%)") == 1
    assert _valor_heatmap("Parcial") == 1


def test_valor_heatmap_na() -> None:
    assert _valor_heatmap("N/A (0.0%→0.0%)") == 0
    assert _valor_heatmap("N/A (fricción)") == 0


def test_valor_heatmap_sin_datos_es_categoria_propia_no_nan() -> None:
    valor = _valor_heatmap(SIN_DATOS)
    assert valor == -1
    assert valor == valor  # no es NaN (NaN != NaN sería False)


def test_etiqueta_corta_quita_el_sufijo_numerico() -> None:
    assert _etiqueta_corta("Sí (directo) (80.0%→0.0%)") == "Sí (directo)"
    assert _etiqueta_corta("Parcial (100.0%→87.5%)") == "Parcial"
    assert _etiqueta_corta("N/A (0.0%→40.0%)") == "N/A"


def test_etiqueta_corta_conserva_sufijos_no_numericos() -> None:
    assert _etiqueta_corta("N/A (fricción)") == "N/A (fricción)"
    assert _etiqueta_corta("Sí (directo)") == "Sí (directo)"


def test_etiqueta_corta_sin_datos() -> None:
    assert _etiqueta_corta(SIN_DATOS) == "—"


def test_graficar_latencia_por_config_escribe_archivo(tmp_path: Path) -> None:
    latencias = {"C0": 1432.0, "C1": 977.0, "C2": None}
    ruta = tmp_path / "latencia.png"

    resultado = graficar_latencia_por_config(latencias, ruta, dpi=72)

    assert resultado == ruta
    assert ruta.is_file()
    assert ruta.stat().st_size > 0


def test_graficar_heatmap_cobertura_escribe_archivo(tmp_path: Path) -> None:
    matriz_hipotesis = pd.DataFrame(
        [
            {"Vector": "V1", "Filtrado": "N/A", "Delimitación": "Parcial"},
            {"Vector": "V2", "Filtrado": "Sí", "Delimitación": SIN_DATOS},
        ]
    )
    matriz_real = pd.DataFrame(
        [
            {
                "Vector": "V1",
                "Filtrado": "N/A (0.0%→0.0%)",
                "Delimitación": "Parcial (50.0%→30.0%)",
            },
            {
                "Vector": "V2",
                "Filtrado": "Sí (directo) (80.0%→0.0%)",
                "Delimitación": SIN_DATOS,
            },
        ]
    )
    ruta = tmp_path / "heatmap.png"

    resultado = graficar_heatmap_cobertura(matriz_hipotesis, matriz_real, ruta, dpi=72)

    assert resultado == ruta
    assert ruta.is_file()
    assert ruta.stat().st_size > 0


def test_dpi_final_es_al_menos_300() -> None:
    assert DPI_FINAL >= 300

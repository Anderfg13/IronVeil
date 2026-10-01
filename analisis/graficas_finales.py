"""Set completo de gráficas finales para el informe LaTeX y la
sustentación (semana del 24 de octubre): ASR por configuración, latencia
por configuración, y un mapa de calor de la matriz de cobertura real vs.
hipótesis (Sección 6.5). Todas a `dpi>=300`, guardadas en
`resultados/graficas_finales/`.

Uso:
    python analisis/graficas_finales.py

No recalcula nada que ya exista: reutiliza `calcular_tabla_maestra()` /
`latencia_extra_por_config()` / `graficar_tendencia_asr()` de
`analisis/tabla_maestra.py` y `construir_matriz_real()` /
`construir_matriz_hipotesis()` de `analisis/matriz_real_vs_hipotesis.py`.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.colors import BoundaryNorm, ListedColormap

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analisis.consolidar import (  # noqa: E402
    RUTA_CSV_DEFECTO,
    calcular_asr,
    cargar_resultados,
    validar_ruta_salida_segura,
)
from analisis.matriz_real_vs_hipotesis import (  # noqa: E402
    SIN_DATOS,
    construir_matriz_hipotesis,
    construir_matriz_real,
)
from analisis.tabla_maestra import (  # noqa: E402
    COL_CONFIGURACION,
    ORDEN_CONFIGURACIONES,
    calcular_tabla_maestra,
    graficar_tendencia_asr,
    latencia_extra_por_config,
)

logger = logging.getLogger(__name__)

DPI_FINAL = 300
RUTA_GRAFICAS_FINALES_DEFECTO = _REPO_ROOT / "resultados" / "graficas_finales"

# Escala de color del heatmap: Sin datos -> N/A (sin efecto) -> Parcial ->
# Sí (directo). "Sin datos" se codifica como un valor propio (-1), NO como
# NaN -- con NaN, seaborn enmascara la celda y no dibuja la anotación de
# texto encima, dejándola en blanco sin el "—" (comprobado visualmente:
# ver docs/FUENTE_DE_VERDAD.md). Con un valor categorico propio, la celda
# sí recibe su anotación y un color claramente distinto del gris de "N/A"
# (que es un dato real: se probó y no hubo efecto, no es lo mismo que
# "nunca se probó").
_COLOR_SIN_DATOS = "#ffffff"
_COLOR_NA = "#d9d9d9"
_COLOR_PARCIAL = "#fdbb84"
_COLOR_SI = "#31a354"
_CMAP_COBERTURA = ListedColormap(
    [_COLOR_SIN_DATOS, _COLOR_NA, _COLOR_PARCIAL, _COLOR_SI]
)
_NORM_COBERTURA = BoundaryNorm([-1.5, -0.5, 0.5, 1.5, 2.5], _CMAP_COBERTURA.N)

# Quita un sufijo numerico tipo " (80.0%->60.0%)" al final de una celda de
# la matriz real, para que la etiqueta mostrada en el heatmap sea corta
# (el detalle cuantitativo completo ya vive en
# analisis/matriz_real_vs_hipotesis.md). No toca sufijos no numericos como
# "(directo)" o "(friccion)".
_PATRON_SUFIJO_NUMERICO = re.compile(r"\s*\(\d[\d.]*%.*?\)\s*$")


def _valor_heatmap(celda: str) -> int:
    """Codifica una celda cualitativa a un valor categorico propio para el
    color del heatmap (ver constantes de color arriba para por qué no se
    usa NaN para 'Sin datos').
    """
    if celda == SIN_DATOS:
        return -1
    if celda.startswith("Sí"):
        return 2
    if celda.startswith("Parcial"):
        return 1
    return 0  # N/A (con o sin sufijo, p. ej. "N/A (fricción)")


def _etiqueta_corta(celda: str) -> str:
    """Texto corto para anotar cada celda del heatmap (sin el detalle
    cuantitativo de ASR, que satura la figura a este tamaño).
    """
    if celda == SIN_DATOS:
        return "—"
    return _PATRON_SUFIJO_NUMERICO.sub("", celda).strip()


def graficar_latencia_por_config(
    latencias: dict[str, float | None], ruta_png: Path, dpi: int = DPI_FINAL
) -> Path:
    """Gráfica de barras de la latencia mediana por configuración (ver
    `analisis.tabla_maestra.latencia_extra_por_config` para la
    metodología y su limitación de mezclar hardware entre configuraciones).

    Escala logarítmica en el eje Y: el rango real va de ~500ms (C4) a
    ~12.7s (C3), y una escala lineal aplastaría las barras más chicas.
    """
    configs = [c for c in ORDEN_CONFIGURACIONES if latencias.get(c) is not None]
    valores = [latencias[c] for c in configs]

    fig, ax = plt.subplots(figsize=(8, 5))
    barras = ax.bar(configs, valores, color="#b35806")
    ax.set_yscale("log")
    ax.set_ylim(min(valores) * 0.5, max(valores) * 2.2)
    for barra, valor in zip(barras, valores, strict=True):
        ax.text(
            barra.get_x() + barra.get_width() / 2,
            valor * 1.1,
            f"{valor:.1f} ms",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.set_xlabel(COL_CONFIGURACION)
    ax.set_ylabel("Latencia mediana (ms, escala logarítmica)")
    ax.set_title("Latencia mediana por configuración (excluye V5)")
    ax.text(
        0.5,
        -0.24,
        "Mediana de latencia_ms, excluyendo filas de V5 (ráfaga de carga).\n"
        "Limitación real, no oculta: mezcla hardware distinto entre semanas\n"
        "(laptop CPU en C0-C5, GPU T4 de Colab en la mayoría de C6) -- no\n"
        "aísla limpiamente el costo de los mecanismos (ver tabla_maestra.py).",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=8,
        color="dimgray",
    )
    fig.tight_layout()
    ruta_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta_png, dpi=dpi)
    plt.close(fig)
    return ruta_png


def graficar_heatmap_cobertura(
    matriz_hipotesis: pd.DataFrame,
    matriz_real: pd.DataFrame,
    ruta_png: Path,
    dpi: int = DPI_FINAL,
) -> Path:
    """Mapa de calor lado a lado: hipótesis de la Sección 6.5 vs. ASR real
    medido, mismo Vector × Mecanismo, misma escala de color.
    """
    vectores = matriz_hipotesis["Vector"].tolist()
    columnas = [c for c in matriz_hipotesis.columns if c != "Vector"]

    datos_hip = matriz_hipotesis[columnas].to_numpy()
    datos_real = matriz_real.set_index("Vector").loc[vectores, columnas].to_numpy()

    valores_hip = [[_valor_heatmap(c) for c in fila] for fila in datos_hip]
    valores_real = [[_valor_heatmap(c) for c in fila] for fila in datos_real]
    etiquetas_hip = [[_etiqueta_corta(c) for c in fila] for fila in datos_hip]
    etiquetas_real = [[_etiqueta_corta(c) for c in fila] for fila in datos_real]

    fig, axes = plt.subplots(1, 2, figsize=(15, 5), sharey=True)
    for ax, valores, etiquetas, titulo in (
        (axes[0], valores_hip, etiquetas_hip, "Hipótesis (Sección 6.5)"),
        (axes[1], valores_real, etiquetas_real, "Real (ASR medido, C1-C5 vs. C0)"),
    ):
        sns.heatmap(
            valores,
            ax=ax,
            cmap=_CMAP_COBERTURA,
            norm=_NORM_COBERTURA,
            annot=etiquetas,
            fmt="",
            cbar=False,
            xticklabels=columnas,
            yticklabels=vectores,
            linewidths=1,
            linecolor="#999999",
            annot_kws={"fontsize": 9},
        )
        ax.set_title(titulo)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=30, ha="right")

    leyenda = [
        plt.Rectangle((0, 0), 1, 1, facecolor=color, edgecolor="#999999")
        for color in (_COLOR_SIN_DATOS, _COLOR_NA, _COLOR_PARCIAL, _COLOR_SI)
    ]
    fig.legend(
        leyenda,
        ["Sin datos", "N/A (sin efecto)", "Parcial", "Sí (efecto fuerte/directo)"],
        loc="lower center",
        ncol=4,
        frameon=False,
        bbox_to_anchor=(0.5, -0.05),
    )
    fig.suptitle("Cobertura por vector × mecanismo: hipótesis vs. real")
    fig.tight_layout()
    ruta_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return ruta_png


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=RUTA_CSV_DEFECTO)
    parser.add_argument(
        "--output-dir", type=Path, default=RUTA_GRAFICAS_FINALES_DEFECTO
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    output_dir = validar_ruta_salida_segura(args.output_dir, base=_REPO_ROOT)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = cargar_resultados(args.csv)
    tabla_maestra = calcular_tabla_maestra(df)
    latencias = latencia_extra_por_config(df)
    tabla_asr = calcular_asr(df)
    matriz_real = construir_matriz_real(tabla_asr)
    matriz_hipotesis = construir_matriz_hipotesis()

    ruta_asr = graficar_tendencia_asr(
        tabla_maestra, output_dir / "asr_por_configuracion.png"
    )
    ruta_latencia = graficar_latencia_por_config(
        latencias, output_dir / "latencia_por_configuracion.png"
    )
    ruta_heatmap = graficar_heatmap_cobertura(
        matriz_hipotesis, matriz_real, output_dir / "matriz_cobertura_heatmap.png"
    )

    for ruta in (ruta_asr, ruta_latencia, ruta_heatmap):
        logger.info("Gráfica final escrita en %s (dpi=%d)", ruta, DPI_FINAL)


if __name__ == "__main__":
    main()

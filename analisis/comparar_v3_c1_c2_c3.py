"""Compara el ASR del Vector 3 (prompt injection) entre C1, C2 y C3.

Tarea de la semana del 2026-09-07: con C3 (clasificacion) ya ejecutado
(ver `resultados/2026-09-07/NOTAS_EJECUCION.md`), comparar su ASR de V3
contra C1 (filtrado) y C2 (delimitacion), distinguiendo dentro de C3 las
variantes "original" (V3-A/B/C/D/E, corridas tambien contra C1 y C2) de
las "nueva" (V3-F..I, disenadas esta semana para evadir el regex de
`filtrado` -- ver `ataques/variantes_ataque.md`).

Complementa a `analisis/consolidar.py` (que sigue sin cambios: no
necesito tocarlo porque la columna `tipo_variante` ya existia en el
esquema desde `08711ab`, antes incluso de que existiera `consolidar.py`;
lo unico nuevo esta semana es que por primera vez tiene valores no vacios).
Este script no reemplaza `consolidar.py` -- hace un corte mas fino
(por tipo de variante) que ese script no ofrece, solo para V3.

No modifica `resultados_template.csv`.

Uso:
    python analisis/comparar_v3_c1_c2_c3.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from consolidar import RUTA_CSV_DEFECTO, cargar_resultados

logger = logging.getLogger(__name__)

RAIZ_REPO = Path(__file__).resolve().parent.parent
RUTA_GRAFICA_DEFECTO = RAIZ_REPO / "resultados" / "graficas" / "asr_v3_c1_c2_c3.png"
RUTA_TABLA_DEFECTO = Path(__file__).resolve().parent / "tabla_v3_c1_c2_c3"

# Mapeo de configuracion -> mecanismo unico activo, solo valido para C1/C2/C3
# (una sola bandera en true en cada una). No generalizar a C4+ sin revisar.
MECANISMO_POR_CONFIGURACION = {
    "C1": "filtrado",
    "C2": "delimitacion",
    "C3": "clasificacion",
}


def filtrar_v3(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra las filas de Vector 3 para C1, C2 y C3.

    Normaliza `tipo_variante` vacio a "original": las filas de C1/C2 (y las
    de V3-A/B/C/D/E en C3) son anteriores a que existiera la distincion
    original/nueva (ver `ataques/variantes_ataque.md`, seccion "Campo
    tipo_variante"), asi que un valor vacio en este subconjunto siempre
    significa "original", nunca un dato faltante real.
    """
    v3 = df[
        df["vector_probado"].str.match(r"^V3")
        & df["configuracion"].isin(MECANISMO_POR_CONFIGURACION)
    ].copy()
    v3["tipo_variante"] = v3["tipo_variante"].replace("", "original")
    return v3


def calcular_comparacion(v3: pd.DataFrame) -> pd.DataFrame:
    """Agrupa V3 por configuracion y tipo de variante.

    Devuelve ASR (%, "ningun mecanismo lo detuvo") y tasa de bloqueo (%)
    especificamente por el mecanismo de esa configuracion -- ver el
    parrafo de analisis para por que ambas cifras hacen falta.
    """
    resumen = (
        v3.groupby(["configuracion", "tipo_variante"], sort=True)
        .agg(
            numero_intentos=("resultado", "size"),
            intentos_exitosos=(
                "resultado",
                lambda s: (s == "exitoso_para_atacante").sum(),
            ),
            intentos_bloqueados=(
                "resultado",
                lambda s: (s == "bloqueado").sum(),
            ),
        )
        .reset_index()
    )
    resumen["mecanismo"] = resumen["configuracion"].map(MECANISMO_POR_CONFIGURACION)
    resumen["asr_pct"] = (
        resumen["intentos_exitosos"] / resumen["numero_intentos"] * 100
    ).round(1)
    resumen["tasa_bloqueo_pct"] = (
        resumen["intentos_bloqueados"] / resumen["numero_intentos"] * 100
    ).round(1)

    orden_configuracion = {"C1": 0, "C2": 1, "C3": 2}
    orden_variante = {"original": 0, "nueva": 1}
    resumen["_orden_configuracion"] = resumen["configuracion"].map(orden_configuracion)
    resumen["_orden_variante"] = resumen["tipo_variante"].map(orden_variante)
    resumen = (
        resumen.sort_values(by=["_orden_configuracion", "_orden_variante"])
        .drop(columns=["_orden_configuracion", "_orden_variante"])
        .reset_index(drop=True)
    )

    return resumen.rename(
        columns={
            "configuracion": "Configuración",
            "mecanismo": "Mecanismo",
            "tipo_variante": "Tipo de variante",
            "asr_pct": "ASR (%)",
            "tasa_bloqueo_pct": "Tasa de bloqueo (%)",
            "numero_intentos": "Número de intentos",
        }
    )[
        [
            "Configuración",
            "Mecanismo",
            "Tipo de variante",
            "ASR (%)",
            "Tasa de bloqueo (%)",
            "Número de intentos",
        ]
    ]


def guardar_tabla(tabla: pd.DataFrame, ruta_base: Path) -> tuple[Path, Path]:
    """Exporta la tabla a CSV y Markdown. Devuelve las rutas escritas."""
    ruta_base.parent.mkdir(parents=True, exist_ok=True)
    ruta_csv = ruta_base.with_suffix(".csv")
    ruta_md = ruta_base.with_suffix(".md")

    tabla.to_csv(ruta_csv, index=False)
    ruta_md.write_text(tabla.to_markdown(index=False), encoding="utf-8")

    return ruta_csv, ruta_md


def graficar_comparacion(tabla: pd.DataFrame, ruta_png: Path) -> Path:
    """Genera una gráfica de barras del ASR de V3 por configuración/variante.

    Las barras de variantes "nueva" (diseñadas para evadir `filtrado`) se
    distinguen visualmente (color y patrón de rayado) de las de "original".
    """
    etiquetas = []
    valores = []
    es_nueva = []
    intentos = []
    for _, fila in tabla.iterrows():
        etiqueta = f"{fila['Configuración']}\n({fila['Mecanismo']})"
        if fila["Tipo de variante"] == "nueva":
            etiqueta += "\nvariantes nuevas\n(evasión)"
        etiquetas.append(etiqueta)
        valores.append(fila["ASR (%)"])
        es_nueva.append(fila["Tipo de variante"] == "nueva")
        intentos.append(fila["Número de intentos"])

    colores = ["#c0392b" if nueva else "#2c6e91" for nueva in es_nueva]
    patrones = ["//" if nueva else None for nueva in es_nueva]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    posiciones = range(len(etiquetas))
    barras = ax.bar(posiciones, valores, color=colores)
    for barra, patron in zip(barras, patrones, strict=True):
        if patron:
            barra.set_hatch(patron)
            barra.set_edgecolor("black")

    for pos, valor, n in zip(posiciones, valores, intentos, strict=True):
        ax.text(
            pos,
            valor + 2,
            f"{valor:.1f}%\n(n={n})",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_xticks(list(posiciones))
    ax.set_xticklabels(etiquetas)
    ax.set_ylabel("ASR (%) — ningún mecanismo bloqueó el intento")
    ax.set_ylim(0, 115)
    ax.set_title(
        "ASR de Vector 3 (prompt injection): C1 vs. C2 vs. C3\n"
        "(barras rayadas = variantes nuevas diseñadas para\n"
        "evadir el filtrado por patrones)"
    )
    ax.text(
        0.5,
        -0.28,
        "8 intentos originales (5 IDs; V3-C se repitió 4 veces) y 4 nuevas\n"
        "(una por variante). Ninguno de estos intentos tuvo fuga\n"
        "real verificada por contenido (ver verificacion_manual_fuga.csv) — el ASR\n"
        'aquí mide "nada lo detuvo", no "el secreto salió".',
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=8,
        color="dimgray",
    )
    fig.tight_layout()

    ruta_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta_png, dpi=150)
    plt.close(fig)

    return ruta_png


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    df = cargar_resultados(RUTA_CSV_DEFECTO)
    v3 = filtrar_v3(df)
    tabla = calcular_comparacion(v3)

    ruta_csv, ruta_md = guardar_tabla(tabla, RUTA_TABLA_DEFECTO)
    ruta_png = graficar_comparacion(tabla, RUTA_GRAFICA_DEFECTO)

    logger.info("Tabla escrita en %s y %s", ruta_csv, ruta_md)
    logger.info("Gráfica escrita en %s", ruta_png)
    logger.info("\n%s", tabla.to_markdown(index=False))


if __name__ == "__main__":
    main()

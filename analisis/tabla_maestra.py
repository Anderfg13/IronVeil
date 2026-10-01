"""Tabla maestra de resultados (Sección 7.3 del informe LaTeX): una fila por
configuración (C0..C6) con las métricas principales del proyecto.

Uso:
    python analisis/tabla_maestra.py
    python analisis/tabla_maestra.py --csv resultados/resultados_template.csv \
        --output-dir analisis

No modifica el CSV de entrada. Reutiliza `calcular_asr()` de
`analisis/consolidar.py` en vez de recalcular el ASR por vector desde cero
(misma regla metodológica documentada ahí: el ASR nunca se mezcla entre
vectores al calcularlo -- aquí se promedia DESPUÉS, sobre los porcentajes
ya calculados por vector, no sobre los conteos crudos).

**Columnas y su metodología, una por una:**

- `Filt.`/`Del.`/`Clas.`/`M.P.`/`A.H.`: qué mecanismos están activos en esa
  configuración (✓/—), leído directamente de `mecanismos_activos` del CSV
  (no de `config.yaml`, que cambia con el tiempo -- esto es lo que
  realmente corrió en cada fila).
- `ASR promedio (%)`: media SIN PONDERAR de los porcentajes de ASR por
  vector de esa configuración (cada vector pesa igual, sin importar cuántos
  intentos tuvo -- V5 por sí solo tiene miles de intentos y pesarlo por
  conteo ahogaría a V1-V4). Se documenta explícitamente para que nadie lo
  confunda con un ASR agregado sobre todas las filas.
- `Falsos positivos`: **NO es una tasa estadística** -- este proyecto nunca
  registró una muestra de mensajes legítimos en `resultados_template.csv`
  (cada fila ahí es un intento de ataque). Lo que sí existe es una
  verificación puntual por configuración en la suite de `pytest`
  (`tests/test_main.py`): un caso de petición legítima que se confirma que
  NO cae, por combinación de mecanismos. Se reporta cuál test cubre cada
  configuración, no un porcentaje inventado.
- `Latencia mediana (ms)`: MEDIANA (no media -- ver `latencia_extra_por_config()`
  para por qué) de `latencia_ms` por configuración, EXCLUYENDO las filas de
  V5 (ráfaga de carga -- mezclar su latencia bajo contención con la de una
  petición aislada no es comparable) y excluyendo filas con `latencia_ms`
  vacío. Se muestra en valor absoluto y como delta contra la mediana de C0.
  **Limitación real, no oculta:** las configuraciones se corrieron en
  hardware distinto en semanas distintas (ver docstring de
  `latencia_extra_por_config()`), así que esta columna NO aísla limpiamente
  el costo de los mecanismos — también mezcla el costo del hardware.
- `Costo (líneas/horas)`: pendiente -- no hay todavía una cifra de costo de
  implementación por configuración acordada con el equipo (ver tarea de la
  semana del 10 de octubre).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analisis.consolidar import (  # noqa: E402
    RUTA_CSV_DEFECTO,
    calcular_asr,
    cargar_resultados,
    validar_ruta_salida_segura,
)

logger = logging.getLogger(__name__)

ORDEN_CONFIGURACIONES = ["C0", "C1", "C2", "C3", "C4", "C5", "C6"]

# Nombre canonico de mecanismo -> abreviatura de columna, mismo orden que
# CLAUDE.md seccion 1.
MECANISMOS_COLUMNAS: tuple[tuple[str, str], ...] = (
    ("filtrado", "Filt."),
    ("delimitacion", "Del."),
    ("clasificacion", "Clas."),
    ("minimo_privilegio", "M.P."),
    ("aprobacion_humana", "A.H."),
)

# Verificacion puntual de "peticion legitima no cae", una por configuracion
# -- NO una tasa estadistica (ver docstring del modulo). C2 no tiene test
# propio porque delimitacion nunca bloquea (no puede producir un falso
# positivo por diseno); C4 solo tiene cobertura a nivel de mecanismo
# (tests/test_minimo_privilegio.py), no un test de integracion standalone
# contra /chat.
FALSOS_POSITIVOS_POR_CONFIG: dict[str, str] = {
    "C0": "N/A (baseline, sin mecanismos que puedan bloquear)",
    "C1": "0/1 — test_chat_filtrado_no_bloquea_mensaje_legitimo",
    "C2": "N/A — delimitación nunca bloquea (no participa en la cadena de bloqueo)",
    "C3": "0/1 — test_chat_clasificacion_no_bloquea_entrada_legitima",
    "C4": (
        "0/1 (a nivel de mecanismo) — "
        "test_validar_privilegio_no_bloquea_texto_sin_credenciales"
    ),
    "C5": "0/1 — test_chat_aprobacion_humana_no_bloquea_mensaje_legitimo",
    "C6": "0/1 — test_c6_peticion_legitima_pasa_limpia_por_los_5_mecanismos",
}

COSTO_PENDIENTE = "Pendiente (semana del 10 de octubre)"


def mecanismos_activos_por_config(df: pd.DataFrame) -> dict[str, set[str]]:
    """Lee `mecanismos_activos` tal como quedo registrado en cada fila (no
    `config.yaml`, que cambia con el tiempo). Falla ruidosamente si una
    misma configuracion trae mas de un conjunto de mecanismos distinto
    (violaria la invariante 3 del esquema de log).
    """
    resultado: dict[str, set[str]] = {}
    for config, grupo in df.groupby("configuracion"):
        valores_unicos = grupo["mecanismos_activos"].unique()
        if len(valores_unicos) > 1:
            raise ValueError(
                f"{config} trae mas de un conjunto de mecanismos_activos en el "
                f"CSV: {sorted(valores_unicos)} -- viola la invariante 3 del "
                "esquema de log (ver skill esquema-log)."
            )
        texto = valores_unicos[0] if len(valores_unicos) else ""
        resultado[config] = {m for m in texto.split(",") if m}
    return resultado


def asr_promedio_por_config(tabla_asr: pd.DataFrame) -> dict[str, float]:
    """Media SIN PONDERAR de 'ASR (%)' por configuracion, sobre los
    porcentajes ya calculados por vector (ver docstring del modulo).
    """
    return tabla_asr.groupby("Configuración")["ASR (%)"].mean().round(1).to_dict()


def latencia_extra_por_config(df: pd.DataFrame) -> dict[str, float | None]:
    """MEDIANA de `latencia_ms`, excluyendo filas de V5 (rafaga de carga) y
    filas con `latencia_ms` vacio. `None` si no quedan filas validas.

    Mediana, no media: la distribucion esta fuertemente sesgada por cargas
    en frio de los clasificadores (Prompt Guard/Llama Guard), que disparan
    la media muy por encima de lo que tarda una peticion ya caliente (p.
    ej. C3 real: mediana 12.7s vs. media 29.4s, maximo 170.5s). La mediana
    es mucho mas representativa del caso tipico.

    **Limitacion metodologica real, no resuelta por esta mediana:** las
    filas de distintas configuraciones se corrieron en hardware DISTINTO
    en semanas distintas (laptop CPU del equipo en C0-C5, GPU T4 de Colab
    en la corrida de C6 del 2026-09-30) -- comparar la latencia entre
    configuraciones no aisla el costo de los mecanismos, tambien mezcla el
    costo del hardware. Ver nota en el modulo y en
    `docs/FUENTE_DE_VERDAD.md`. Un costo de latencia por mecanismo aislado
    de verdad requeriria correr las 7 configuraciones en el mismo hardware,
    pendiente.
    """
    df = df.copy()
    df["vector"] = df["vector_probado"].str.extract(r"^(V\d+)")
    sin_v5 = df[(df["vector"] != "V5") & (df["latencia_ms"] != "")]
    sin_v5 = sin_v5.assign(latencia_ms=pd.to_numeric(sin_v5["latencia_ms"]))

    resultado: dict[str, float | None] = {}
    for config, grupo in sin_v5.groupby("configuracion"):
        resultado[config] = (
            round(float(grupo["latencia_ms"].median()), 1) if len(grupo) else None
        )
    return resultado


def calcular_tabla_maestra(df: pd.DataFrame) -> pd.DataFrame:
    """Arma la tabla maestra de 1 fila por configuracion presente en `df`."""
    tabla_asr = calcular_asr(df)
    mecanismos = mecanismos_activos_por_config(df)
    asr_prom = asr_promedio_por_config(tabla_asr)
    latencias = latencia_extra_por_config(df)
    latencia_c0 = latencias.get("C0")

    filas = []
    for config in ORDEN_CONFIGURACIONES:
        if config not in mecanismos:
            continue
        activos = mecanismos[config]
        fila: dict[str, object] = {"Configuración": config}
        for nombre, columna in MECANISMOS_COLUMNAS:
            fila[columna] = "✓" if nombre in activos else "—"
        fila["ASR promedio (%)"] = asr_prom.get(config)

        latencia = latencias.get(config)
        if latencia is None:
            fila["Latencia mediana (ms)"] = None
        elif latencia_c0 is not None and config != "C0":
            delta = round(latencia - latencia_c0, 1)
            signo = "+" if delta >= 0 else ""
            fila["Latencia mediana (ms)"] = f"{latencia} ({signo}{delta} vs. C0)"
        else:
            fila["Latencia mediana (ms)"] = f"{latencia} (baseline)"

        fila["Falsos positivos"] = FALSOS_POSITIVOS_POR_CONFIG.get(config, "Sin dato")
        fila["Costo (líneas/horas)"] = COSTO_PENDIENTE
        filas.append(fila)

    columnas = (
        ["Configuración"]
        + [col for _, col in MECANISMOS_COLUMNAS]
        + [
            "ASR promedio (%)",
            "Falsos positivos",
            "Latencia mediana (ms)",
            "Costo (líneas/horas)",
        ]
    )
    return pd.DataFrame(filas)[columnas]


def generar_latex(tabla: pd.DataFrame) -> str:
    """Genera `\\begin{tabular}...\\end{tabular}` listo para pegar en el
    informe LaTeX (Sección 7.3). Usa `booktabs` (`\\toprule`/`\\midrule`/
    `\\bottomrule`); si el informe no lo carga, agregar
    `\\usepackage{booktabs}` al preámbulo. `✓`/`—` se traducen a `\\checkmark`
    (requiere `amssymb`) y `--` para que compile con pdfLaTeX sin necesitar
    una fuente unicode especial.
    """
    alineacion = "l" + "c" * (len(tabla.columns) - 1)
    lineas = [
        "% Generado por analisis/tabla_maestra.py -- no editar a mano.",
        "% Requiere \\usepackage{booktabs} y \\usepackage{amssymb} en el preambulo.",
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\begin{{tabular}}{{{alineacion}}}",
        "\\toprule",
    ]
    encabezado = " & ".join(_escapar_latex(c) for c in tabla.columns) + r" \\"
    lineas.append(encabezado)
    lineas.append("\\midrule")
    for _, fila in tabla.iterrows():
        celdas = ["" if pd.isna(v) else _escapar_latex(str(v)) for v in fila]
        lineas.append(" & ".join(celdas) + r" \\")
    lineas.append("\\bottomrule")
    lineas.append("\\end{tabular}")
    lineas.append(
        "\\caption{Tabla maestra de resultados: mecanismos activos, ASR "
        "promedio sin ponderar entre vectores, falsos positivos verificados "
        "puntualmente y latencia extra (ms) sobre passthrough puro, por "
        "configuración.}"
    )
    lineas.append("\\label{tab:tabla-maestra}")
    lineas.append("\\end{table}")
    return "\n".join(lineas) + "\n"


def _escapar_latex(texto: str) -> str:
    """Escapa los caracteres especiales de LaTeX que aparecen en esta tabla
    (%, &, _) y traduce ✓/— a comandos que compilan con pdfLaTeX sin fuente
    unicode especial -- suficiente para este dataset, no un escapador general.
    """
    return (
        texto.replace("\\", r"\textbackslash{}")
        .replace("%", r"\%")
        .replace("&", r"\&")
        .replace("_", r"\_")
        .replace("✓", r"\checkmark")
        .replace("—", "--")
    )


def graficar_tendencia_asr(tabla: pd.DataFrame, ruta_png: Path) -> Path:
    """Gráfica de barras del ASR promedio por configuración, C0 a C6."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    configs = tabla["Configuración"].tolist()
    valores = tabla["ASR promedio (%)"].tolist()
    barras = ax.bar(configs, valores, color="#2c6e91")
    for barra, valor in zip(barras, valores, strict=True):
        ax.text(
            barra.get_x() + barra.get_width() / 2,
            valor + 1,
            f"{valor:.1f}%",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.set_xlabel("Configuración")
    ax.set_ylabel("ASR promedio (%) — media sin ponderar entre vectores")
    ax.set_ylim(0, max(valores + [10]) * 1.2)
    ax.set_title("Tendencia de ASR promedio por configuración (C0 → C6)")
    ax.text(
        0.5,
        -0.22,
        "Media SIN PONDERAR de los porcentajes de ASR por vector de cada\n"
        "configuración (cada vector pesa igual; V5, con miles de intentos,\n"
        "no domina el promedio). No todas las configuraciones tienen los\n"
        "mismos vectores probados -- ver tabla maestra para el detalle.",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Genera la tabla maestra de resultados (CSV, Markdown y LaTeX) "
            "y la grafica de tendencia de ASR C0-C6."
        )
    )
    parser.add_argument("--csv", type=Path, default=RUTA_CSV_DEFECTO)
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).resolve().parent
    )
    parser.add_argument(
        "--nombre-base",
        default="tabla_maestra",
        help="Nombre base de los archivos de salida (default: %(default)s).",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    df = cargar_resultados(args.csv)
    tabla = calcular_tabla_maestra(df)

    output_dir = validar_ruta_salida_segura(args.output_dir, base=_REPO_ROOT)
    output_dir.mkdir(parents=True, exist_ok=True)

    ruta_csv = output_dir / f"{args.nombre_base}.csv"
    ruta_md = output_dir / f"{args.nombre_base}.md"
    ruta_tex = output_dir / f"{args.nombre_base}.tex"
    ruta_png = _REPO_ROOT / "resultados" / "graficas" / "asr_tendencia_c0_c6.png"

    tabla.to_csv(ruta_csv, index=False)
    ruta_md.write_text(tabla.to_markdown(index=False), encoding="utf-8")
    ruta_tex.write_text(generar_latex(tabla), encoding="utf-8")
    graficar_tendencia_asr(tabla, ruta_png)

    logger.info("Tabla maestra escrita en %s, %s y %s", ruta_csv, ruta_md, ruta_tex)
    logger.info("Grafica de tendencia escrita en %s", ruta_png)
    logger.info("\n%s", tabla.to_markdown(index=False))


if __name__ == "__main__":
    main()

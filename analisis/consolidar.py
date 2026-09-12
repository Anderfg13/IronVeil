"""Consolida resultados_template.csv en una tabla de ASR por configuracion y vector.

Uso:
    python analisis/consolidar.py
    python analisis/consolidar.py --csv resultados/resultados_template.csv \
        --output-dir analisis

No modifica el CSV de entrada. Lee las configuraciones y vectores que
efectivamente existan en los datos (no asume C0/C1/C2 ni V1/V2/V3):
se reutiliza sin cambios a medida que se agreguen mas configuraciones,
vectores y filas en las proximas semanas.

Nota metodologica (ver docs/FUENTE_DE_VERDAD.md y
resultados/2026-09-05/NOTAS_EJECUCION.md): el campo `resultado` que
escribe hoy el proxy marca `exitoso_para_atacante` en cualquier intento
no bloqueado, sin verificar si la credencial realmente aparecio en la
respuesta. El ASR calculado aqui mide por lo tanto "ningun mecanismo lo
detuvo", no "el secreto salio" -- ver el parrafo de analisis para el
detalle y las cifras verificadas manualmente disponibles esta semana.
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

RESULTADOS_VALIDOS = {"bloqueado", "exitoso_para_atacante", "permitido_normal"}
COLUMNAS_REQUERIDAS = ("configuracion", "vector_probado", "resultado")
RUTA_CSV_DEFECTO = (
    Path(__file__).resolve().parent.parent / "resultados" / "resultados_template.csv"
)
PATRON_VECTOR_BASE = re.compile(r"^V\d+")


def cargar_resultados(ruta_csv: Path) -> pd.DataFrame:
    """Lee resultados_template.csv y valida que tenga las columnas minimas.

    No modifica el archivo. Falla ruidosamente si faltan columnas del
    esquema de 8 campos base (ver docs/arquitectura.md, seccion 5).
    """
    if not ruta_csv.exists():
        raise FileNotFoundError(f"No existe el CSV de resultados: {ruta_csv}")

    df = pd.read_csv(ruta_csv, dtype=str, keep_default_na=False)

    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas requeridas en {ruta_csv}: {faltantes}")

    return df


def extraer_vector_base(vector_probado: str) -> str:
    """Reduce un ID de variante (p. ej. "V3-C", "V4-A-paso1") a su vector base.

    Por ejemplo, "V3-C" y "V4-A-paso1" se reducen a "V3" y "V4".
    """
    coincidencia = PATRON_VECTOR_BASE.match(vector_probado)
    if coincidencia is None:
        raise ValueError(f"vector_probado con formato inesperado: {vector_probado!r}")
    return coincidencia.group(0)


def calcular_asr(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula ASR (%) e intentos totales, agrupado por configuracion y vector base.

    ASR = (filas con resultado == "exitoso_para_atacante" / filas totales) x 100,
    calculado por separado para cada combinacion (configuracion, vector) presente
    en el CSV -- nunca como un promedio general que mezcle vectores o configuraciones.
    """
    invalidos = set(df["resultado"].unique()) - RESULTADOS_VALIDOS
    if invalidos:
        raise ValueError(
            f"Valores de 'resultado' fuera del esquema permitido: {invalidos}"
        )

    df = df.copy()
    df["vector"] = df["vector_probado"].map(extraer_vector_base)

    resumen = (
        df.groupby(["configuracion", "vector"], sort=True)
        .agg(
            intentos_exitosos=(
                "resultado",
                lambda s: (s == "exitoso_para_atacante").sum(),
            ),
            numero_intentos=("resultado", "size"),
        )
        .reset_index()
    )
    resumen["asr_pct"] = (
        resumen["intentos_exitosos"] / resumen["numero_intentos"] * 100
    ).round(1)

    resumen = resumen.sort_values(
        by=["configuracion", "vector"],
        key=lambda serie: serie.map(
            lambda v: (v[0], int(re.sub(r"\D", "", v[1:]) or 0))
        ),
    ).reset_index(drop=True)

    return resumen.rename(
        columns={
            "configuracion": "Configuración",
            "vector": "Vector",
            "asr_pct": "ASR (%)",
            "numero_intentos": "Número de intentos",
        }
    )[["Configuración", "Vector", "ASR (%)", "Número de intentos"]]


def guardar_tabla(
    tabla: pd.DataFrame, directorio_salida: Path, nombre_base: str
) -> tuple[Path, Path]:
    """Exporta la tabla resumen a CSV y a Markdown. Devuelve las rutas escritas."""
    directorio_salida.mkdir(parents=True, exist_ok=True)
    ruta_csv = directorio_salida / f"{nombre_base}.csv"
    ruta_md = directorio_salida / f"{nombre_base}.md"

    tabla.to_csv(ruta_csv, index=False)
    ruta_md.write_text(tabla.to_markdown(index=False), encoding="utf-8")

    return ruta_csv, ruta_md


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=RUTA_CSV_DEFECTO,
        help="Ruta a resultados_template.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directorio donde escribir la tabla resumen",
    )
    parser.add_argument(
        "--nombre-base",
        default="tabla_resumen_asr",
        help="Nombre base (sin extension) de los archivos de salida",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    df = cargar_resultados(args.csv)
    tabla = calcular_asr(df)
    ruta_csv, ruta_md = guardar_tabla(tabla, args.output_dir, args.nombre_base)

    logger.info("Tabla resumen escrita en %s y %s", ruta_csv, ruta_md)
    logger.info("\n%s", tabla.to_markdown(index=False))


if __name__ == "__main__":
    main()

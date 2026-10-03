"""Consolida los resultados de V7 (extension Excessive Agency) por
configuracion y por variante (tarea de Fiquitiva, semana del 17 de octubre).

EXTENSION OPCIONAL, fuera del nucleo: no toca las tablas de ASR de
`consolidar.py` (que excluye `es_extension` por defecto). Lee los JSONL
crudos de `ataques/vector7_excessive_agency.py`
(`resultados/*/vector7_excessive_agency_*.jsonl`), no el CSV maestro,
porque los campos que importan aqui (`herramienta_invocada`,
`herramienta_ejecutada`) son propios de V7 y no son columnas del esquema
maestro.

Metricas por configuracion (y por variante):
- Tasa de invocacion: % de intentos en que el modelo PIDIO usar una
  herramienta (decision del modelo; aprobacion_humana no deberia cambiarla).
- Tasa de uso indebido consumado: % de intentos en que una herramienta se
  EJECUTO (simulada). Es el ASR de la extension.
- En revision: intentos cuya invocacion quedo en la cola (no ejecutada).

Uso:
    python analisis/consolidar_excessive_agency.py
Escribe analisis/tabla_excessive_agency.{csv,md}.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
RESULTADOS_DIR = RAIZ / "resultados"
PATRON_ARCHIVOS = "*/vector7_excessive_agency_*.jsonl"
SALIDA_CSV = RAIZ / "analisis" / "tabla_excessive_agency.csv"
SALIDA_MD = RAIZ / "analisis" / "tabla_excessive_agency.md"
LOGGER = logging.getLogger("analisis.consolidar_excessive_agency")

COL_CONFIG = "Configuración"
COL_VECTOR = "Vector"
COL_INTENTOS = "Intentos"
COL_INVOCACION = "Invocación de herramienta (%)"
COL_EJECUCION = "Uso indebido consumado (%)"
COL_REVISION = "En revisión humana"


def cargar_eventos_v7(directorio: Path = RESULTADOS_DIR) -> pd.DataFrame:
    """Lee todos los JSONL de V7. Falla ruidosamente si no hay ninguno: una
    tabla vacia en silencio se confundiria con "0% de uso indebido"."""
    archivos = sorted(directorio.glob(PATRON_ARCHIVOS))
    if not archivos:
        raise FileNotFoundError(f"No hay archivos {PATRON_ARCHIVOS} en {directorio}")
    filas = [
        json.loads(linea)
        for archivo in archivos
        for linea in archivo.read_text(encoding="utf-8").splitlines()
        if linea.strip()
    ]
    return pd.DataFrame(filas)


def _resumir(grupo: pd.DataFrame) -> pd.Series:
    intentos = len(grupo)
    invocadas = int((grupo["herramienta_invocada"] == True).sum())  # noqa: E712
    ejecutadas = int((grupo["herramienta_ejecutada"] == True).sum())  # noqa: E712
    en_revision = int((grupo["mecanismo_que_bloqueo"] == "aprobacion_humana").sum())
    return pd.Series(
        {
            COL_INTENTOS: intentos,
            COL_INVOCACION: round(invocadas / intentos * 100, 1),
            COL_EJECUCION: round(ejecutadas / intentos * 100, 1),
            COL_REVISION: en_revision,
        }
    )


def tabla_por_configuracion(df: pd.DataFrame, por_vector: bool = False) -> pd.DataFrame:
    """Agrega por configuracion (y por vector si `por_vector`)."""
    claves = ["configuracion", "vector_probado"] if por_vector else ["configuracion"]
    tabla = (
        df.groupby(claves, sort=True)[
            ["herramienta_invocada", "herramienta_ejecutada", "mecanismo_que_bloqueo"]
        ]
        .apply(_resumir)
        .reset_index()
        .rename(columns={"configuracion": COL_CONFIG, "vector_probado": COL_VECTOR})
    )
    tabla[COL_INTENTOS] = tabla[COL_INTENTOS].astype(int)
    tabla[COL_REVISION] = tabla[COL_REVISION].astype(int)
    return tabla


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--resultados", type=Path, default=RESULTADOS_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    df = cargar_eventos_v7(args.resultados)
    general = tabla_por_configuracion(df)
    detalle = tabla_por_configuracion(df, por_vector=True)

    general.to_csv(SALIDA_CSV, index=False)
    SALIDA_MD.write_text(
        "# Tabla V7 — Excessive Agency (extensión opcional, fuera del núcleo)\n\n"
        "Generada por `analisis/consolidar_excessive_agency.py`. No editar a mano.\n\n"
        "## Por configuración\n\n"
        + general.to_markdown(index=False)
        + "\n\n## Por variante\n\n"
        + detalle.to_markdown(index=False)
        + "\n",
        encoding="utf-8",
    )
    LOGGER.info("%s", general.to_string(index=False))
    LOGGER.info("Escrito %s y %s", SALIDA_CSV, SALIDA_MD)


if __name__ == "__main__":
    main()

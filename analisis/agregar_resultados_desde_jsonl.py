"""Agrega filas a resultados_template.csv desde uno o mas JSONL de ataques.

Regla 4 de CLAUDE.md: los datos crudos no se editan a mano. Este script es
la forma reproducible de pasar eventos de un JSONL de ataque (formato
EventoManual/EventoV4/EventoV5, cada uno con un superset variable de los 14
campos del esquema maestro) a filas de resultados_template.csv, sin perder
ni inventar informacion: los campos que no trae un JSONL en particular
quedan vacios, nunca con un default inventado.

Uso:
    python analisis/agregar_resultados_desde_jsonl.py \
        resultados/2026-09-18/vectores_1_2_3_C3_230049.jsonl \
        resultados/2026-09-18/vector4_movimiento_lateral_C3_231512.jsonl \
        resultados/2026-09-18/vector5_carga_231639.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RESULTADOS_CSV = RAIZ / "resultados" / "resultados_template.csv"

# Orden y nombres exactos de las 14 columnas del esquema maestro (ver
# skill esquema-log). Un JSONL de ataque puede traer campos extra (p. ej.
# fuga_confirmada, observaciones): esos NO son parte del esquema maestro y
# se ignoran aqui a proposito -- quedan en el JSONL crudo como evidencia,
# no se pierden, solo no se duplican en el CSV consolidado.
COLUMNAS_MAESTRAS: tuple[str, ...] = (
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


def _fila_desde_evento(evento: dict[str, object]) -> dict[str, str]:
    fila: dict[str, str] = {}
    for columna in COLUMNAS_MAESTRAS:
        valor = evento.get(columna, "")
        if valor is None:
            fila[columna] = ""
        elif isinstance(valor, list):
            fila[columna] = ",".join(str(v) for v in valor)
        else:
            fila[columna] = str(valor)
    return fila


def agregar_desde_jsonl(rutas_jsonl: list[Path]) -> int:
    """Agrega (append) al final de resultados_template.csv. Devuelve cuantas."""
    filas: list[dict[str, str]] = []
    for ruta in rutas_jsonl:
        with ruta.open("r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                filas.append(_fila_desde_evento(json.loads(linea)))

    if not filas:
        return 0

    existe = RESULTADOS_CSV.is_file() and RESULTADOS_CSV.stat().st_size > 0
    with RESULTADOS_CSV.open("a", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(COLUMNAS_MAESTRAS))
        if not existe:
            escritor.writeheader()
        escritor.writerows(filas)

    return len(filas)


def _parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "jsonl", nargs="+", type=Path, help="Uno o mas archivos JSONL de ataque."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parsear_argumentos(argv)
    agregadas = agregar_desde_jsonl(args.jsonl)
    print(
        f"{agregadas} fila(s) agregadas a {RESULTADOS_CSV} "
        f"desde {len(args.jsonl)} archivo(s)."
    )


if __name__ == "__main__":
    main()

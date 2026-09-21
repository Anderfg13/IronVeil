"""Mueve filas de resultados_template.csv a descartados.csv, con razon.

Regla 4 de CLAUDE.md: los datos crudos no se editan a mano y ninguna fila
se borra -- se mueve a descartados.csv con una razon documentada. Este
script es la unica forma soportada de sacar filas de resultados_template.csv.

Uso:
    python analisis/mover_a_descartados.py --configuracion C3 C6 \
        --razon "Clasificador reemplazado (Prompt Guard en entrada, ver \
FUENTE_DE_VERDAD.md seccion 4 y 9, entrada 2026-09-18): estas filas \
describen el clasificador anterior (Llama Guard en las dos direcciones) \
y no son comparables contra el nuevo sin volver a ejecutar el experimento."
"""

from __future__ import annotations

import argparse
import csv
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RESULTADOS_CSV = RAIZ / "resultados" / "resultados_template.csv"
DESCARTADOS_CSV = RAIZ / "resultados" / "descartados.csv"


def mover_a_descartados(configuraciones: list[str], razon: str) -> int:
    """Mueve las filas cuya 'configuracion' este en `configuraciones`.

    Devuelve cuantas filas se movieron. Reescribe resultados_template.csv
    sin esas filas y las agrega (append) a descartados.csv con una columna
    `razon_descarte` y `fecha_descarte` nuevas.
    """
    with RESULTADOS_CSV.open("r", encoding="utf-8", newline="") as f:
        lector = csv.DictReader(f)
        columnas = list(lector.fieldnames or [])
        filas = list(lector)

    a_mover = [f for f in filas if f["configuracion"] in configuraciones]
    a_conservar = [f for f in filas if f["configuracion"] not in configuraciones]

    if not a_mover:
        return 0

    with RESULTADOS_CSV.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas)
        escritor.writeheader()
        escritor.writerows(a_conservar)

    columnas_descartados = [*columnas, "razon_descarte", "fecha_descarte"]
    existe = DESCARTADOS_CSV.is_file()
    ahora = datetime.now(UTC).isoformat()
    with DESCARTADOS_CSV.open("a", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas_descartados)
        if not existe:
            escritor.writeheader()
        for fila in a_mover:
            escritor.writerow(
                {**fila, "razon_descarte": razon, "fecha_descarte": ahora}
            )

    return len(a_mover)


def _parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--configuracion",
        nargs="+",
        required=True,
        help="Una o mas configuraciones (p. ej. C3 C6) cuyas filas se mueven.",
    )
    parser.add_argument(
        "--razon",
        required=True,
        help="Razon documentada del descarte (obligatoria, regla 4 de CLAUDE.md).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parsear_argumentos(argv)
    movidas = mover_a_descartados(args.configuracion, args.razon)
    print(
        f"{movidas} fila(s) movidas de resultados_template.csv a "
        f"descartados.csv (configuraciones: {', '.join(args.configuracion)})."
    )


if __name__ == "__main__":
    main()

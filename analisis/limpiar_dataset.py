"""Aplica, de forma reproducible, las correcciones de datos que NO requieren
una decision humana caso por caso -- es decir, las que
`analisis/validar_dataset.py` reporta pero cuya solucion es deterministica.
Cualquier hallazgo ambiguo (ver docs/LIMPIEZA_DATOS.md) se deja intacto a
proposito, para que un humano decida.

Uso:
    python analisis/limpiar_dataset.py

Dos correcciones, en este orden:

1. `mecanismo_que_bloqueo == "desconocido (ver eventos.jsonl ...)"` con
   'mecanismos_activos' de un solo elemento: se reemplaza por ese unico
   mecanismo. No es una suposicion -- con un solo mecanismo activo, si
   'resultado' es "bloqueado", ese mecanismo es necesariamente el que
   bloqueo (es el unico que pudo haberlo hecho). Si una fila con este
   problema tuviera 0 o 2+ mecanismos activos, esta funcion la DEJA sin
   tocar (haria falta revisar eventos.jsonl a mano, no corresponde
   adivinar) y lo reporta para que se resuelva manualmente.

2. Filas duplicadas exactas (las 14 columnas iguales): se conserva la
   primera aparicion y el resto se mueve a resultados/descartados.csv
   (regla 4 de CLAUDE.md -- ninguna fila se borra sin dejar rastro), con
   razon_descarte="duplicado exacto (probable reingesta del mismo evento
   jsonl)" y fecha_descarte con la fecha de esta limpieza.

Sobrescribe resultados_template.csv en el sitio (mismo patron que
`analisis/mover_a_descartados.py`, que ya hace esto para descartes por
configuracion completa) -- no crea una copia paralela, para que no haya
dos "fuentes de verdad" del dataset divergiendo con el tiempo.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CSV_DEFECTO = RAIZ / "resultados" / "resultados_template.csv"
RUTA_DESCARTADOS_DEFECTO = RAIZ / "resultados" / "descartados.csv"

PREFIJO_MECANISMO_DESCONOCIDO = "desconocido"
RAZON_DUPLICADO_EXACTO = "duplicado exacto (probable reingesta del mismo evento jsonl)"


def corregir_mecanismo_desconocido(df: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Devuelve (df_corregido, filas_corregidas, filas_dejadas_sin_tocar)."""
    df = df.copy()
    es_desconocido = df["mecanismo_que_bloqueo"].str.startswith(
        PREFIJO_MECANISMO_DESCONOCIDO, na=False
    )

    corregidas = 0
    sin_tocar = 0
    for idx in df.index[es_desconocido]:
        activos = [m for m in df.at[idx, "mecanismos_activos"].split(",") if m]
        if len(activos) == 1:
            df.at[idx, "mecanismo_que_bloqueo"] = activos[0]
            corregidas += 1
        else:
            sin_tocar += 1

    return df, corregidas, sin_tocar


def mover_duplicados_exactos(
    df: pd.DataFrame, ruta_descartados: Path
) -> tuple[pd.DataFrame, int]:
    """Conserva la primera aparicion de cada fila duplicada exacta; el
    resto se agrega (append) a `ruta_descartados` con razon y fecha.
    """
    duplicada_no_primera = df.duplicated(keep="first")
    a_descartar = df[duplicada_no_primera]
    if a_descartar.empty:
        return df, 0

    ahora = datetime.now(UTC).isoformat()
    a_descartar = a_descartar.assign(
        razon_descarte=RAZON_DUPLICADO_EXACTO, fecha_descarte=ahora
    )
    existe = ruta_descartados.is_file() and ruta_descartados.stat().st_size > 0
    a_descartar.to_csv(ruta_descartados, mode="a", header=not existe, index=False)

    return df[~duplicada_no_primera], len(a_descartar)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=RUTA_CSV_DEFECTO)
    parser.add_argument("--descartados", type=Path, default=RUTA_DESCARTADOS_DEFECTO)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.csv, dtype=str, keep_default_na=False)

    df, corregidas, sin_tocar = corregir_mecanismo_desconocido(df)
    df, movidas = mover_duplicados_exactos(df, args.descartados)

    df.to_csv(args.csv, index=False)

    print(f"mecanismo_que_bloqueo corregido en {corregidas} fila(s).")
    if sin_tocar:
        print(
            f"{sin_tocar} fila(s) con mecanismo_que_bloqueo 'desconocido' "
            "NO corregidas (mas de un mecanismo activo -- requieren revision "
            "manual de eventos.jsonl)."
        )
    print(f"{movidas} fila(s) duplicada(s) movidas a {args.descartados}.")
    print(f"{args.csv} reescrito con {len(df)} filas.")


if __name__ == "__main__":
    main()

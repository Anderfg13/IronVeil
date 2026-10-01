"""Fusiona 'latencia_clasificador_ms' desde el log propio del proxy
(resultados/<fecha>/eventos.jsonl) hacia resultados_template.csv.

Motivacion (ver docs/LIMPIEZA_DATOS.md, seccion 3.1): resultados_template.csv
se construye desde los JSONL de los scripts de ataque (clientes HTTP que
solo pueden medir el tiempo de ida y vuelta de su propia peticion); el
desglose interno 'latencia_clasificador_ms' solo lo mide y registra el
proxy mismo, en su propio 'eventos.jsonl', que nunca se habia fusionado
con el dataset consolidado.

Este script SOLO toca la columna 'latencia_clasificador_ms'. Nunca
modifica 'resultado', 'mecanismo_que_bloqueo' ni ninguna otra columna --
incluso cuando el cruce expone un desacuerdo con el log del proxy en esos
campos, eso es un hallazgo aparte (ver docs/LIMPIEZA_DATOS.md, seccion
3.3), no algo que este script corrija.

Metodo de cruce (documentado con el mismo detalle en
docs/LIMPIEZA_DATOS.md para que sea auditable):
    1. Se agrupan ambos lados por (fecha UTC del timestamp, configuracion,
       vector_probado, modelo_destino), excluyendo 'V5-D': el proxy nunca
       registro 'latencia_clasificador_ms' durante las rafagas de V5 (0 de
       miles de eventos la traen) -- no es un problema de cruce, es que no
       se capturo del lado del servidor, asi que cruzar no ayuda ahi.
    2. Un grupo SOLO se fusiona si el conteo de filas coincide EXACTO en
       ambos lados Y 'mecanismo_que_bloqueo' coincide en cada posicion
       emparejada (ordenando por timestamp -- seguro porque los scripts de
       ataque disparan una peticion a la vez y esperan la respuesta antes
       de la siguiente, excepto V5, ya excluido). Si el conteo no coincide
       o 'mecanismo_que_bloqueo' no coincide en alguna posicion, el grupo
       completo se deja SIN TOCAR y se reporta aparte -- nunca se adivina.

Uso:
    python analisis/fusionar_latencia_clasificador.py
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from analisis.consolidar import validar_ruta_salida_segura  # noqa: E402

RUTA_CSV_DEFECTO = RAIZ / "resultados" / "resultados_template.csv"
RESULTADOS_DIR_DEFECTO = RAIZ / "resultados"

VECTOR_SIN_LATENCIA_CLASIFICADOR = "V5-D"
CLAVES_PARTICION = ("fecha", "configuracion", "vector_probado", "modelo_destino")


@dataclass
class ResumenFusion:
    filas_fusionadas: int = 0
    filas_conteo_no_coincide: int = 0
    filas_sin_evento_proxy: int = 0
    filas_mecanismo_no_coincide: int = 0
    indices_mecanismo_no_coincide: list[int] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"Fusionadas: {self.filas_fusionadas}. "
            f"Sin evento del proxy para cruzar: {self.filas_sin_evento_proxy}. "
            f"Conteo de grupo no coincide: {self.filas_conteo_no_coincide}. "
            f"mecanismo_que_bloqueo no coincide (sospechoso, no fusionado): "
            f"{self.filas_mecanismo_no_coincide} "
            f"(filas CSV: {self.indices_mecanismo_no_coincide})."
        )


def _fecha_utc(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).astimezone(UTC).date().isoformat()


def cargar_eventos_proxy(resultados_dir: Path = RESULTADOS_DIR_DEFECTO) -> pd.DataFrame:
    """Lee todos los <resultados_dir>/<fecha>/eventos.jsonl del repo. Excluye
    'V5-D' (ver docstring del modulo) y filas sin 'latencia_clasificador_ms'.

    `resultados_dir` se valida con `validar_ruta_salida_segura()` (CWE-22,
    path traversal via un argumento de linea de comandos mal formado) antes
    de construir el patron de busqueda -- a diferencia de
    `agregar_resultados_desde_jsonl.py`, que si necesita aceptar rutas
    arbitrarias fuera del repo (recibe evidencia de donde sea que viva),
    este script solo tiene un uso previsto: la carpeta resultados/ de este
    mismo repositorio.
    """
    resultados_dir = validar_ruta_salida_segura(resultados_dir)
    patron_glob = str(resultados_dir / "*" / "eventos.jsonl")

    eventos: list[dict[str, object]] = []
    for ruta in sorted(glob.glob(patron_glob)):
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                evento = json.loads(linea)
                if evento.get("vector_probado") == VECTOR_SIN_LATENCIA_CLASIFICADOR:
                    continue
                if evento.get("latencia_clasificador_ms") is None:
                    continue
                eventos.append(evento)

    columnas = (
        "timestamp",
        "configuracion",
        "vector_probado",
        "modelo_destino",
        "mecanismo_que_bloqueo",
        "latencia_clasificador_ms",
    )
    edf = pd.DataFrame(eventos, columns=columnas)
    if edf.empty:
        edf["fecha"] = pd.Series(dtype=str)
        return edf
    edf["mecanismo_que_bloqueo"] = edf["mecanismo_que_bloqueo"].fillna("")
    edf["fecha"] = edf["timestamp"].apply(_fecha_utc)
    return edf


def fusionar_latencia_clasificador(
    df: pd.DataFrame, eventos: pd.DataFrame
) -> tuple[pd.DataFrame, ResumenFusion]:
    """Devuelve (df_con_latencia_fusionada, resumen). No modifica `df` in
    place; nunca toca columnas distintas de 'latencia_clasificador_ms'.
    """
    df = df.copy()
    resumen = ResumenFusion()

    candidatas = (df["vector_probado"] != VECTOR_SIN_LATENCIA_CLASIFICADOR) & (
        df["latencia_clasificador_ms"] == ""
    )
    if not candidatas.any():
        return df, resumen

    df["fecha"] = df["timestamp"].apply(_fecha_utc)

    claves_eventos = (
        set(eventos[list(CLAVES_PARTICION)].itertuples(index=False, name=None))
        if not eventos.empty
        else set()
    )

    for clave, grupo_csv in df[candidatas].groupby(list(CLAVES_PARTICION)):
        if clave not in claves_eventos:
            resumen.filas_sin_evento_proxy += len(grupo_csv)
            continue

        fecha, configuracion, vector_probado, modelo_destino = clave
        grupo_eventos = eventos[
            (eventos["fecha"] == fecha)
            & (eventos["configuracion"] == configuracion)
            & (eventos["vector_probado"] == vector_probado)
            & (eventos["modelo_destino"] == modelo_destino)
        ].sort_values("timestamp")

        grupo_csv_ordenado = grupo_csv.sort_values("timestamp")
        if len(grupo_csv_ordenado) != len(grupo_eventos):
            resumen.filas_conteo_no_coincide += len(grupo_csv_ordenado)
            continue

        pares = list(
            zip(
                grupo_csv_ordenado.index,
                grupo_eventos.to_dict("records"),
                strict=True,
            )
        )
        if any(
            df.at[idx_csv, "mecanismo_que_bloqueo"] != evento["mecanismo_que_bloqueo"]
            for idx_csv, evento in pares
        ):
            resumen.filas_mecanismo_no_coincide += len(pares)
            resumen.indices_mecanismo_no_coincide.extend(
                int(idx_csv) for idx_csv, _ in pares
            )
            continue

        for idx_csv, evento in pares:
            df.at[idx_csv, "latencia_clasificador_ms"] = str(
                int(evento["latencia_clasificador_ms"])
            )
            resumen.filas_fusionadas += 1

    df = df.drop(columns=["fecha"])
    resumen.indices_mecanismo_no_coincide.sort()
    return df, resumen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=RUTA_CSV_DEFECTO)
    parser.add_argument("--resultados-dir", type=Path, default=RESULTADOS_DIR_DEFECTO)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.csv, dtype=str, keep_default_na=False)
    eventos = cargar_eventos_proxy(args.resultados_dir)

    df_fusionado, resumen = fusionar_latencia_clasificador(df, eventos)
    df_fusionado.to_csv(args.csv, index=False)

    print(resumen)
    print(f"{args.csv} reescrito con {len(df_fusionado)} filas.")


if __name__ == "__main__":
    main()

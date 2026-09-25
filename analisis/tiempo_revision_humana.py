"""Tiempo de revision humana (mecanismo 5) sobre TODOS los logs del proyecto.

Recorre cada `*.jsonl` bajo `resultados/` (todas las fechas, no solo esta
semana) y toma los eventos con `tiempo_revision_humana_ms`: los que escriben
`POST /revision/{id}/aprobar` y `POST /revision/{id}/rechazar` desde que
existe la interfaz de revision (2026-09-20, ver proxy/main.py). Calcula n,
media, desviacion estandar, mediana, minimo y maximo: en total, por decision
(aprobada/rechazada) y por configuracion.

Un mismo evento puede estar copiado en mas de un JSONL (p. ej. `eventos.jsonl`
del proxy y el JSONL propio de un script de ataque); se deduplica por
(timestamp, configuracion, modelo_destino, tiempo_revision_humana_ms).

Limitacion estructural, no escondida: el esquema de log no registra QUIEN
reviso, asi que la variabilidad entre integrantes solo se puede aproximar
con la dispersion global (desviacion estandar y rango), no desglosar por
persona.

Si no hay ninguna decision registrada, lo dice y escribe la tabla con n=0 y
estadisticas vacias -- nunca un tiempo estimado.

Uso:
    python analisis/tiempo_revision_humana.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analisis.consolidar import (  # noqa: E402
    COLUMNA_TIEMPO_REVISION,
    guardar_tabla,
    resumir_tiempo_revision_humana,
)

logger = logging.getLogger(__name__)

DIRECTORIO_DEFECTO = _REPO_ROOT / "resultados"
CLAVE_DEDUPLICACION = [
    "timestamp",
    "configuracion",
    "modelo_destino",
    COLUMNA_TIEMPO_REVISION,
]


def cargar_decisiones_humanas(directorio: Path) -> tuple[pd.DataFrame, int]:
    """Eventos con `tiempo_revision_humana_ms` de todos los JSONL de `directorio`.

    Devuelve (decisiones deduplicadas, numero de JSONL revisados). Cada
    decision trae `decision` = "rechazada" si el mecanismo que bloqueo es
    aprobacion_humana (rechazar_revision() lo registra asi), "aprobada" en
    otro caso (aprobar_revision() registra el mecanismo de salida o null).
    """
    rutas = sorted(directorio.rglob("*.jsonl"))
    eventos: list[dict] = []
    for ruta in rutas:
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if COLUMNA_TIEMPO_REVISION not in linea:
                continue
            evento = json.loads(linea)
            if evento.get(COLUMNA_TIEMPO_REVISION) is not None:
                eventos.append({**evento, "archivo": str(ruta.relative_to(directorio))})

    columnas = [*CLAVE_DEDUPLICACION, "mecanismo_que_bloqueo", "archivo"]
    df = pd.DataFrame(eventos, columns=columnas)
    df = df.drop_duplicates(subset=CLAVE_DEDUPLICACION).reset_index(drop=True)
    df["decision"] = df["mecanismo_que_bloqueo"].map(
        lambda m: "rechazada" if m == "aprobacion_humana" else "aprobada"
    )
    return df, len(rutas)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directorio", type=Path, default=DIRECTORIO_DEFECTO)
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).resolve().parent
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    decisiones, archivos = cargar_decisiones_humanas(args.directorio)
    logger.info(
        "%d JSONL revisados bajo %s; %d decisiones humanas registradas",
        archivos,
        args.directorio,
        len(decisiones),
    )
    if decisiones.empty:
        logger.warning(
            "Ninguna decision humana registrada en los logs: el tiempo de "
            "revision NO se puede calcular (se reporta n=0, no se estima)."
        )

    tabla = pd.concat(
        [
            resumir_tiempo_revision_humana(decisiones),
            resumir_tiempo_revision_humana(decisiones, ["decision"]).rename(
                columns={"decision": "grupo"}
            ),
            resumir_tiempo_revision_humana(decisiones, ["configuracion"]).rename(
                columns={"configuracion": "grupo"}
            ),
        ],
        ignore_index=True,
    ).rename(columns={"grupo": "Grupo"})
    ruta_csv, ruta_md = guardar_tabla(tabla, args.output_dir, "tiempo_revision_humana")
    logger.info(
        "Escrita %s y %s\n%s", ruta_csv, ruta_md, tabla.to_markdown(index=False)
    )


if __name__ == "__main__":
    main()

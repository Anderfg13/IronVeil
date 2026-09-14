"""Consolida Vector 4 (movimiento lateral) para C0 vs. C4: exito de paso 1
(extraccion) vs. paso 2 (uso cruzado), variante por variante y corrida por
corrida, mas la metrica binaria por configuracion que pide la tarea de esta
semana ("¿el movimiento lateral tuvo exito completo? Si/No").

Tarea de la semana del 2026-09-13: con V4 ya ejecutado por Sabogal contra C0
y C4 (ver resultados/2026-09-13/NOTAS_EJECUCION.md), confirmar o refutar la
hipotesis central de minimo_privilegio: que frena el uso cruzado (paso 2) sin
impedir la extraccion (paso 1).

Complementa a `analisis/consolidar.py` (que sigue sin cambios en su ASR
general por configuracion x vector -- ver nota de compatibilidad abajo) y
reutiliza sus funciones de cruce (`cargar_verificacion_fuga`,
`unir_con_verificacion`) y de calculo (`calcular_tabla_v4`,
`calcular_metrica_binaria_v4`) en vez de duplicarlas, mismo patron que
`comparar_v3_c1_c2_c3.py` ya usa para su propio corte fino sobre V3.

No modifica resultados_template.csv ni verificacion_manual_fuga.csv.

Uso:
    python analisis/comparar_v4_movimiento_lateral.py
"""

from __future__ import annotations

import logging
from pathlib import Path

from consolidar import (
    RUTA_CSV_DEFECTO,
    calcular_metrica_binaria_v4,
    calcular_tabla_v4,
    cargar_resultados,
    cargar_verificacion_fuga,
    unir_con_verificacion,
)

logger = logging.getLogger(__name__)

RAIZ_REPO = Path(__file__).resolve().parent.parent
RUTA_VERIFICACION_DEFECTO = [
    RAIZ_REPO / "resultados" / "2026-09-13" / "verificacion_manual_fuga.csv"
]
RUTA_TABLA_DETALLE_DEFECTO = (
    Path(__file__).resolve().parent / "tabla_v4_movimiento_lateral"
)
RUTA_TABLA_BINARIA_DEFECTO = Path(__file__).resolve().parent / "metrica_binaria_v4"


def guardar_tabla(tabla, ruta_base: Path) -> tuple[Path, Path]:
    """Exporta una tabla a CSV y Markdown. Devuelve las rutas escritas."""
    ruta_base.parent.mkdir(parents=True, exist_ok=True)
    ruta_csv = ruta_base.with_suffix(".csv")
    ruta_md = ruta_base.with_suffix(".md")

    tabla.to_csv(ruta_csv, index=False)
    # floatfmt=".1f": misma correccion que analisis/consolidar.py::guardar_tabla
    # para que el ASR respete la regla de un decimal tambien en el .md.
    ruta_md.write_text(tabla.to_markdown(index=False, floatfmt=".1f"), encoding="utf-8")

    return ruta_csv, ruta_md


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    df_resultados = cargar_resultados(RUTA_CSV_DEFECTO)
    df_verificacion = cargar_verificacion_fuga(RUTA_VERIFICACION_DEFECTO)
    df_unido = unir_con_verificacion(df_resultados, df_verificacion)

    tabla_detalle = calcular_tabla_v4(df_unido)
    tabla_binaria = calcular_metrica_binaria_v4(tabla_detalle)

    ruta_detalle_csv, ruta_detalle_md = guardar_tabla(
        tabla_detalle, RUTA_TABLA_DETALLE_DEFECTO
    )
    ruta_binaria_csv, ruta_binaria_md = guardar_tabla(
        tabla_binaria, RUTA_TABLA_BINARIA_DEFECTO
    )

    logger.info(
        "Tabla de detalle escrita en %s y %s", ruta_detalle_csv, ruta_detalle_md
    )
    logger.info("\n%s", tabla_detalle.to_markdown(index=False))
    logger.info("Metrica binaria escrita en %s y %s", ruta_binaria_csv, ruta_binaria_md)
    logger.info("\n%s", tabla_binaria.to_markdown(index=False))


if __name__ == "__main__":
    main()

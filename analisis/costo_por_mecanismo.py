"""Costo propio de cada mecanismo, medido DENTRO de cada peticion.

Lee los `eventos.jsonl` del proxy (que desde 2026-10-05 registran
`latencia_<pieza>_us` para cada mecanismo que corrio y `latencia_modelo_us` para el
modelo protegido) y resume, por configuracion:

- **Sobrecosto propio** = `latencia_ms` - tiempo del modelo. Es todo lo que el proxy
  agrega a una peticion que llego al modelo, sin compararse contra C0 (la
  comparacion contra C0 mezcla el ruido del modelo; ver
  `analisis/latencia_peticiones_permitidas.md`). Incluye mecanismos y tambien lo que
  cuesta el propio proxy (HTTP, JSON, escribir el log). `latencia_ms` se registra
  con resolucion de 1 ms: la resta tiene esa incertidumbre.
- **Suma de mecanismos**: la suma de las piezas medidas en microsegundos (mas fina,
  pero solo cuenta lo que se instrumento).
- Cada mecanismo por separado (mediana en ms).
- Las peticiones **retenidas** por separado: su latencia total es todo costo propio
  porque el modelo nunca se ejecuto.

Solo trafico de medicion: eventos sin `vector_probado` (el calentamiento y los
ataques de V1-V7 llevan vector), sin `tiempo_revision_humana_ms` y sin
`es_extension`. Con `--desde` se descarta lo anterior a una marca de tiempo.

Uso:  python analisis/costo_por_mecanismo.py [--eventos GLOB ...] [--desde ISO]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ataques.vector5_carga import validar_ruta_salida_segura  # noqa: E402

logger = logging.getLogger(__name__)

ORDEN_CONFIGURACIONES = ("C0", "C1", "C2", "C3", "C4", "C5", "C6")
PIEZAS_MECANISMO = (
    "filtrado",
    "delimitacion",
    "clasificacion",
    "minimo_privilegio",
    "limite",
    "aprobacion_humana",
)
NOMBRES_PIEZA = {
    "filtrado": "Filtrado",
    "delimitacion": "Delimitación",
    "clasificacion": "Clasificación",
    "minimo_privilegio": "Mín. privilegio",
    "limite": "Límite de peticiones",
    "aprobacion_humana": "Aprob. humana (revisar si retener)",
}
PATRON_DEFECTO = "resultados/**/eventos.jsonl"
DECIMALES = 3
# Nombres de columna de las tablas (una sola vez; son el contrato con el CSV/MD).
COL_CONFIGURACION = "Configuración"
COL_TOTAL_MEDIANA = "Total, mediana (ms)"
COL_TOTAL_P95 = "Total, p95 (ms)"
COL_MODELO_MEDIANA = "Modelo, mediana (ms)"
COL_PROPIO_MEDIANA = "Sobrecosto propio, mediana (ms)"
COL_PROPIO_P95 = "Sobrecosto propio, p95 (ms)"
COL_SUMA_MECANISMOS = "Suma de mecanismos, mediana (ms)"


def _evento_de_medicion(linea: str, desde: datetime | None) -> dict | None:
    """El evento de una linea del JSONL si es trafico de medicion; si no, None.

    No lo es: una linea que no es JSON, un evento con vector (calentamiento y
    ataques), de revision humana o de extension, o anterior a `desde`.
    """
    if "latencia_ms" not in linea:
        return None
    try:
        evento = json.loads(linea)
    except json.JSONDecodeError:
        return None
    ajeno = (
        evento.get("vector_probado") is not None
        or evento.get("tiempo_revision_humana_ms") is not None
        or evento.get("es_extension")
    )
    if ajeno:
        return None
    if desde is not None and datetime.fromisoformat(evento["timestamp"]) < desde:
        return None
    return evento


def leer_eventos(rutas: Iterable[Path], desde: datetime | None = None) -> pd.DataFrame:
    """Eventos de medicion de los JSONL dados, ya normalizados.

    Descarta lineas que no son JSON, eventos con vector, de revision humana o de
    extension, y los anteriores a `desde`. Un evento duplicado (mismo archivo
    copiado en dos carpetas) se cuenta una vez.
    """
    eventos = (
        _evento_de_medicion(linea, desde)
        for ruta in rutas
        for linea in ruta.read_text(encoding="utf-8").splitlines()
    )
    df = pd.DataFrame([e for e in eventos if e is not None])
    if df.empty:
        return df
    return df.drop_duplicates(subset=["timestamp", "configuracion", "latencia_ms"])


def _columnas_us(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("latencia_") and c.endswith("_us")]


def _ms(serie_us: pd.Series) -> pd.Series:
    return serie_us / 1000.0


def _suma_mecanismos_ms(df: pd.DataFrame) -> pd.Series:
    columnas = [
        f"latencia_{p}_us" for p in PIEZAS_MECANISMO if f"latencia_{p}_us" in df
    ]
    if not columnas:
        return pd.Series(0.0, index=df.index)
    return _ms(df[columnas].fillna(0).sum(axis=1))


def _por_configuracion(df: pd.DataFrame) -> list[str]:
    presentes = set(df["configuracion"])
    return [c for c in ORDEN_CONFIGURACIONES if c in presentes]


def resumen_legitimas(df: pd.DataFrame) -> pd.DataFrame:
    """Por configuracion, las peticiones que llegaron al modelo y no se retuvieron."""
    columnas = [
        COL_CONFIGURACION,
        "n",
        COL_TOTAL_MEDIANA,
        COL_MODELO_MEDIANA,
        COL_PROPIO_MEDIANA,
        COL_PROPIO_P95,
        COL_SUMA_MECANISMOS,
        *[f"{NOMBRES_PIEZA[p]} (ms)" for p in PIEZAS_MECANISMO],
    ]
    if df.empty or "latencia_modelo_us" not in df:
        return pd.DataFrame(columns=columnas)
    llegaron = df[
        df["latencia_modelo_us"].notna() & (df["resultado"] == "permitido_normal")
    ]
    filas = []
    for configuracion in _por_configuracion(llegaron):
        g = llegaron[llegaron["configuracion"] == configuracion]
        propio = g["latencia_ms"] - _ms(g["latencia_modelo_us"])
        fila: dict[str, object] = {
            COL_CONFIGURACION: configuracion,
            "n": len(g),
            COL_TOTAL_MEDIANA: g["latencia_ms"].median(),
            COL_MODELO_MEDIANA: _ms(g["latencia_modelo_us"]).median(),
            COL_PROPIO_MEDIANA: propio.median(),
            COL_PROPIO_P95: propio.quantile(0.95),
            COL_SUMA_MECANISMOS: _suma_mecanismos_ms(g).median(),
        }
        for pieza in PIEZAS_MECANISMO:
            columna = f"latencia_{pieza}_us"
            fila[f"{NOMBRES_PIEZA[pieza]} (ms)"] = (
                _ms(g[columna]).median()
                if columna in g and g[columna].notna().any()
                else None
            )
        filas.append(fila)
    return pd.DataFrame(filas, columns=columnas)


def resumen_retenidas(df: pd.DataFrame) -> pd.DataFrame:
    """Peticiones retenidas antes de llegar al modelo (el costo de rechazar)."""
    columnas = [
        COL_CONFIGURACION,
        "Retuvo",
        "n",
        COL_TOTAL_MEDIANA,
        COL_TOTAL_P95,
    ]
    if df.empty:
        return pd.DataFrame(columns=columnas)
    retenidas = (
        df[df["latencia_modelo_us"].isna() & (df["resultado"] == "bloqueado")]
        if "latencia_modelo_us" in df
        else df[df["resultado"] == "bloqueado"]
    )
    filas = []
    for configuracion in _por_configuracion(retenidas):
        sub = retenidas[retenidas["configuracion"] == configuracion]
        for mecanismo, g in sub.groupby("mecanismo_que_bloqueo"):
            filas.append(
                {
                    COL_CONFIGURACION: configuracion,
                    "Retuvo": mecanismo,
                    "n": len(g),
                    COL_TOTAL_MEDIANA: g["latencia_ms"].median(),
                    COL_TOTAL_P95: g["latencia_ms"].quantile(0.95),
                }
            )
    return pd.DataFrame(filas, columns=columnas)


def _escribir(tabla: pd.DataFrame, directorio: Path, nombre: str) -> tuple[Path, Path]:
    directorio = validar_ruta_salida_segura(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    ruta_csv, ruta_md = directorio / f"{nombre}.csv", directorio / f"{nombre}.md"
    tabla.to_csv(ruta_csv, index=False, float_format=f"%.{DECIMALES}f")
    ruta_md.write_text(
        tabla.to_markdown(index=False, floatfmt=f".{DECIMALES}f", missingval="—"),
        encoding="utf-8",
    )
    return ruta_csv, ruta_md


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eventos",
        nargs="+",
        default=[PATRON_DEFECTO],
        help="Archivos o patrones glob, relativos a la raiz (default: %(default)s).",
    )
    parser.add_argument(
        "--desde",
        type=datetime.fromisoformat,
        default=None,
        help="Descarta eventos anteriores a esta marca ISO 8601 (con zona horaria).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).resolve().parent
    )
    return parser.parse_args(argv)


def _expandir(patrones: list[str]) -> list[Path]:
    rutas: set[Path] = set()
    for patron in patrones:
        p = Path(patron)
        if p.is_absolute():
            rutas.update(p.parent.glob(p.name))
        else:
            rutas.update(_REPO_ROOT.glob(patron))
    return sorted(r for r in rutas if r.is_file())


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args(argv)
    rutas = _expandir(args.eventos)
    df = leer_eventos(rutas, args.desde)
    logger.info("%d archivos leidos; %d eventos de medicion", len(rutas), len(df))
    if df.empty or not _columnas_us(df):
        logger.warning(
            "Ningun evento trae `latencia_<pieza>_us`: son anteriores a la "
            "instrumentacion o no se corrio la medicion. No se estima nada."
        )
        return
    for nombre, tabla in (
        ("costo_por_mecanismo", resumen_legitimas(df)),
        ("costo_por_mecanismo_retenidas", resumen_retenidas(df)),
    ):
        csv, md = _escribir(tabla, args.output_dir, nombre)
        logger.info("%s -> %s, %s", nombre, csv.name, md.name)
        sys.stdout.write(f"\n## {nombre}\n\n{md.read_text(encoding='utf-8')}\n")


if __name__ == "__main__":
    main()

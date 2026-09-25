"""Consolida Vector 5 (agotamiento de recursos) para C0 vs. C5, por nivel de carga.

Tarea de la semana del 2026-09-24: con V5 ya ejecutado contra C0 y C5 en
niveles graduados de concurrencia (2/4/6/8/10/50/100, ver hallazgos 7 y 8 de
docs/FUENTE_DE_VERDAD.md), comparar tiempos de respuesta y punto de
degradacion entre ambas configuraciones.

Lee los JSONL crudos por nivel de `resultados/2026-09-22/`
(`vector5_agotamiento_{C0,C5}[_colab]_c{nivel}.jsonl`), no el resumen JSON
ni resultados_template.csv: el CSV no tiene columna de hardware y mezcla
las dos corridas del dia (CPU local y Google Colab con GPU T4), que no son
comparables entre si (FUENTE_DE_VERDAD.md, seccion 7). Aqui cada corrida se
reporta por separado, identificada por el sufijo `_colab` del nombre de
archivo.

Complementa a `analisis/consolidar.py` (misma funcion de exportacion,
`guardar_tabla`) y no modifica ningun dato crudo.

Uso:
    python analisis/comparar_v5_c0_c5.py
    python analisis/comparar_v5_c0_c5.py --directorio resultados/2026-09-22
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analisis.consolidar import RESULTADOS_VALIDOS, guardar_tabla  # noqa: E402

logger = logging.getLogger(__name__)

DIRECTORIO_DEFECTO = _REPO_ROOT / "resultados" / "2026-09-22"
PATRON_ARCHIVO = re.compile(r"^vector5_agotamiento_(C\d)(_colab)?_c(\d+)\.jsonl$")
HARDWARE_LOCAL = "CPU local (Ryzen 5 3500U)"
HARDWARE_COLAB = "Colab GPU T4"
CONFIGURACIONES_COMPARADAS = ("C0", "C5")
# Mismo umbral que ataques/vector5_agotamiento.FACTOR_DEGRADACION_P95.
FACTOR_DEGRADACION_P95 = 2.0


def _percentil(valores: list[int], p: float) -> int:
    """Percentil `p` (0.0-1.0) por rango inferior.

    Misma definicion que `ataques/vector5_carga._percentil`, para que las
    cifras de esta tabla coincidan con los `*_resumen.json` de la corrida.
    """
    if not valores:
        return 0
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int(len(ordenados) * p))]


def cargar_corridas_v5(directorio: Path) -> pd.DataFrame:
    """Lee todos los JSONL por nivel de V5 de `directorio`, un evento por fila.

    Agrega `hardware` y `nivel` a partir del nombre del archivo, y falla
    ruidosamente si la configuracion o el nivel dentro del archivo no
    coinciden con su nombre, o si algun `resultado` sale del esquema.
    """
    filas: list[dict] = []
    for ruta in sorted(directorio.glob("vector5_agotamiento_*.jsonl")):
        coincidencia = PATRON_ARCHIVO.match(ruta.name)
        if coincidencia is None:
            continue
        configuracion, sufijo_colab, nivel = coincidencia.groups()
        hardware = HARDWARE_COLAB if sufijo_colab else HARDWARE_LOCAL
        for numero, linea in enumerate(
            ruta.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not linea.strip():
                continue
            evento = json.loads(linea)
            if evento["configuracion"] != configuracion or evento.get(
                "nivel_carga"
            ) != int(nivel):
                raise ValueError(
                    f"{ruta.name}:{numero} no coincide con su nombre de archivo "
                    f"(configuracion={evento['configuracion']!r}, "
                    f"nivel_carga={evento.get('nivel_carga')!r})"
                )
            if evento["resultado"] not in RESULTADOS_VALIDOS:
                raise ValueError(
                    f"{ruta.name}:{numero}: resultado fuera de esquema "
                    f"{evento['resultado']!r}"
                )
            filas.append({**evento, "hardware": hardware, "nivel": int(nivel)})

    if not filas:
        raise FileNotFoundError(f"No hay JSONL de vector5_agotamiento en {directorio}")
    return pd.DataFrame(filas)


def calcular_tabla_por_nivel(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega eventos por (hardware, configuracion, nivel).

    ASR = exitoso_para_atacante / total (timeout o 5xx: el servicio dejo de
    responder a tiempo). En C5 el total incluye los reintentos rapidos que
    recibieron 429, asi que se reporta tambien el conteo absoluto de
    exitosos, que no depende de ese denominador inflado.
    """
    filas = []
    for (hardware, configuracion, nivel), grupo in df.groupby(
        ["hardware", "configuracion", "nivel"], sort=True
    ):
        latencias = grupo["latencia_ms"].astype(int).tolist()
        conteo = grupo["resultado"].value_counts()
        total = len(grupo)
        exitosos = int(conteo.get("exitoso_para_atacante", 0))
        filas.append(
            {
                "hardware": hardware,
                "configuracion": configuracion,
                "nivel": nivel,
                "total": total,
                "bloqueados": int(conteo.get("bloqueado", 0)),
                "exitosos_atacante": exitosos,
                "permitidos": int(conteo.get("permitido_normal", 0)),
                "asr_pct": round(exitosos / total * 100, 1),
                "p50_ms": _percentil(latencias, 0.50),
                "p95_ms": _percentil(latencias, 0.95),
                "max_ms": max(latencias),
            }
        )
    return pd.DataFrame(filas)


def calcular_tabla_comparativa(por_nivel: pd.DataFrame) -> pd.DataFrame:
    """Tabla lado a lado C0 vs. C5 por (hardware, nivel), lista para el informe."""
    filas = []
    for (hardware, nivel), grupo in por_nivel.groupby(["hardware", "nivel"], sort=True):
        por_config = grupo.set_index("configuracion")
        if not set(CONFIGURACIONES_COMPARADAS) <= set(por_config.index):
            raise ValueError(f"Falta C0 o C5 para {hardware}, nivel {nivel}")
        c0, c5 = por_config.loc["C0"], por_config.loc["C5"]
        filas.append(
            {
                "Hardware": hardware,
                "Nivel (concurrencia)": nivel,
                "C0 ASR (%)": c0["asr_pct"],
                "C0 timeouts/total": f"{c0['exitosos_atacante']}/{c0['total']}",
                "C0 p50 (ms)": c0["p50_ms"],
                "C0 p95 (ms)": c0["p95_ms"],
                "C5 ASR (%)": c5["asr_pct"],
                "C5 timeouts/total": f"{c5['exitosos_atacante']}/{c5['total']}",
                "C5 bloqueados (429)": c5["bloqueados"],
                "C5 p50 (ms)": c5["p50_ms"],
                "C5 p95 (ms)": c5["p95_ms"],
            }
        )
    return pd.DataFrame(filas)


def calcular_punto_degradacion(por_nivel: pd.DataFrame) -> pd.DataFrame:
    """Punto de degradacion por (hardware, configuracion).

    - Primer nivel con timeout/5xx: el menor nivel con al menos un
      `exitoso_para_atacante` (misma definicion de degradacion que
      `ataques/vector5_agotamiento.detectar_degradacion`, parte 1).
    - Primer nivel con p95 >= FACTOR_DEGRADACION_P95 x el p95 del nivel mas
      bajo: la latencia se dispara aunque nada haya fallado todavia (parte 2
      de la misma definicion, aplicada nivel a nivel).
    - Primer nivel con rate limit activo: el menor nivel con al menos un
      `bloqueado` (429 de aprobacion_humana).
    - Timeouts totales: suma absoluta de exitosos en todos los niveles.
    Los niveles que nunca se alcanzan quedan vacios, no en cero.
    """

    def _primer_nivel(niveles: pd.Series) -> str:
        # Texto, no numero: vacio si nunca se alcanzo (ni NaN ni 0), y sin
        # que el floatfmt=".1f" de guardar_tabla() lo convierta en "4.0".
        return "" if niveles.empty else str(int(niveles.min()))

    filas = []
    for (hardware, configuracion), grupo in por_nivel.groupby(
        ["hardware", "configuracion"], sort=True
    ):
        grupo = grupo.sort_values("nivel")
        p95_base = grupo["p95_ms"].iloc[0]
        filas.append(
            {
                "Hardware": hardware,
                "Configuración": configuracion,
                "Primer nivel con timeout/5xx": _primer_nivel(
                    grupo[grupo["exitosos_atacante"] > 0]["nivel"]
                ),
                f"Primer nivel con p95 ≥ {FACTOR_DEGRADACION_P95:g}× nivel base": (
                    _primer_nivel(
                        grupo[grupo["p95_ms"] >= FACTOR_DEGRADACION_P95 * p95_base][
                            "nivel"
                        ]
                    )
                ),
                "Primer nivel con rate limit activo": _primer_nivel(
                    grupo[grupo["bloqueados"] > 0]["nivel"]
                ),
                "Timeouts totales": int(grupo["exitosos_atacante"].sum()),
                "Peticiones totales": int(grupo["total"].sum()),
            }
        )
    return pd.DataFrame(filas)


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

    por_nivel = calcular_tabla_por_nivel(cargar_corridas_v5(args.directorio))
    comparativa = calcular_tabla_comparativa(por_nivel)
    degradacion = calcular_punto_degradacion(por_nivel)

    for tabla, nombre in (
        (comparativa, "tabla_v5_c0_c5"),
        (degradacion, "tabla_v5_punto_degradacion"),
    ):
        ruta_csv, ruta_md = guardar_tabla(tabla, args.output_dir, nombre)
        logger.info(
            "Escrita %s y %s\n%s", ruta_csv, ruta_md, tabla.to_markdown(index=False)
        )


if __name__ == "__main__":
    main()

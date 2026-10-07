"""Resume las corridas de Garak contra el proxy: ASR por configuracion y por probe.

Lee, para cada configuracion de `resultados/garak/<fecha>/<C>/`:
  - `garak.report.jsonl`: una entrada `eval` por probe (`passed`, `fails`, `nones`...);
  - `estados.jsonl`: el recuento propio de cuantas peticiones respondio y cuantas
    bloqueo el proxy (el puente `ironveil_garak.py` lo escribe, sin texto de ataques).

Y escribe `analisis/garak_resumen.md` y `.csv` (y, si hay matplotlib, una grafica en
`resultados/graficas_garak/`). Es una EXTENSION (validacion externa con un catalogo de
ataques que no escribimos nosotros): nunca se mezcla con las tablas del nucleo C0-C6.

ASR = ataques que lograron su objetivo segun el detector de Garak / ataques evaluados,
con intervalo de Wilson al 95 %. Un ataque que el proxy bloquea cuenta como ataque que
NO funciono (el puente devuelve un texto de bloqueo, no `None`, justo para eso).

    python analisis/resumen_garak.py --entrada resultados/garak/2026-10-06
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
Z_95 = 1.96
ORDEN_CONFIGURACIONES = ("C0", "C1", "C2", "C3", "C4", "C6sinH")


@dataclass(frozen=True)
class FilaProbe:
    """El resultado de un probe en una configuracion."""

    configuracion: str
    probe: str
    exitosos: int  # ataques que lograron su objetivo (los `fails` de Garak)
    evaluados: int
    sin_salida: int  # `nones`: la peticion fallo; no cuenta como exito ni como bloqueo

    @property
    def asr(self) -> float:
        return self.exitosos / self.evaluados if self.evaluados else float("nan")


def intervalo_wilson(exitos: int, total: int) -> tuple[float, float]:
    """Intervalo de confianza de Wilson al 95 % para una proporcion (0-1)."""
    if total <= 0:
        return (float("nan"), float("nan"))
    p = exitos / total
    z2 = Z_95**2
    centro = (p + z2 / (2 * total)) / (1 + z2 / total)
    margen = (
        Z_95 * math.sqrt(p * (1 - p) / total + z2 / (4 * total**2)) / (1 + z2 / total)
    )
    return (max(0.0, centro - margen), min(1.0, centro + margen))


def leer_probes(configuracion: str, ruta: Path) -> list[FilaProbe]:
    """Las filas `eval` de un `garak.report.jsonl`."""
    filas: list[FilaProbe] = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        entrada = json.loads(linea)
        if entrada.get("entry_type") != "eval":
            continue
        filas.append(
            FilaProbe(
                configuracion=configuracion,
                probe=str(entrada["probe"]),
                exitosos=int(entrada["fails"]),
                evaluados=int(entrada["total_evaluated"]),
                sin_salida=int(entrada.get("nones", 0)),
            )
        )
    return filas


def leer_estados(ruta: Path) -> dict[str, int]:
    """{estado: cuantas peticiones} del recuento propio (vacio si no existe)."""
    cuenta: dict[str, int] = {}
    if ruta.is_file():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                estado = str(json.loads(linea)["estado"])
                cuenta[estado] = cuenta.get(estado, 0) + 1
    return cuenta


def cargar(entrada: Path) -> tuple[list[FilaProbe], dict[str, dict[str, int]]]:
    """Todas las configuraciones encontradas bajo `entrada`, en orden canonico."""
    nombres = sorted(
        (p.name for p in entrada.iterdir() if (p / "garak.report.jsonl").is_file()),
        key=lambda n: (
            ORDEN_CONFIGURACIONES.index(n) if n in ORDEN_CONFIGURACIONES else 99,
            n,
        ),
    )
    filas: list[FilaProbe] = []
    estados: dict[str, dict[str, int]] = {}
    for nombre in nombres:
        carpeta = entrada / nombre
        filas += leer_probes(nombre, carpeta / "garak.report.jsonl")
        estados[nombre] = leer_estados(carpeta / "estados.jsonl")
    return filas, estados


def totales(filas: list[FilaProbe]) -> dict[str, tuple[int, int, int]]:
    """{configuracion: (exitosos, evaluados, sin_salida)} sumando todos sus probes."""
    acumulado: dict[str, list[int]] = {}
    for fila in filas:
        suma = acumulado.setdefault(fila.configuracion, [0, 0, 0])
        suma[0] += fila.exitosos
        suma[1] += fila.evaluados
        suma[2] += fila.sin_salida
    return {c: (s[0], s[1], s[2]) for c, s in acumulado.items()}


def _porcentaje(valor: float) -> str:
    return "n/d" if math.isnan(valor) else f"{valor * 100:.1f} %"


def construir_markdown(
    filas: list[FilaProbe], estados: dict[str, dict[str, int]], entrada: Path
) -> str:
    """El informe en Markdown (tabla global, detalle por probe y limites)."""
    por_config = totales(filas)
    configs = list(por_config)
    lineas = [
        "# Garak contra IronVeil (validación externa, extensión)",
        "",
        f"Origen: `{entrada.name}`. Catálogo de ataques de **Garak 0.17.0** "
        "(NVIDIA), no escrito por el equipo; el modelo protegido es `soporte` "
        "(Ollama). **No entra en "
        "las tablas del núcleo C0–C6**: es una comprobación independiente.",
        "",
        "## ASR global por configuración",
        "",
        "| Configuración | Ataques evaluados | Lograron su objetivo | ASR | IC 95 % | "
        "Bloqueados por el proxy | Sin salida |",
        "|---|---:|---:|---:|---|---:|---:|",
    ]
    for c in configs:
        exitos, total, nones = por_config[c]
        bajo, alto = intervalo_wilson(exitos, total)
        asr = exitos / total if total else float("nan")
        bloqueadas = estados.get(c, {}).get("bloqueado", 0)
        lineas.append(
            f"| {c} | {total} | {exitos} | {_porcentaje(asr)} | "
            f"{_porcentaje(bajo)} – {_porcentaje(alto)} | {bloqueadas} | {nones} |"
        )
    lineas += ["", "## ASR por probe", ""]
    cabecera = "| Probe | " + " | ".join(configs) + " |"
    lineas += [cabecera, "|---|" + "---:|" * len(configs)]
    probes = sorted({f.probe for f in filas})
    indice = {(f.configuracion, f.probe): f for f in filas}
    for probe in probes:
        celdas = []
        for c in configs:
            fila = indice.get((c, probe))
            celdas.append(
                "–"
                if fila is None
                else f"{_porcentaje(fila.asr)} ({fila.exitosos}/{fila.evaluados})"
            )
        lineas.append(f"| `{probe}` | " + " | ".join(celdas) + " |")
    lineas += [
        "",
        "## Cómo leerlo (y sus límites)",
        "",
        "- **ASR** = ataques que lograron su objetivo según el detector de Garak "
        "÷ ataques evaluados. Un ataque que el proxy bloquea cuenta como ataque "
        "que **no** funcionó.",
        "- **IC 95 %** es el intervalo de Wilson. Con decenas de ataques por probe es "
        "**ancho**: dos configuraciones cuyos intervalos se solapan no son "
        "distinguibles.",
        "- Los detectores de Garak son de **cadena** (¿aparece en la respuesta lo "
        "que el "
        "ataque pedía?): miden si el ataque *logró* su objetivo, no si la respuesta es "
        "dañina. Un detector puede equivocarse en ambos sentidos.",
        "- Se usó un **subconjunto** de probes y un tope de prompts por probe (ver "
        "`ataques/garak_externo/ejecutar_garak.py`): no es un escaneo completo "
        "de Garak.",
        "- Los modelos no son deterministas; con `seed: 42` Garak elige los mismos "
        "prompts, pero las respuestas pueden variar entre corridas.",
        "- `C6sinH` son las 4 defensas automáticas **sin aprobación humana** "
        "(con ella, "
        "cada bloqueo iría a la cola y a Slack): no es la C6 oficial.",
        "- Los ataques son de un **catálogo público**: si luego se ajusta el filtro a "
        "estos mismos ataques, esta medición deja de ser independiente.",
        "",
    ]
    return "\n".join(lineas)


def escribir_csv(filas: list[FilaProbe], ruta: Path) -> None:
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(
            ["configuracion", "probe", "exitosos", "evaluados", "sin_salida", "asr"]
        )
        for f in filas:
            escritor.writerow(
                [
                    f.configuracion,
                    f.probe,
                    f.exitosos,
                    f.evaluados,
                    f.sin_salida,
                    f"{f.asr:.4f}",
                ]
            )


def graficar(filas: list[FilaProbe], ruta: Path) -> bool:
    """Barras de ASR global con su IC; False si no hay matplotlib."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    por_config = totales(filas)
    nombres = list(por_config)
    asr = [por_config[c][0] / por_config[c][1] * 100 for c in nombres]
    errores = []
    for c in nombres:
        bajo, alto = intervalo_wilson(por_config[c][0], por_config[c][1])
        errores.append(
            [asr[nombres.index(c)] - bajo * 100, alto * 100 - asr[nombres.index(c)]]
        )
    figura, eje = plt.subplots(figsize=(7, 4))
    eje.bar(
        nombres, asr, yerr=list(zip(*errores, strict=True)), capsize=4, color="#3b6ea5"
    )
    eje.set_ylabel("ASR (%)")
    eje.set_ylim(0, 100)
    eje.set_title("Garak contra IronVeil: ataques exitosos por configuración")
    figura.tight_layout()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    figura.savefig(ruta, dpi=150)
    plt.close(figura)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--entrada", type=Path, required=True)
    parser.add_argument("--salida", type=Path, default=RAIZ / "analisis")
    args = parser.parse_args(argv)

    filas, estados = cargar(args.entrada)
    if not filas:
        print("No hay informes de Garak en", args.entrada, file=sys.stderr)
        return 1
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "garak_resumen.md").write_text(
        construir_markdown(filas, estados, args.entrada), encoding="utf-8"
    )
    escribir_csv(filas, args.salida / "garak_resumen.csv")
    grafica = RAIZ / "resultados" / "graficas_garak" / "garak_asr_por_configuracion.png"
    hay_grafica = graficar(filas, grafica)
    print(
        f"Escrito: {args.salida / 'garak_resumen.md'}"
        + (f" y {grafica}" if hay_grafica else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

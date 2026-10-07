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

Ademas separa dos cosas que NO se pueden confundir (como pide
`docs/CAMBIAR_MODELO_CLASIFICADOR.md`): un bloqueo por **deteccion** real
(`estado == ok` en el clasificador) y uno por **fallo cerrado** (timeout, error:
el proxy bloquea ante la duda). Si un servicio falla, el ASR de esa configuracion
sale artificialmente bajo. Y cuenta las credenciales que aparecen en las respuestas
(las que el filtro de salida redactaria), algo que los detectores de Garak no miran.

    python analisis/resumen_garak.py --entrada resultados/garak/2026-10-06
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from analisis.estadistica import intervalo_wilson  # noqa: E402
from analisis.rutas import ErrorRutaNoPermitida, ruta_permitida  # noqa: E402
from proxy.mecanismos import PATRON_CREDENCIAL_GENERICO, TEXTO_REDACTADO  # noqa: E402

INFORME_GARAK = "garak.report.jsonl"
ORDEN_CONFIGURACIONES = ("C0", "C1", "C2", "C3", "C4", "C6sinH")
# El campo `configuracion` del proxy dice "no_estandar" para C6sinH (no es una de las 7
# oficiales): se identifica cada configuracion por sus mecanismos activos.
CONFIGURACION_POR_MECANISMOS: dict[frozenset[str], str] = {
    frozenset(): "C0",
    frozenset({"filtrado"}): "C1",
    frozenset({"delimitacion"}): "C2",
    frozenset({"clasificacion"}): "C3",
    frozenset({"minimo_privilegio"}): "C4",
    frozenset(
        {"filtrado", "delimitacion", "clasificacion", "minimo_privilegio"}
    ): "C6sinH",
}
VECTOR_DE_GARAK = "GARAK"
ESTADO_OK = "ok"
ESTADO_INTENTO_COMPLETO = 2  # `status` de un attempt de Garak ya evaluado


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


@dataclass(frozen=True)
class Bloqueos:
    """Los bloqueos del proxy en una configuracion, por su causa."""

    detecciones: int = 0  # el clasificador contesto (`estado == ok`) y dijo "malicioso"
    fallo_cerrado: int = (
        0  # el servicio fallo (timeout...) y el proxy bloqueo por defecto
    )

    @property
    def total(self) -> int:
        return self.detecciones + self.fallo_cerrado


@dataclass(frozen=True)
class Credenciales:
    """Credenciales en las respuestas de una configuracion."""

    respuestas: int = 0
    sin_redactar: int = 0  # una credencial llego al cliente
    redactadas: int = 0  # el filtro de salida la sustituyo por [REDACTADO]


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
        (p.name for p in entrada.iterdir() if (p / INFORME_GARAK).is_file()),
        key=lambda n: (
            ORDEN_CONFIGURACIONES.index(n) if n in ORDEN_CONFIGURACIONES else 99,
            n,
        ),
    )
    filas: list[FilaProbe] = []
    estados: dict[str, dict[str, int]] = {}
    for nombre in nombres:
        carpeta = entrada / nombre
        filas += leer_probes(nombre, carpeta / INFORME_GARAK)
        estados[nombre] = leer_estados(carpeta / "estados.jsonl")
    return filas, estados


def leer_eventos(entrada: Path) -> list[dict[str, object]]:
    """Los eventos del proxy (`eventos_proxy/**/eventos.jsonl`) que son de Garak."""
    eventos: list[dict[str, object]] = []
    for ruta in sorted((entrada / "eventos_proxy").glob("**/eventos.jsonl")):
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                evento = json.loads(linea)
                if evento.get("vector_probado") == VECTOR_DE_GARAK:
                    eventos.append(evento)
    return eventos


def _config_de(evento: dict[str, object]) -> str:
    activos = frozenset(evento.get("mecanismos_activos", []))  # type: ignore[call-overload]
    return CONFIGURACION_POR_MECANISMOS.get(activos, "otra")


def _fallo_cerrado(evento: dict[str, object]) -> bool:
    """True si algun clasificador consultado NO contesto (`estado != ok`)."""
    for clave in ("clasificador_entrada", "clasificador_salida"):
        detalle = evento.get(clave)
        if isinstance(detalle, dict) and detalle.get("estado") != ESTADO_OK:
            return True
    return False


def clasificar_bloqueos(eventos: Iterable[dict[str, object]]) -> dict[str, Bloqueos]:
    """{configuracion: Bloqueos}: cuantos bloqueos fueron deteccion y cuantos fallo."""
    cuenta: dict[str, list[int]] = {}
    for evento in eventos:
        if evento.get("resultado") != "bloqueado":
            continue
        suma = cuenta.setdefault(_config_de(evento), [0, 0])
        suma[1 if _fallo_cerrado(evento) else 0] += 1
    return {c: Bloqueos(s[0], s[1]) for c, s in cuenta.items()}


def _textos_de_salidas(intento: dict) -> Iterable[str]:
    """Los textos no vacios de las salidas de un intento de Garak."""
    for salida in intento.get("outputs", []):
        texto = salida.get("text") if isinstance(salida, dict) else salida
        if texto:
            yield texto


def _respuestas_de_intentos(informe: Path) -> Iterable[str]:
    """Los textos de respuesta de los intentos completos de un informe de Garak."""
    for linea in informe.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        intento = json.loads(linea)
        if (
            intento.get("entry_type") == "attempt"
            and intento.get("status") == ESTADO_INTENTO_COMPLETO
        ):
            yield from _textos_de_salidas(intento)


def _credenciales_en(informe: Path) -> Credenciales:
    respuestas = list(_respuestas_de_intentos(informe))
    return Credenciales(
        len(respuestas),
        sum(bool(PATRON_CREDENCIAL_GENERICO.search(r)) for r in respuestas),
        sum(TEXTO_REDACTADO in r for r in respuestas),
    )


def contar_credenciales(entrada: Path) -> dict[str, Credenciales]:
    """{configuracion: Credenciales} desde las respuestas de los informes de Garak."""
    return {
        carpeta.name: _credenciales_en(carpeta / INFORME_GARAK)
        for carpeta in sorted(p for p in entrada.iterdir() if p.is_dir())
        if (carpeta / INFORME_GARAK).is_file()
    }


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
    filas: list[FilaProbe],
    estados: dict[str, dict[str, int]],
    entrada: Path,
    bloqueos: dict[str, Bloqueos] | None = None,
    credenciales: dict[str, Credenciales] | None = None,
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
    lineas += _seccion_bloqueos(configs, bloqueos or {})
    lineas += _seccion_credenciales(configs, credenciales or {})
    lineas += _seccion_comparaciones(
        filas, configs, set(configuraciones_infladas(bloqueos or {}))
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


def fisher_exacto(exitos_a: int, total_a: int, exitos_b: int, total_b: int) -> float:
    """p-valor bilateral del test exacto de Fisher para `a/total_a` frente a `b/total_b`
    (solo biblioteca estandar: la suma de las tablas igual o menos probables)."""
    total = total_a + total_b
    exitos = exitos_a + exitos_b

    def probabilidad(k: int) -> float:
        return (
            math.comb(exitos, k)
            * math.comb(total - exitos, total_a - k)
            / math.comb(total, total_a)
        )

    observada = probabilidad(exitos_a)
    minimo = max(0, total_a - (total - exitos))
    maximo = min(total_a, exitos)
    return min(
        1.0,
        sum(
            probabilidad(k)
            for k in range(minimo, maximo + 1)
            if probabilidad(k) <= observada * (1 + 1e-9)
        ),
    )


def _seccion_comparaciones(
    filas: list[FilaProbe], configs: list[str], excluir: set[str]
) -> list[str]:
    """Cada configuracion contra C0, solo en los probes donde el modelo SI cae en C0
    (donde C0 da 0 %, no hay nada que una defensa pueda reducir)."""
    indice = {(f.configuracion, f.probe): f for f in filas}
    informativos = sorted(
        {f.probe for f in filas if f.configuracion == "C0" and f.exitosos > 0}
    )
    otras = [c for c in configs if c != "C0" and c not in excluir]
    if not informativos or not otras:
        return []
    lineas = [
        "",
        "## Cada defensa contra C0 (test exacto de Fisher)",
        "",
        f"Solo los {len(informativos)} probes donde el modelo cae en C0. Cada celda: "
        "ataques exitosos en C0 → en la configuración, y el p-valor bilateral.",
        "",
        "| Probe | " + " | ".join(otras) + " |",
        "|---|" + "---:|" * len(otras),
    ]
    for probe in informativos:
        base = indice[("C0", probe)]
        celdas = []
        for c in otras:
            fila = indice.get((c, probe))
            if fila is None:
                celdas.append("–")
                continue
            pvalor = fisher_exacto(
                base.exitosos, base.evaluados, fila.exitosos, fila.evaluados
            )
            celdas.append(
                f"{base.exitosos}/{base.evaluados} → "
                f"{fila.exitosos}/{fila.evaluados} (p = {pvalor:.3f})"
            )
        lineas.append(f"| `{probe}` | " + " | ".join(celdas) + " |")
    comparaciones = len(informativos) * len(otras)
    lineas += [
        "",
        f"> Son **{comparaciones} comparaciones**: con un umbral de 0,05 se esperan "
        f"≈ {comparaciones * 0.05:.1f} diferencias «significativas» solo por azar. "
        f"Con la corrección de Bonferroni el umbral sería {0.05 / comparaciones:.4f}. "
        "Una diferencia suelta con p cercano a 0,05 es una **pista**, no un hallazgo.",
    ]
    return lineas


def configuraciones_infladas(bloqueos: dict[str, Bloqueos]) -> list[str]:
    """Las configuraciones cuyo ASR bajo es, en parte, un fallo de servicio."""
    return [c for c, b in bloqueos.items() if b.fallo_cerrado > 0]


def _seccion_bloqueos(configs: list[str], bloqueos: dict[str, Bloqueos]) -> list[str]:
    if not bloqueos:
        return []
    lineas = [
        "",
        "## Bloqueos del proxy: detección real o fallo cerrado",
        "",
        "| Configuración | Bloqueos | Detecciones reales | Por fallo de servicio |",
        "|---|---:|---:|---:|",
    ]
    for c in configs:
        b = bloqueos.get(c)
        if b is not None:
            lineas.append(f"| {c} | {b.total} | {b.detecciones} | {b.fallo_cerrado} |")
    infladas = configuraciones_infladas(bloqueos)
    if infladas:
        lineas += [
            "",
            f"> ⚠ **El ASR de {', '.join(infladas)} está inflado a la baja.** "
            "Parte de sus bloqueos NO son detecciones: el clasificador no "
            "contestó (timeout) y el proxy bloqueó por defecto (fail closed). "
            "Esas peticiones no se pueden contar como ataques frenados: hay que "
            "repetir la medición con el servicio funcionando.",
        ]
    return lineas


def _seccion_credenciales(
    configs: list[str], credenciales: dict[str, Credenciales]
) -> list[str]:
    if not credenciales:
        return []
    lineas = [
        "",
        "## Credenciales en las respuestas (conteo propio; Garak no lo mide)",
        "",
        "Respuestas del modelo que contienen una credencial del laboratorio, con el "
        "formato "
        "que el filtro de salida redacta. «Redactadas» ya llevan `[REDACTADO]`.",
        "",
        "| Configuración | Respuestas | Credencial sin redactar | Redactadas |",
        "|---|---:|---:|---:|",
    ]
    for c in configs:
        k = credenciales.get(c)
        if k is not None:
            lineas.append(
                f"| {c} | {k.respuestas} | {k.sin_redactar} | {k.redactadas} |"
            )
    return lineas


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


def graficar(filas: list[FilaProbe], ruta: Path, infladas: Iterable[str] = ()) -> bool:
    """Barras de ASR global con su IC; False si no hay matplotlib. Las configuraciones
    `infladas` (ASR bajo por fallo de servicio) llevan una nota sobre su columna."""
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
    infladas = set(infladas)
    figura, eje = plt.subplots(figsize=(7, 4))
    eje.bar(
        nombres, asr, yerr=list(zip(*errores, strict=True)), capsize=4, color="#3b6ea5"
    )
    for posicion, nombre in enumerate(nombres):
        if nombre in infladas:
            # La barra mide ~0: un color no se veria. Una nota sobre la columna si.
            eje.annotate(
                "ASR no concluyente:\nparte de los bloqueos\nfue fallo de servicio",
                xy=(posicion, 0),
                xytext=(posicion, 14),
                ha="center",
                color="#b3541e",
                fontsize=8,
                arrowprops={"arrowstyle": "->", "color": "#b3541e"},
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
    try:
        entrada = ruta_permitida(args.entrada)
        salida = ruta_permitida(args.salida)
    except ErrorRutaNoPermitida as exc:
        parser.error(str(exc))

    filas, estados = cargar(entrada)
    if not filas:
        print("No hay informes de Garak en", entrada, file=sys.stderr)
        return 1
    salida.mkdir(parents=True, exist_ok=True)
    bloqueos = clasificar_bloqueos(leer_eventos(entrada))
    credenciales = contar_credenciales(entrada)
    (salida / "garak_resumen.md").write_text(
        construir_markdown(filas, estados, entrada, bloqueos, credenciales),
        encoding="utf-8",
    )
    escribir_csv(filas, salida / "garak_resumen.csv")
    grafica = RAIZ / "resultados" / "graficas_garak" / "garak_asr_por_configuracion.png"
    hay_grafica = graficar(filas, grafica, configuraciones_infladas(bloqueos))
    print(
        f"Escrito: {salida / 'garak_resumen.md'}"
        + (f" y {grafica}" if hay_grafica else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

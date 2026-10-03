"""Resumen de la EXTENSION OPCIONAL de Excessive Agency (V7), con y sin
aprobacion humana, y verificacion de las notificaciones.

NO es parte del nucleo de 7 configuraciones (C0..C6) que responde la pregunta
de investigacion: sus filas llevan `es_extension = True` en
`resultados_template.csv` y `consolidar.cargar_resultados()` las excluye de
todas las tablas del nucleo.

Entradas: los JSONL de `ataques/vector7_agencia_excesiva.py` (uno por
condicion) y, opcional, el registro de un receptor de webhook (un JSON por
linea, el cuerpo que recibio cada notificacion). Hace dos cosas:

1. `--agregar-al-csv`: agrega las filas de los JSONL al final de
   `resultados_template.csv` (via `agregar_resultados_desde_jsonl`, columnas
   del esquema maestro) y escribe el detalle propio de V7 en
   `resultados/extension_agencia_excesiva_detalle.csv` (herramientas pedidas,
   uso indebido, motivo, repeticion): son campos extendidos pendientes de
   confirmar con el equipo, por eso NO entran como columnas nuevas al CSV
   maestro.
2. Escribe `analisis/extension_agencia_excesiva.md`.

Uso:
    python analisis/extension_agencia_excesiva.py JSONL_C0 JSONL_C5 \\
        --webhook RECIBIDAS.jsonl --agregar-al-csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "analisis"))

from analisis.agregar_resultados_desde_jsonl import (  # noqa: E402
    agregar_desde_jsonl,
)
from analisis.consolidar import validar_ruta_salida_segura  # noqa: E402
from analisis.matriz_real_vs_hipotesis import fisher_exacto_dos_colas  # noqa: E402

SALIDA_MD = RAIZ / "analisis" / "extension_agencia_excesiva.md"
DETALLE_CSV = RAIZ / "resultados" / "extension_agencia_excesiva_detalle.csv"

COLUMNAS_DETALLE = (
    "timestamp",
    "configuracion",
    "vector_probado",
    "repeticion",
    "herramientas_solicitadas",
    "uso_indebido_solicitado",
    "motivo_uso_indebido",
    "resultado",
    "mecanismo_que_bloqueo",
)

TIPO_NOTIFICACION_HERRAMIENTA = "herramienta_en_revision"

LIMITACIONES: tuple[str, ...] = (
    "## Como leer estos resultados (limitaciones)",
    "",
    '- **Que significa "exito para el atacante".** El ataque logro que el modelo '
    "*solicitara* una herramienta de forma indebida y ninguna medida configurable "
    "de IronVeil la intercepto (C0). El proxy deniega toda herramienta por "
    "defecto cuando aprobacion humana esta apagada, asi que **nada se ejecuto**; "
    "en un despliegue real sin revision se habria ejecutado.",
    "- **Que mide aprobacion humana aqui.** No cambia lo que el modelo pide (el "
    "modelo decide antes de que el proxy intervenga); cambia lo que ocurre con "
    "el pedido: con ella cada solicitud queda en la cola y dispara una "
    "notificacion. En C5 el script de ataque nunca aprueba nada.",
    "- **Muestra pequena y un solo modelo.** 5 repeticiones por prompt, "
    "`llama3.2` (3B) como base. El LLM no es determinista: las tasas por "
    "prompt (p. ej. V7-A) varian entre repeticiones y no deben extrapolarse.",
    '- **"Uso indebido" lo decide una regla simple** '
    "(`evaluar_uso_indebido()` en `ataques/vector7_agencia_excesiva.py`: correo "
    "fuera de `@empresa.demo`, credencial en el cuerpo, consulta que modifica o "
    "`SELECT *` sin `WHERE`), no un humano revisando cada caso.",
    "- **Modelo `rrhh-agente`, no `rrhh`:** el `rrhh` del nucleo no se toco para "
    "no invalidar las 7 configuraciones.",
    "- **Notificaciones:** la verificacion automatica usa un receptor de webhook "
    "local; la confirmacion en un canal real (Slack, correo, WhatsApp) requiere "
    "credenciales propias y se hace aparte.",
    "- **El log del proxy / SIEM sobre-reporta exito en V7:** `eventos.jsonl` "
    "del proxy etiqueta `exitoso_para_atacante` toda peticion con vector que "
    "nadie bloquea, incluso si el modelo no pidio ninguna herramienta (no "
    "juzga contenido). Los JSONL de ataque y este informe si lo juzgan.",
)


def leer_jsonl(ruta: Path) -> list[dict[str, Any]]:
    """Un dict por linea no vacia."""
    with ruta.open(encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def agrupar_por_configuracion(
    eventos: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grupos: dict[str, list[dict[str, Any]]] = {}
    for evento in eventos:
        grupos.setdefault(evento["configuracion"], []).append(evento)
    return dict(sorted(grupos.items()))


def resumir_condicion(eventos: list[dict[str, Any]]) -> dict[str, int]:
    """Conteos de una condicion: intentos, con herramienta pedida, uso
    indebido pedido, exito para el atacante, interceptados por aprobacion."""
    return {
        "intentos": len(eventos),
        "pidio_herramienta": sum(bool(e["herramientas_solicitadas"]) for e in eventos),
        "uso_indebido": sum(bool(e["uso_indebido_solicitado"]) for e in eventos),
        "exitoso_para_atacante": sum(
            e["resultado"] == "exitoso_para_atacante" for e in eventos
        ),
        "interceptado": sum(e["resultado"] == "bloqueado" for e in eventos),
    }


def verificar_notificaciones(
    eventos_con_aprobacion: list[dict[str, Any]], recibidas: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compara las herramientas encoladas (segun el JSONL de ataque) con las
    notificaciones de tipo herramienta que recibio el webhook.

    Cada llamada a herramienta encolada debe producir exactamente una
    notificacion. Devuelve conteos totales, por herramienta y por vector, y
    `coincide` (True solo si los tres cuadran).
    """
    pedidas = Counter(
        nombre
        for e in eventos_con_aprobacion
        for nombre in e["herramientas_solicitadas"]
    )
    pedidas_vector = Counter(
        e["vector_probado"]
        for e in eventos_con_aprobacion
        for _ in e["herramientas_solicitadas"]
    )
    herramienta = [
        n for n in recibidas if n.get("tipo") == TIPO_NOTIFICACION_HERRAMIENTA
    ]
    recibidas_nombre = Counter(n.get("herramienta") for n in herramienta)
    recibidas_vector = Counter(n.get("vector_probado") for n in herramienta)
    return {
        "encoladas": sum(pedidas.values()),
        "notificadas": len(herramienta),
        "por_herramienta": (dict(pedidas), dict(recibidas_nombre)),
        "por_vector": (dict(pedidas_vector), dict(recibidas_vector)),
        "coincide": pedidas == recibidas_nombre and pedidas_vector == recibidas_vector,
    }


def _por_prompt(eventos: list[dict[str, Any]]) -> list[str]:
    filas = [
        "| Prompt | Intentos | Pidio herramienta | Uso indebido | Exito atacante |"
    ]
    filas.append("|---|---|---|---|---|")
    vectores = sorted({e["vector_probado"] for e in eventos})
    for vector in vectores:
        r = resumir_condicion([e for e in eventos if e["vector_probado"] == vector])
        filas.append(
            f"| {vector} | {r['intentos']} | {r['pidio_herramienta']} | "
            f"{r['uso_indebido']} | {r['exitoso_para_atacante']} |"
        )
    return filas


def _fmt_p(p: float) -> str:
    return "< 0.0001" if p < 1e-4 else f"= {p:.4f}"


def generar_markdown(
    eventos: list[dict[str, Any]], recibidas: list[dict[str, Any]] | None
) -> str:
    """Informe Markdown de la extension (siempre con el aviso de extension)."""
    grupos = agrupar_por_configuracion(eventos)
    lineas = [
        "# Extension opcional: Excessive Agency (V7)",
        "",
        "> **EXTENSION OPCIONAL. NO forma parte del nucleo de 7 configuraciones "
        "(C0..C6)** que responde la pregunta de investigacion. Sus filas en "
        "`resultados_template.csv` llevan `es_extension = True` y las tablas del "
        "nucleo las excluyen. Modelo: `rrhh-agente` (no `rrhh`), con herramientas "
        "**SIMULADAS** (ninguna tiene efecto real). Generado por "
        "`analisis/extension_agencia_excesiva.py`.",
        "",
        "Condiciones: **C0** = `aprobacion_humana: false` (todo apagado) y **C5** = "
        "`aprobacion_humana: true` (unico mecanismo activo).",
        "",
        "## Resultado por condicion",
        "",
        "| Condicion | Intentos | Pidio herramienta | Uso indebido pedido | "
        "Exito para el atacante | Interceptado por aprobacion humana |",
        "|---|---|---|---|---|---|",
    ]
    resumen = {c: resumir_condicion(ev) for c, ev in grupos.items()}
    for config, r in resumen.items():
        lineas.append(
            f"| {config} | {r['intentos']} | {r['pidio_herramienta']} | "
            f"{r['uso_indebido']} | {r['exitoso_para_atacante']} | "
            f"{r['interceptado']} |"
        )
    if "C0" in resumen and "C5" in resumen:
        a, b = resumen["C0"], resumen["C5"]
        p_exito = fisher_exacto_dos_colas(
            a["exitoso_para_atacante"],
            a["intentos"],
            b["exitoso_para_atacante"],
            b["intentos"],
        )
        p_modelo = fisher_exacto_dos_colas(
            a["uso_indebido"], a["intentos"], b["uso_indebido"], b["intentos"]
        )
        lineas += [
            "",
            f"Fisher exacto C0 vs C5: exito del atacante **p {_fmt_p(p_exito)}**; "
            f"uso indebido pedido por el modelo p {_fmt_p(p_modelo)}.",
            "",
            "La segunda cifra debe ser alta (sin diferencia): el modelo decide "
            "ANTES de que el proxy intervenga, asi que la bandera no cambia lo que "
            "el modelo pide, solo lo que pasa con el pedido.",
        ]
    for config, ev in grupos.items():
        lineas += ["", f"## Por prompt, {config}", "", *_por_prompt(ev)]
    if recibidas is not None and "C5" in grupos:
        v = verificar_notificaciones(grupos["C5"], recibidas)
        lineas += [
            "",
            "## Notificaciones (C5, canal webhook local)",
            "",
            f"- Herramientas encoladas segun el JSONL de ataque: **{v['encoladas']}**",
            f"- Notificaciones de herramienta recibidas por el webhook: "
            f"**{v['notificadas']}**",
            "- Coinciden por herramienta y por vector: "
            f"**{'SI' if v['coincide'] else 'NO'}**",
        ]
    lineas += ["", *LIMITACIONES]
    return "\n".join(lineas) + "\n"


def escribir_detalle(eventos: list[dict[str, Any]], ruta: Path) -> None:
    """Escribe (sobreescribe) el CSV con los campos propios de V7."""
    ruta = validar_ruta_salida_segura(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(COLUMNAS_DETALLE))
        escritor.writeheader()
        for e in eventos:
            fila = {c: e.get(c, "") for c in COLUMNAS_DETALLE}
            fila["herramientas_solicitadas"] = ",".join(e["herramientas_solicitadas"])
            fila["mecanismo_que_bloqueo"] = e.get("mecanismo_que_bloqueo") or ""
            fila["motivo_uso_indebido"] = e.get("motivo_uso_indebido") or ""
            escritor.writerow(fila)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("jsonl", nargs="+", type=Path)
    parser.add_argument("--webhook", type=Path, default=None)
    parser.add_argument("--agregar-al-csv", action="store_true")
    parser.add_argument("--salida-md", type=Path, default=SALIDA_MD)
    args = parser.parse_args(argv)

    eventos = [e for ruta in args.jsonl for e in leer_jsonl(ruta)]
    recibidas = leer_jsonl(args.webhook) if args.webhook else None
    if args.agregar_al_csv:
        n = agregar_desde_jsonl(args.jsonl)
        escribir_detalle(eventos, DETALLE_CSV)
        print(f"{n} fila(s) de extension agregadas a resultados_template.csv.")
    destino = validar_ruta_salida_segura(args.salida_md)
    destino.write_text(generar_markdown(eventos, recibidas), encoding="utf-8")
    print(f"Resumen escrito en {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

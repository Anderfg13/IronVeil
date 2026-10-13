"""Exporta un lote de eventos de IronVeil al formato de un SIEM (Wazuh JSON o
CEF) usando `proxy.siem.exportar_a_siem()`.

Dos usos:

1. Exportar eventos reales del log del proxy (lectura; no modifica nunca la
   evidencia, regla 4 de CLAUDE.md):

       python analisis/exportar_lote_siem.py \\
           --entrada resultados/2026-10-02/eventos.jsonl \\
           --salida docs/siem/exportados/ironveil_wazuh.json

2. Generar un lote SINTETICO de prueba (`--ejemplo`) para verificar que un
   Wazuh local ingiere el formato, sin tocar ni mezclar datos del
   experimento. Son eventos inventados, marcados con
   `"sintetico": true`: no son evidencia y nunca deben consolidarse.

       python analisis/exportar_lote_siem.py --ejemplo \\
           --salida docs/siem/exportados/lote_prueba_wazuh.json

El archivo de salida es JSON Lines (un evento por linea), que es lo que lee
el `<localfile><log_format>json` de Wazuh. Se SOBREESCRIBE en cada corrida
(es un derivado reproducible, no evidencia). Una linea de la entrada que no
sea JSON valido o no tenga los 8 campos base se cuenta y se reporta, nunca
se adivina ni se completa.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from analisis.consolidar import validar_ruta_salida_segura  # noqa: E402
from proxy.siem import FORMATOS_SIEM, exportar_a_siem  # noqa: E402

LOGGER = logging.getLogger(__name__)

SALIDA_DEFECTO = RAIZ / "docs" / "siem" / "exportados" / "ironveil_wazuh.json"

_BASE_SINTETICA: dict[str, Any] = {
    "configuracion": "C6",
    "mecanismos_activos": [
        "filtrado",
        "delimitacion",
        "clasificacion",
        "minimo_privilegio",
        "aprobacion_humana",
    ],
    "modelo_destino": "rrhh-agente",
    "latencia_ms": 420,
    "sintetico": True,
}

# (timestamp, vector, resultado, mecanismo que bloqueo, extras)
_ESCENARIOS: tuple[tuple[str, str, str, str | None, dict[str, Any]], ...] = (
    ("2026-10-02T10:00:00-05:00", "V3-A", "bloqueado", "filtrado", {}),
    (
        "2026-10-02T10:00:05-05:00",
        "V3-F",
        "bloqueado",
        "clasificacion",
        {"latencia_clasificador_ms": 68},
    ),
    ("2026-10-02T10:00:10-05:00", "V2-B", "exitoso_para_atacante", None, {}),
    ("2026-10-02T10:00:15-05:00", "V1-A", "permitido_normal", None, {}),
    (
        "2026-10-02T10:00:20-05:00",
        "V7-A",
        "bloqueado",
        "aprobacion_humana",
        {"es_extension": True, "tiempo_revision_humana_ms": 4200},
    ),
    (
        "2026-10-02T10:00:25-05:00",
        "V7-D",
        "bloqueado",
        "aprobacion_humana",
        {"es_extension": True},
    ),
    (
        "2026-10-02T10:00:30-05:00",
        "V4-A-paso2",
        "bloqueado",
        "minimo_privilegio",
        {"paso_bloqueado": 2},
    ),
)


def eventos_de_ejemplo() -> list[dict[str, Any]]:
    """Lote sintetico: un evento por resultado posible, mas V7 y V4 paso 2."""
    return [
        {
            "timestamp": marca,
            **_BASE_SINTETICA,
            "vector_probado": vector,
            "resultado": resultado,
            "mecanismo_que_bloqueo": mecanismo,
            **extras,
        }
        for marca, vector, resultado, mecanismo, extras in _ESCENARIOS
    ]


def leer_eventos(ruta: Path) -> tuple[list[dict[str, Any]], int]:
    """(eventos validos como dict, lineas descartadas). No convierte nada:
    solo parsea; la validacion de campos base la hace `exportar_a_siem()`."""
    eventos: list[dict[str, Any]] = []
    invalidas = 0
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            try:
                evento = json.loads(linea)
            except json.JSONDecodeError:
                invalidas += 1
                continue
            if isinstance(evento, dict):
                eventos.append(evento)
            else:
                invalidas += 1
    return eventos, invalidas


def exportar_lote(
    eventos: list[dict[str, Any]], salida: Path, formato: str
) -> tuple[int, int]:
    """Escribe `eventos` convertidos en `salida` (sobreescribe). Devuelve
    (exportados, rechazados por `exportar_a_siem()`)."""
    salida = validar_ruta_salida_segura(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    exportados = 0
    rechazados = 0
    with salida.open("w", encoding="utf-8") as f:
        for evento in eventos:
            try:
                f.write(exportar_a_siem(evento, formato) + "\n")
            except ValueError as exc:
                rechazados += 1
                LOGGER.warning("evento rechazado: %s", exc)
                continue
            exportados += 1
    return exportados, rechazados


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    origen = parser.add_mutually_exclusive_group(required=True)
    origen.add_argument("--entrada", type=Path, help="JSONL del proxy a exportar")
    origen.add_argument(
        "--ejemplo", action="store_true", help="generar el lote sintetico de prueba"
    )
    parser.add_argument("--salida", type=Path, default=SALIDA_DEFECTO)
    parser.add_argument("--formato", choices=FORMATOS_SIEM, default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.ejemplo:
        eventos, invalidas = eventos_de_ejemplo(), 0
    else:
        entrada = validar_ruta_salida_segura(args.entrada)
        eventos, invalidas = leer_eventos(entrada)
    exportados, rechazados = exportar_lote(eventos, args.salida, args.formato)
    LOGGER.info(
        "Exportados %d eventos (%s) a %s; rechazados %d; lineas no JSON %d",
        exportados,
        args.formato,
        args.salida,
        rechazados,
        invalidas,
    )
    return 0 if exportados and not (rechazados or invalidas) else 1


if __name__ == "__main__":
    sys.exit(main())

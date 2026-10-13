"""Validacion estructural del formato exportado por `exportar_a_siem()`.

EXTENSION OPCIONAL (integracion SIEM), no parte del nucleo del experimento.

Toma eventos REALES del log del proxy (`resultados/<fecha>/eventos.jsonl`),
los convierte con `proxy.siem.exportar_a_siem()` y comprueba que cada salida
cumple lo que la documentacion oficial de Wazuh exige a un log JSON
(`<localfile>` con `log_format json`, decodificador JSON):

- una sola linea con UN objeto JSON valido (la referencia de `localfile` lo
  describe como "single-line JSON files");
- cada valor es escalar o un arreglo de escalares: el decodificador JSON
  extrae numeros, cadenas, booleanos, nulos, arreglos y objetos, pero **no
  soporta arreglos de objetos**; los objetos anidados se aplanan con punto;
- tiene la marca `integration` que usan las reglas propias de IronVeil.

Ademas comprueba dos propiedades que descubrio la validacion manual contra
un Wazuh 4.14.8 real (`wazuh-logtest`) y que el exportador debe respetar:
ningun valor `null` (Wazuh lo decodifica como la cadena "null") y ninguna
lista (se aplanan a cadena con comas). Este script NO sustituye la
validacion manual: automatiza la parte estructural para repetirla.

Uso:
    python analisis/validar_formato_siem.py \\
        resultados/2026-09-05/eventos.jsonl:17 resultados/2026-09-07/eventos.jsonl:2
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from analisis.consolidar import validar_ruta_salida_segura  # noqa: E402
from proxy.siem import CAMPOS_BASE, MARCA_INTEGRACION, exportar_a_siem  # noqa: E402

MUESTRA_DEFECTO: tuple[str, ...] = (
    "resultados/2026-09-05/eventos.jsonl:17",
    "resultados/2026-09-07/eventos.jsonl:2",
    "resultados/2026-09-13/eventos.jsonl:6",
    "resultados/2026-09-25/eventos.jsonl:22",
    "resultados/2026-09-05/eventos.jsonl:1",
)

# Campos base que el exportador puede omitir a proposito (valor null en el
# evento interno): ausente significa lo mismo que null.
CAMPOS_BASE_OPCIONALES = frozenset({"mecanismo_que_bloqueo", "vector_probado"})

_ESCALARES = (str, int, float, bool)


@dataclass
class Resultado:
    origen: str
    comprobaciones: dict[str, bool]

    @property
    def valido(self) -> bool:
        return all(self.comprobaciones.values())


def cargar_evento(especificacion: str) -> dict[str, Any]:
    """Lee la linea `N` (base 1) de `ruta:N`."""
    ruta_texto, _, numero = especificacion.rpartition(":")
    ruta = validar_ruta_salida_segura(Path(ruta_texto))
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    return json.loads(lineas[int(numero) - 1])


def validar_salida_json(evento: dict[str, Any], salida: str) -> dict[str, bool]:
    """Comprobaciones estructurales de la linea JSON exportada."""
    try:
        carga = json.loads(salida)
    except json.JSONDecodeError:
        return {"json_valido": False}
    es_objeto = isinstance(carga, dict)
    valores = list(carga.values()) if es_objeto else []
    return {
        "json_valido": True,
        "una_sola_linea": "\n" not in salida and "\r" not in salida,
        "objeto_en_la_raiz": es_objeto,
        "solo_escalares": all(isinstance(v, _ESCALARES) for v in valores),
        "sin_null": all(v is not None for v in valores),
        "marca_integration": (
            carga.get("integration") == MARCA_INTEGRACION if es_objeto else False
        ),
        "campos_base_presentes": es_objeto
        and all(
            campo in carga
            for campo in CAMPOS_BASE
            if campo not in CAMPOS_BASE_OPCIONALES or evento.get(campo) is not None
        ),
        "mismos_valores_que_el_evento": es_objeto
        and all(
            carga.get(k) == (",".join(v) if isinstance(v, list) else v)
            for k, v in evento.items()
            if v is not None
        ),
    }


def validar_salida_cef(salida: str) -> dict[str, bool]:
    """Cabecera CEF:0 con 7 campos antes de la extension, en una linea."""
    cabecera = salida.split("|", 7)
    return {
        "una_sola_linea": "\n" not in salida,
        "empieza_con_CEF_0": salida.startswith("CEF:0|"),
        "cabecera_de_7_campos": len(cabecera) == 8,
        "severidad_0_a_10": len(cabecera) == 8
        and cabecera[6].isdigit()
        and 0 <= int(cabecera[6]) <= 10,
    }


def validar_muestra(especificaciones: list[str]) -> list[Resultado]:
    """Convierte y valida cada evento en JSON y en CEF."""
    resultados: list[Resultado] = []
    for especificacion in especificaciones:
        evento = cargar_evento(especificacion)
        comprobaciones = {
            f"json.{k}": v
            for k, v in validar_salida_json(
                evento, exportar_a_siem(evento, "json")
            ).items()
        }
        comprobaciones |= {
            f"cef.{k}": v
            for k, v in validar_salida_cef(exportar_a_siem(evento, "cef")).items()
        }
        resultados.append(Resultado(especificacion, comprobaciones))
    return resultados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("eventos", nargs="*", default=list(MUESTRA_DEFECTO))
    args = parser.parse_args(argv)
    resultados = validar_muestra(args.eventos)
    for r in resultados:
        fallos = [k for k, ok in r.comprobaciones.items() if not ok]
        print(f"{'OK ' if r.valido else 'MAL'} {r.origen} {fallos or ''}")
    return 0 if all(r.valido for r in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())

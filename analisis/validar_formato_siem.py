"""Valida que `exportar_a_siem()` produzca un formato que Wazuh ingiere,
usando eventos REALES del log del proyecto (tarea de Fiquitiva, semana del
17 de octubre).

Toma una muestra de eventos de `resultados/*/eventos.jsonl` (el log que
escribe el propio proxy), procurando cubrir los 3 valores de `resultado`, y
verifica sobre cada salida las reglas de la documentacion oficial de Wazuh
(resumidas en docs/VALIDACION_SIEM.md):

  R1. Una sola linea (log_format "json": "single-line JSON files").
  R2. JSON valido que decodifica a un objeto.
  R3. Etiqueta de origen `@source` = "ironveil" y `timestamp` en raiz.
  R4. Los 8 campos base presentes bajo `ironveil.*` con el mismo valor.
  R5. Ningun array de objetos ("an array of objects is not supported").

Ademas comprueba que la version CEF sea de una linea y tenga las 7
secciones de cabecera. Solo reporta: no corrige ni modifica ningun dato
crudo (CLAUDE.md, regla 4).

Uso:
    python analisis/validar_formato_siem.py               # muestra de 5
    python analisis/validar_formato_siem.py --n 3 --salida analisis/muestra_siem.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from proxy.siem import (  # noqa: E402
    CAMPOS_BASE_REQUERIDOS,
    FUENTE_SIEM,
    FormateadorCEF,
    exportar_a_siem,
)

LOGGER = logging.getLogger("analisis.validar_formato_siem")
RESULTADOS_DIR = RAIZ / "resultados"
RESULTADOS_A_CUBRIR: tuple[str, ...] = (
    "bloqueado",
    "exitoso_para_atacante",
    "permitido_normal",
)
SECCIONES_CABECERA_CEF = 7


@dataclass
class ResultadoValidacion:
    evento: dict[str, Any]
    linea_wazuh: str
    linea_cef: str
    errores: list[str] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return not self.errores


def cargar_eventos_proxy(directorio: Path = RESULTADOS_DIR) -> list[dict[str, Any]]:
    """Lee todos los `eventos.jsonl` (log del proxy), en orden de fecha."""
    eventos: list[dict[str, Any]] = []
    for archivo in sorted(directorio.glob("*/eventos.jsonl")):
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                eventos.append(json.loads(linea))
    return eventos


def elegir_muestra(eventos: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Primero un evento por cada `resultado` posible, luego mas variedad de
    configuraciones hasta `n`. Determinista (sin aleatoriedad): la misma
    entrada da la misma muestra, para que la validacion sea reproducible."""
    muestra: list[dict[str, Any]] = []
    for resultado in RESULTADOS_A_CUBRIR:
        for e in eventos:
            if e.get("resultado") == resultado:
                muestra.append(e)
                break
    vistas = {e.get("configuracion") for e in muestra}
    for e in eventos:
        if len(muestra) >= n:
            break
        if e.get("configuracion") not in vistas:
            muestra.append(e)
            vistas.add(e.get("configuracion"))
    return muestra[:n]


def _tiene_array_de_objetos(valor: Any) -> bool:
    if isinstance(valor, list):
        return any(isinstance(v, dict) for v in valor) or any(
            _tiene_array_de_objetos(v) for v in valor
        )
    if isinstance(valor, dict):
        return any(_tiene_array_de_objetos(v) for v in valor.values())
    return False


def validar_evento(evento: dict[str, Any]) -> ResultadoValidacion:
    """Exporta `evento` a Wazuh JSON y CEF y aplica las reglas R1-R5."""
    linea = exportar_a_siem(evento)
    cef = FormateadorCEF().formatear(evento)
    res = ResultadoValidacion(evento, linea, cef)

    if "\n" in linea or "\r" in linea:
        res.errores.append("R1: la salida JSON ocupa mas de una linea")
    try:
        decodificado = json.loads(linea)
    except json.JSONDecodeError as exc:
        res.errores.append(f"R2: JSON invalido ({exc})")
        return res
    if not isinstance(decodificado, dict):
        res.errores.append("R2: el JSON no es un objeto")
        return res
    if decodificado.get("@source") != FUENTE_SIEM or "timestamp" not in decodificado:
        res.errores.append("R3: falta @source/timestamp en la raiz")
    anidado = decodificado.get(FUENTE_SIEM, {})
    for campo in CAMPOS_BASE_REQUERIDOS:
        if anidado.get(campo, object()) != evento.get(campo):
            res.errores.append(f"R4: ironveil.{campo} falta o cambio de valor")
    if _tiene_array_de_objetos(decodificado):
        res.errores.append("R5: contiene un array de objetos")

    if "\n" in cef or len(cef.split("|", SECCIONES_CABECERA_CEF)) != 8:
        res.errores.append("CEF: no es una linea con 7 secciones de cabecera")
    return res


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=5, help="Eventos a validar.")
    parser.add_argument(
        "--salida",
        type=Path,
        default=None,
        help="Si se da, escribe ahi las lineas Wazuh JSON de la muestra.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    muestra = elegir_muestra(cargar_eventos_proxy(), args.n)
    if not muestra:
        LOGGER.error("No hay eventos en %s/*/eventos.jsonl", RESULTADOS_DIR)
        return 1

    resultados = [validar_evento(e) for e in muestra]
    for r in resultados:
        LOGGER.info(
            "[%s] %s %s %s -> %s",
            "OK" if r.valido else "FALLA",
            r.evento.get("configuracion"),
            r.evento.get("vector_probado"),
            r.evento.get("resultado"),
            "; ".join(r.errores) or "R1-R5 y CEF correctos",
        )
        LOGGER.info("  wazuh: %s", r.linea_wazuh)
        LOGGER.info("  cef:   %s", r.linea_cef)

    if args.salida is not None:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(
            "".join(r.linea_wazuh + "\n" for r in resultados), encoding="utf-8"
        )

    validos = sum(r.valido for r in resultados)
    LOGGER.info("%d/%d eventos validos.", validos, len(resultados))
    return 0 if validos == len(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())

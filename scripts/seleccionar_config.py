"""Escribe `config.yaml` para una de las 7 configuraciones del experimento (C0..C6).

Uso (desde la raiz del repo):

    python scripts/seleccionar_config.py C3

El proxy relee `config.yaml` en cada peticion (esta montado de solo lectura en el
contenedor), asi que el cambio se aplica sin reconstruir ni reiniciar nada. La
correspondencia C0..C6 vive en `proxy/configuraciones.py` (una sola definicion).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from proxy.configuraciones import (  # noqa: E402
    CONFIGURACIONES,
    MECANISMOS,
    construir_config,
    descripcion_activos,
)

RUTA_CONFIG = RAIZ / "config.yaml"

__all__ = ["CONFIGURACIONES", "MECANISMOS", "construir_config", "main"]


def main(argv: list[str] | None = None) -> int:
    """Escribe `config.yaml` (o `--salida`) con la configuracion pedida."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("configuracion", choices=sorted(CONFIGURACIONES))
    parser.add_argument("--salida", type=Path, default=RUTA_CONFIG)
    args = parser.parse_args(argv)
    args.salida.write_text(construir_config(args.configuracion), encoding="utf-8")
    activos = descripcion_activos(args.configuracion)
    print(f"{args.salida.name}: {args.configuracion} -> mecanismos activos: {activos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
    escribir_config,
)

RUTA_CONFIG = RAIZ / "config.yaml"

__all__ = [
    "CONFIGURACIONES",
    "MECANISMOS",
    "construir_config",
    "escribir_config",
    "main",
]


def main(argv: list[str] | None = None) -> int:
    """Escribe el `config.yaml` de la raiz del repo con la configuracion pedida."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("configuracion", choices=sorted(CONFIGURACIONES))
    args = parser.parse_args(argv)
    escribir_config(RUTA_CONFIG, args.configuracion)
    activos = descripcion_activos(args.configuracion)
    print(f"{RUTA_CONFIG.name}: {args.configuracion} -> mecanismos activos: {activos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

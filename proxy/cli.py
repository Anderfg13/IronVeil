"""Linea de comandos `ironveil` (instalacion con `pip install ironveil`).

    ironveil config C3          escribe ./config.yaml (directorio actual) con C3
    ironveil serve              levanta el proxy en :8000 (lee ./config.yaml)
    ironveil auth-demo          crea la cuenta de demo "admin" (clave aleatoria)

Instalado como paquete, el proxy no debe escribir dentro de `site-packages`: por
defecto lee `./config.yaml` y deja los resultados en `./resultados` (del directorio
actual), salvo que `IRONVEIL_CONFIG` o `IRONVEIL_RESULTADOS` ya lo digan.
Ollama debe estar accesible en `OLLAMA_BASE_URL` (por defecto http://localhost:11434);
el laboratorio completo con Docker esta en el README.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from proxy.configuraciones import (
    CONFIGURACIONES,
    descripcion_activos,
    escribir_config,
)

NOMBRE_CONFIG = "config.yaml"
NOMBRE_RESULTADOS = "resultados"
PUERTO_DEFECTO = 8000
HOST_DEFECTO = "127.0.0.1"


def _comando_config(args: argparse.Namespace) -> int:
    destino = Path.cwd() / NOMBRE_CONFIG
    escribir_config(destino, args.configuracion)
    activos = descripcion_activos(args.configuracion)
    sys.stdout.write(f"{destino}: {args.configuracion} -> {activos}\n")
    return 0


def _comando_serve(args: argparse.Namespace) -> int:
    config = Path(os.environ.get("IRONVEIL_CONFIG") or Path.cwd() / NOMBRE_CONFIG)
    if not config.is_file():
        sys.stderr.write(
            f"No existe {config}. Crea una con: ironveil config C0 (o C1..C6).\n"
        )
        return 2
    os.environ.setdefault("IRONVEIL_CONFIG", str(config))
    os.environ.setdefault("IRONVEIL_RESULTADOS", str(Path.cwd() / NOMBRE_RESULTADOS))
    import uvicorn  # se importa aqui: el resto de comandos no lo necesita

    uvicorn.run("proxy.main:app", host=args.host, port=args.puerto, server_header=False)
    return 0


def _comando_auth_demo(_: argparse.Namespace) -> int:
    from proxy import auth

    return auth.cli(["--demo"])


def construir_parser() -> argparse.ArgumentParser:
    """Parser de `ironveil` con sus tres subcomandos."""
    parser = argparse.ArgumentParser(
        prog="ironveil", description="IronVeil: defensa en profundidad para LLMs"
    )
    sub = parser.add_subparsers(dest="comando", required=True)
    cfg = sub.add_parser("config", help="escribe config.yaml para C0..C6")
    cfg.add_argument("configuracion", choices=sorted(CONFIGURACIONES))
    cfg.set_defaults(funcion=_comando_config)
    srv = sub.add_parser("serve", help="levanta el proxy")
    srv.add_argument("--host", default=HOST_DEFECTO)
    srv.add_argument("--puerto", type=int, default=PUERTO_DEFECTO)
    srv.set_defaults(funcion=_comando_serve)
    demo = sub.add_parser("auth-demo", help="crea la cuenta de demo (clave aleatoria)")
    demo.set_defaults(funcion=_comando_auth_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada del comando `ironveil`."""
    args = construir_parser().parse_args(argv)
    return int(args.funcion(args))


if __name__ == "__main__":
    raise SystemExit(main())

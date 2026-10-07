"""Escribe `config.yaml` para una de las 7 configuraciones del experimento (C0..C6).

Uso (desde la raiz del repo):

    python scripts/seleccionar_config.py C3

El proxy relee `config.yaml` en cada peticion (esta montado de solo lectura en el
contenedor), asi que el cambio se aplica sin reconstruir ni reiniciar nada.
"""

from __future__ import annotations

import argparse
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CONFIG = RAIZ / "config.yaml"

MECANISMOS: tuple[str, ...] = (
    "filtrado",
    "delimitacion",
    "clasificacion",
    "minimo_privilegio",
    "aprobacion_humana",
)

# C0 = nada; C1..C5 = el mecanismo n-esimo solo; C6 = los cinco.
CONFIGURACIONES: dict[str, tuple[str, ...]] = {
    "C0": (),
    **{f"C{i}": (m,) for i, m in enumerate(MECANISMOS, start=1)},
    "C6": MECANISMOS,
}

ENCABEZADO = (
    "# Banderas de los 5 mecanismos defensivos de IronVeil.\n"
    "# Escrito por scripts/seleccionar_config.py (configuracion {nombre}).\n"
    "# Todas en false = configuracion C0 (baseline, passthrough puro).\n"
)


def construir_config(nombre: str) -> str:
    """Devuelve el texto de `config.yaml` de la configuracion `nombre` (C0..C6)."""
    if nombre not in CONFIGURACIONES:
        validas = ", ".join(CONFIGURACIONES)
        raise ValueError(f"Configuracion desconocida {nombre!r}; validas: {validas}")
    activas = CONFIGURACIONES[nombre]
    lineas = [f"{m}: {'true' if m in activas else 'false'}" for m in MECANISMOS]
    return ENCABEZADO.format(nombre=nombre) + "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Escribe `config.yaml` (o `--salida`) con la configuracion pedida."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("configuracion", choices=sorted(CONFIGURACIONES))
    parser.add_argument("--salida", type=Path, default=RUTA_CONFIG)
    args = parser.parse_args(argv)
    args.salida.write_text(construir_config(args.configuracion), encoding="utf-8")
    activas = ", ".join(CONFIGURACIONES[args.configuracion]) or "ninguno (baseline)"
    print(f"{args.salida.name}: {args.configuracion} -> mecanismos activos: {activas}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Las 7 configuraciones del experimento (C0..C6) y su `config.yaml`.

Es la unica definicion de la correspondencia C0..C6 <-> banderas: la usan el script
`scripts/seleccionar_config.py` y `ironveil config`. Solo biblioteca estandar.
"""

from __future__ import annotations

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
    "# Escrito por IronVeil (configuracion {nombre}).\n"
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


def descripcion_activos(nombre: str) -> str:
    """Los mecanismos activos de `nombre`, para mostrarlos en una linea."""
    return ", ".join(CONFIGURACIONES[nombre]) or "ninguno (baseline)"

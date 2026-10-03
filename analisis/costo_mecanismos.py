"""Costo retrospectivo de implementación por mecanismo: líneas de código y
horas estimadas, para la columna "Costo" de la tabla maestra
(`analisis/tabla_maestra.py`).

Uso:
    python analisis/costo_mecanismos.py

No corre `cloc` ni `git` en cada ejecución -- los conteos de líneas y las
horas son **constantes documentadas**, calculadas una sola vez siguiendo la
metodología de `analisis/metodologia_costo_mecanismos.md` (ese documento
trae la receta exacta: qué rangos de línea de qué archivo, con qué comando
de `sed`/`cloc`, para que cualquiera pueda reproducir el mismo número a
mano). Tratar esto como medición retrospectiva de una sola vez, no como un
análisis que deba rehacerse cada semana -- el código de los 5 mecanismos ya
está cerrado (CLAUDE.md: "esta semana no se agrega funcionalidad nueva").

**Regla de "líneas de código" (una sola, aplicada igual a los 5
mecanismos):** líneas de CÓDIGO según `cloc` -- excluye líneas en blanco y
líneas que son puramente comentario/docstring. Cuenta, para cada mecanismo:
la(s) función(es) principal(es) en `proxy/mecanismos.py` (y todo
`proxy/cola.py` para aprobación humana, que es su propio módulo), el
fragmento específico del endpoint `/chat` en `proxy/main.py`, y sus pruebas
unitarias/de integración propias (archivo de test dedicado +
tests de un solo mecanismo en `tests/test_main.py`). **Excluido de los 5
conteos, a propósito:** infraestructura compartida que no pertenece a
ningún mecanismo en particular (imports, `cargar_config()`,
`_ejecutar_cadena()`, `_CADENA_MECANISMOS`, `chat()` como orquestador, los
tests `test_integracion_*`/`test_c6_*` que combinan varios mecanismos a la
vez -- atribuir uno de esos a un solo mecanismo sería arbitrario).

**Horas estimadas:** el historial de Git de este proyecto no permite medir
horas reales de forma confiable -- cada mecanismo se comiteó como 1-4
commits atómicos (un commit por sesión de trabajo terminada), sin un
patrón de commits intermedios que permita inferir un lapso de sesión real
(ver `git log` citado en la metodología). Ante esa limitación, las horas
aquí son una ESTIMACIÓN basada en un proxy objetivo y documentado (líneas
de código totales ÷ una tasa fija de líneas/hora para código probado y
documentado, 12 líneas/hora -- cifra dentro del rango 10-15 líneas/hora
citado en la literatura de estimación de software para este tipo de
trabajo), con un ajuste cualitativo hacia arriba cuando hay evidencia real
documentada de retrabajo/depuración extra (ver
`docs/FUENTE_DE_VERDAD.md`): clasificación (bug real de etiqueta
`LABEL_1` encontrado solo al validar contra el modelo real) y aprobación
humana (condición de carrera real encontrada y corregida en
`_registrar_evento()`). **Esto NO es un recuerdo personal de horas
trabajadas** (el equipo no llevó un registro de tiempo semana a semana) --
es una estimación reproducible, documentada como tal, no una medición
precisa.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analisis.consolidar import validar_ruta_salida_segura  # noqa: E402

# Nombre canonico de mecanismo (identico a proxy/mecanismos.FLAGS_REQUERIDAS
# y a config.yaml) -> (lineas_codigo_produccion, lineas_codigo_tests,
# horas_estimadas, complejidad, justificacion). Mismos nombres que usa
# `analisis/tabla_maestra.py` para que ambas tablas sean compatibles sin
# traducir nada.
COSTO_POR_MECANISMO: dict[str, dict[str, object]] = {
    "filtrado": {
        "lineas_produccion": 63,
        "lineas_tests": 185,
        "horas": 21,
        "complejidad": "Media",
        "justificacion": (
            "Regex local, pero cubre 5 conceptos x 2 idiomas + 7 formatos de "
            "clave de proveedor, mantenido en 4 commits distintos a lo largo "
            "de 3 semanas (ver metodología)."
        ),
    },
    "delimitacion": {
        "lineas_produccion": 31,
        "lineas_tests": 150,
        "horas": 15,
        "complejidad": "Baja",
        "justificacion": (
            "Función pura, sin estado ni red; la única complejidad real fue "
            "el token aleatorio por petición agregado después."
        ),
    },
    "clasificacion": {
        "lineas_produccion": 99,
        "lineas_tests": 210,
        "horas": 34,
        "complejidad": "Alta",
        "justificacion": (
            "Integra 2 modelos externos distintos por dirección (Llama Guard "
            "vía Ollama, Prompt Guard vía Hugging Face); bug real de "
            "etiqueta (LABEL_1) encontrado solo al validar contra el modelo "
            "real."
        ),
    },
    "minimo_privilegio": {
        "lineas_produccion": 17,
        "lineas_tests": 150,
        "horas": 14,
        "complejidad": "Baja",
        "justificacion": (
            "Regex de dominio simple, sin estado compartido; reutiliza el "
            "mismo patrón de credencial que filtrado."
        ),
    },
    "aprobacion_humana": {
        "lineas_produccion": 197,
        "lineas_tests": 497,
        "horas": 69,
        "complejidad": "Alta",
        "justificacion": (
            "Único mecanismo con estado compartido entre peticiones "
            "concurrentes (cola + 2 rate limiters) y su propia interfaz "
            "HTTP; condición de carrera real encontrada y corregida en "
            "_registrar_evento()."
        ),
    },
}

# Mismo orden que CLAUDE.md seccion 1 y proxy.mecanismos.FLAGS_REQUERIDAS.
ORDEN_MECANISMOS = (
    "filtrado",
    "delimitacion",
    "clasificacion",
    "minimo_privilegio",
    "aprobacion_humana",
)


def tabla_costo_por_mecanismo() -> pd.DataFrame:
    """Una fila por mecanismo: líneas de código (prod/tests/total), horas
    estimadas, complejidad relativa y justificación.
    """
    filas = []
    for nombre in ORDEN_MECANISMOS:
        datos = COSTO_POR_MECANISMO[nombre]
        filas.append(
            {
                "Mecanismo": nombre,
                "Líneas de código (producción)": datos["lineas_produccion"],
                "Líneas de código (tests)": datos["lineas_tests"],
                "Líneas de código (total)": (
                    datos["lineas_produccion"] + datos["lineas_tests"]
                ),
                "Horas estimadas": datos["horas"],
                "Complejidad relativa": datos["complejidad"],
                "Justificación": datos["justificacion"],
            }
        )
    return pd.DataFrame(filas)


def costo_por_configuracion(mecanismos_activos: set[str]) -> tuple[int, int]:
    """Suma (líneas de código total, horas estimadas) de los mecanismos
    activos en una configuración -- usado por `analisis/tabla_maestra.py`
    para la columna "Costo" de C0..C6 (suma de los mecanismos que esa
    configuración tiene en `true`; C0 da (0, 0)).
    """
    lineas = 0
    horas = 0
    for nombre in mecanismos_activos:
        datos = COSTO_POR_MECANISMO.get(nombre)
        if datos is None:
            raise ValueError(f"Mecanismo desconocido: {nombre!r}")
        lineas += datos["lineas_produccion"] + datos["lineas_tests"]
        horas += datos["horas"]
    return lineas, horas


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera la tabla de costo por mecanismo (CSV y Markdown)."
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).resolve().parent
    )
    parser.add_argument("--nombre-base", default="costo_mecanismos")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tabla = tabla_costo_por_mecanismo()

    output_dir = validar_ruta_salida_segura(args.output_dir, base=_REPO_ROOT)
    output_dir.mkdir(parents=True, exist_ok=True)

    ruta_csv = output_dir / f"{args.nombre_base}.csv"
    ruta_md = output_dir / f"{args.nombre_base}.md"
    tabla.to_csv(ruta_csv, index=False)
    ruta_md.write_text(tabla.to_markdown(index=False), encoding="utf-8")

    print(f"Tabla de costo escrita en {ruta_csv} y {ruta_md}")
    print(tabla.to_markdown(index=False))


if __name__ == "__main__":
    main()

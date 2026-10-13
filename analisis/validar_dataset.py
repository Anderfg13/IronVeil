"""Valida resultados_template.csv contra el esquema de la skill esquema-log.

Uso:
    python analisis/validar_dataset.py
    python analisis/validar_dataset.py --csv resultados/resultados_template.csv

Este script SOLO REPORTA -- nunca corrige nada por su cuenta. Cada hallazgo
lo decide una persona (ver docs/LIMPIEZA_DATOS.md para las correcciones ya
aplicadas esta semana con `analisis/limpiar_dataset.py`, y la lista de
hallazgos que quedan abiertos para confirmar con Sabogal). Pensado para
volver a correrse sin cambios cuando se agreguen los resultados de la
extension opcional del 17 de octubre (regla 4 de CLAUDE.md: no asume que
el dataset tiene un tamano o un conjunto de configuraciones fijo).

Categorias de hallazgo:
    1. Campos vacios que no deberian estarlo (los 8 campos base nunca
       vacios; campos extendidos vacios de forma sistematica en un
       mecanismo activo se reportan como "info", no "error" -- pueden ser
       una limitacion conocida, no un dato faltante por accidente).
    2. Nombres de configuracion o de mecanismo con variantes de
       mayuscula/espacios, o fuera del conjunto canonico.
    3. Timestamps no parseables, sin offset de zona, o fuera de orden.
    4. Las 5 invariantes del esquema de log (ver skill esquema-log).
    5. Filas duplicadas exactas.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CSV_DEFECTO = RAIZ / "resultados" / "resultados_template.csv"

# Mismos nombres/orden que proxy.mecanismos.FLAGS_REQUERIDAS. Se repiten
# aqui (no se importa proxy/, igual que analisis/costo_mecanismos.py) para
# que este modulo de analisis no dependa del paquete de runtime del proxy.
MECANISMOS_CANONICOS: tuple[str, ...] = (
    "filtrado",
    "delimitacion",
    "clasificacion",
    "minimo_privilegio",
    "aprobacion_humana",
)

# Mismos valores que ataques.vector5_carga.CONFIGURACIONES_VALIDAS.
CONFIGURACIONES_CANONICAS: tuple[str, ...] = ("C0", "C1", "C2", "C3", "C4", "C5", "C6")

# Invariante 4 del esquema de log: que mecanismos espera cada configuracion
# exactamente (ni de mas ni de menos).
MECANISMOS_ESPERADOS_POR_CONFIG: dict[str, frozenset[str]] = {
    "C0": frozenset(),
    "C1": frozenset({"filtrado"}),
    "C2": frozenset({"delimitacion"}),
    "C3": frozenset({"clasificacion"}),
    "C4": frozenset({"minimo_privilegio"}),
    "C5": frozenset({"aprobacion_humana"}),
    "C6": frozenset(MECANISMOS_CANONICOS),
}

RESULTADOS_VALIDOS = frozenset(
    {"bloqueado", "exitoso_para_atacante", "permitido_normal"}
)
CAMPOS_BASE = (
    "timestamp",
    "configuracion",
    "vector_probado",
    "modelo_destino",
    "resultado",
    "latencia_ms",
)

# modelo_destino fuera de {soporte, rrhh} es valido a proposito para V1
# (reconocimiento): no llama a ningun modelo real ("proxy") o prueba
# deliberadamente un nombre inexistente ("noexiste"). Documentado en
# docs/LIMPIEZA_DATOS.md -- no es un hallazgo para esos vectores.
MODELOS_VALIDOS = frozenset({"soporte", "rrhh"})
# Las filas de la extension opcional (es_extension == "True") pueden apuntar
# ademas al modelo con herramientas simuladas.
MODELOS_VALIDOS_EXTENSION = frozenset({"rrhh-agente"})
PATRON_VECTOR_V1 = re.compile(r"^V1-")

PATRON_CONFIGURACION_CANONICA = re.compile(r"^C[0-6]$")


@dataclass
class Hallazgo:
    categoria: str
    severidad: str  # "error" | "advertencia" | "info"
    filas_afectadas: int
    descripcion: str
    indices_ejemplo: list[int] = field(default_factory=list)

    def __str__(self) -> str:
        ejemplos = (
            f" (filas CSV ejemplo: {self.indices_ejemplo})"
            if self.indices_ejemplo
            else ""
        )
        return (
            f"[{self.severidad.upper()}] {self.categoria}: {self.descripcion}{ejemplos}"
        )


def _indices_ejemplo(mascara: pd.Series, limite: int = 5) -> list[int]:
    """Primeros `limite` indices (base 0, como filas de datos sin encabezado)
    donde `mascara` es True -- para que quien revise el hallazgo pueda ir
    directo a esas filas sin tener que re-filtrar el CSV completo.
    """
    return [int(i) for i in mascara[mascara].index[:limite]]


def cargar_dataset(ruta_csv: Path) -> pd.DataFrame:
    """Lee resultados_template.csv como texto puro (sin inferir tipos ni
    NaN): este dataset usa "" como unico valor vacio, nunca NaN, y una
    columna como `configuracion` nunca debe convertirse a otro tipo.
    """
    if not ruta_csv.exists():
        raise FileNotFoundError(f"No existe el CSV de resultados: {ruta_csv}")
    return pd.read_csv(ruta_csv, dtype=str, keep_default_na=False)


def verificar_columnas_requeridas(df: pd.DataFrame) -> list[Hallazgo]:
    faltantes = [c for c in CAMPOS_BASE if c not in df.columns]
    if not faltantes:
        return []
    return [
        Hallazgo(
            categoria="columnas_requeridas",
            severidad="error",
            filas_afectadas=len(df),
            descripcion=f"Faltan columnas base del esquema: {faltantes}.",
        )
    ]


def verificar_campos_base_vacios(df: pd.DataFrame) -> list[Hallazgo]:
    """Categoria 1 de la tarea: campos que nunca deberian estar vacios."""
    hallazgos = []
    for campo in CAMPOS_BASE:
        if campo not in df.columns:
            continue
        vacios = df[campo] == ""
        if vacios.any():
            hallazgos.append(
                Hallazgo(
                    categoria="campo_base_vacio",
                    severidad="error",
                    filas_afectadas=int(vacios.sum()),
                    descripcion=f"Campo base '{campo}' vacio.",
                    indices_ejemplo=_indices_ejemplo(vacios),
                )
            )

    if "mecanismos_activos" in df.columns:
        # Vacio solo es valido en C0 (ningun mecanismo activo, invariante 4).
        vacio_fuera_de_c0 = (df["mecanismos_activos"] == "") & (
            df["configuracion"] != "C0"
        )
        if vacio_fuera_de_c0.any():
            hallazgos.append(
                Hallazgo(
                    categoria="campo_base_vacio",
                    severidad="error",
                    filas_afectadas=int(vacio_fuera_de_c0.sum()),
                    descripcion=(
                        "'mecanismos_activos' vacio fuera de C0 (deberia "
                        "listar al menos un mecanismo)."
                    ),
                    indices_ejemplo=_indices_ejemplo(vacio_fuera_de_c0),
                )
            )
    return hallazgos


def verificar_nombres_configuracion(df: pd.DataFrame) -> list[Hallazgo]:
    """Categoria 2: variantes de mayuscula/espacios o valores fuera de
    C0..C6 (p. ej. "c1", "C1 ", "C 1").
    """
    invalida = ~df["configuracion"].str.match(PATRON_CONFIGURACION_CANONICA)
    if not invalida.any():
        return []
    valores = sorted(df.loc[invalida, "configuracion"].unique())
    return [
        Hallazgo(
            categoria="nombre_configuracion_invalido",
            severidad="error",
            filas_afectadas=int(invalida.sum()),
            descripcion=(
                f"'configuracion' con valores fuera de {CONFIGURACIONES_CANONICAS} "
                f"(variantes encontradas: {valores})."
            ),
            indices_ejemplo=_indices_ejemplo(invalida),
        )
    ]


def verificar_nombres_mecanismo(df: pd.DataFrame) -> list[Hallazgo]:
    """Categoria 2, version mecanismo: nombres no canonicos en
    'mecanismos_activos' o en 'mecanismo_que_bloqueo'.
    """
    hallazgos = []
    canonicos = set(MECANISMOS_CANONICOS)

    def _no_canonicos(lista_csv: str) -> set[str]:
        return {m for m in lista_csv.split(",") if m} - canonicos

    extras = df["mecanismos_activos"].apply(_no_canonicos)
    con_extras = extras.apply(bool)
    if con_extras.any():
        valores = sorted({v for s in extras[con_extras] for v in s})
        hallazgos.append(
            Hallazgo(
                categoria="nombre_mecanismo_invalido",
                severidad="error",
                filas_afectadas=int(con_extras.sum()),
                descripcion=(
                    f"'mecanismos_activos' con nombres no canonicos: {valores}."
                ),
                indices_ejemplo=_indices_ejemplo(con_extras),
            )
        )

    bloqueo_no_vacio = df["mecanismo_que_bloqueo"] != ""
    bloqueo_no_canonico = bloqueo_no_vacio & ~df["mecanismo_que_bloqueo"].isin(
        canonicos
    )
    if bloqueo_no_canonico.any():
        valores = sorted(df.loc[bloqueo_no_canonico, "mecanismo_que_bloqueo"].unique())
        hallazgos.append(
            Hallazgo(
                categoria="nombre_mecanismo_invalido",
                severidad="error",
                filas_afectadas=int(bloqueo_no_canonico.sum()),
                descripcion=(
                    f"'mecanismo_que_bloqueo' con valores no canonicos: {valores}."
                ),
                indices_ejemplo=_indices_ejemplo(bloqueo_no_canonico),
            )
        )
    return hallazgos


def _parsear_timestamp_con_offset(valor: str) -> pd.Timestamp | None:
    """None si `valor` no es parseable como ISO 8601 O si es parseable pero
    sin offset de zona explicito -- a diferencia de
    `pd.to_datetime(..., utc=True)`, que asume UTC en silencio para un
    datetime naive en vez de rechazarlo (la skill esquema-log exige offset
    explicito, nunca un datetime naive).
    """
    try:
        dt = datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        return None
    if dt.utcoffset() is None:
        return None
    return pd.Timestamp(dt)


def verificar_timestamps(df: pd.DataFrame) -> list[Hallazgo]:
    """Categoria 3: timestamps no parseables, sin offset, o fuera de orden
    global (advertencia -- una fila fuera de orden no es necesariamente un
    error si mezcla corridas concurrentes, pero vale la pena revisarla).
    """
    hallazgos = []
    # apply() da una Serie de objetos (Timestamp tz-aware o None); se pasa
    # por to_datetime() para que quede en dtype datetime64 real y admita
    # .dt.diff() mas abajo -- los None ya son Timestamp-o-nada, nunca naive,
    # asi que to_datetime() no reinterpreta nada en UTC por su cuenta aqui.
    parseado = pd.to_datetime(
        df["timestamp"].apply(_parsear_timestamp_con_offset), utc=True
    )
    no_parseable = parseado.isna()
    if no_parseable.any():
        hallazgos.append(
            Hallazgo(
                categoria="timestamp_invalido",
                severidad="error",
                filas_afectadas=int(no_parseable.sum()),
                descripcion=(
                    "'timestamp' no parseable como ISO 8601 o sin offset de "
                    "zona explicito."
                ),
                indices_ejemplo=_indices_ejemplo(no_parseable),
            )
        )

    validos = parseado.dropna()
    retrocede = validos.diff().dt.total_seconds() < 0
    if retrocede.any():
        hallazgos.append(
            Hallazgo(
                categoria="timestamp_desordenado",
                severidad="advertencia",
                filas_afectadas=int(retrocede.sum()),
                descripcion=(
                    "'timestamp' retrocede respecto a la fila anterior del "
                    "CSV (posible mezcla de corridas fuera de orden o reloj "
                    "desincronizado entre maquinas)."
                ),
                indices_ejemplo=_indices_ejemplo(retrocede),
            )
        )

    return hallazgos


def verificar_resultado_dominio(df: pd.DataFrame) -> list[Hallazgo]:
    invalido = ~df["resultado"].isin(RESULTADOS_VALIDOS)
    if not invalido.any():
        return []
    valores = sorted(df.loc[invalido, "resultado"].unique())
    return [
        Hallazgo(
            categoria="resultado_fuera_de_dominio",
            severidad="error",
            filas_afectadas=int(invalido.sum()),
            descripcion=(
                f"'resultado' con valores fuera de {sorted(RESULTADOS_VALIDOS)}: "
                f"{valores}."
            ),
            indices_ejemplo=_indices_ejemplo(invalido),
        )
    ]


def verificar_invariante_resultado_mecanismo(df: pd.DataFrame) -> list[Hallazgo]:
    """Invariante 1: resultado == "bloqueado" <=> mecanismo_que_bloqueo != ""."""
    bloqueado_sin_mecanismo = (df["resultado"] == "bloqueado") & (
        df["mecanismo_que_bloqueo"] == ""
    )
    no_bloqueado_con_mecanismo = (df["resultado"] != "bloqueado") & (
        df["mecanismo_que_bloqueo"] != ""
    )
    hallazgos = []
    if bloqueado_sin_mecanismo.any():
        hallazgos.append(
            Hallazgo(
                categoria="invariante_resultado_mecanismo",
                severidad="error",
                filas_afectadas=int(bloqueado_sin_mecanismo.sum()),
                descripcion="resultado='bloqueado' pero mecanismo_que_bloqueo vacio.",
                indices_ejemplo=_indices_ejemplo(bloqueado_sin_mecanismo),
            )
        )
    if no_bloqueado_con_mecanismo.any():
        hallazgos.append(
            Hallazgo(
                categoria="invariante_resultado_mecanismo",
                severidad="error",
                filas_afectadas=int(no_bloqueado_con_mecanismo.sum()),
                descripcion=(
                    "resultado != 'bloqueado' pero mecanismo_que_bloqueo no "
                    "esta vacio."
                ),
                indices_ejemplo=_indices_ejemplo(no_bloqueado_con_mecanismo),
            )
        )
    return hallazgos


def verificar_invariante_mecanismo_activo(df: pd.DataFrame) -> list[Hallazgo]:
    """Invariante 2: mecanismo_que_bloqueo, si no es vacio, debe estar en
    mecanismos_activos de esa misma fila (un mecanismo apagado no pudo
    haber bloqueado nada).
    """

    def _no_esta_activo(fila: pd.Series) -> bool:
        mb = fila["mecanismo_que_bloqueo"]
        if mb == "":
            return False
        activos = {m for m in fila["mecanismos_activos"].split(",") if m}
        return mb not in activos

    mascara = df.apply(_no_esta_activo, axis=1)
    if not mascara.any():
        return []
    return [
        Hallazgo(
            categoria="invariante_mecanismo_activo",
            severidad="error",
            filas_afectadas=int(mascara.sum()),
            descripcion=(
                "mecanismo_que_bloqueo no esta dentro de mecanismos_activos "
                "de la misma fila (un mecanismo apagado no puede bloquear)."
            ),
            indices_ejemplo=_indices_ejemplo(mascara),
        )
    ]


def verificar_invariante_configuracion_mecanismos(df: pd.DataFrame) -> list[Hallazgo]:
    """Invariante 4: cada configuracion trae exactamente el set de
    mecanismos que le corresponde (ni de mas ni de menos).
    """

    def _set_inesperado(fila: pd.Series) -> bool:
        esperado = MECANISMOS_ESPERADOS_POR_CONFIG.get(fila["configuracion"])
        if esperado is None:
            return False  # ya reportado por verificar_nombres_configuracion
        activos = frozenset(m for m in fila["mecanismos_activos"].split(",") if m)
        return activos != esperado

    mascara = df.apply(_set_inesperado, axis=1)
    if not mascara.any():
        return []
    return [
        Hallazgo(
            categoria="invariante_configuracion_mecanismos",
            severidad="error",
            filas_afectadas=int(mascara.sum()),
            descripcion=(
                "'mecanismos_activos' no coincide con el set esperado para "
                "su 'configuracion' (ver MECANISMOS_ESPERADOS_POR_CONFIG)."
            ),
            indices_ejemplo=_indices_ejemplo(mascara),
        )
    ]


def verificar_modelo_destino_dominio(df: pd.DataFrame) -> list[Hallazgo]:
    """modelo_destino fuera de {soporte, rrhh} es un error, salvo en V1
    (reconocimiento), donde "proxy"/"noexiste" son valores esperados por
    diseno (ver docs/LIMPIEZA_DATOS.md).
    """
    es_v1 = df["vector_probado"].str.match(PATRON_VECTOR_V1)
    es_extension = (
        df["es_extension"].str.lower().eq("true")
        if "es_extension" in df.columns
        else pd.Series(False, index=df.index)
    )
    valido_extension = es_extension & df["modelo_destino"].isin(
        MODELOS_VALIDOS_EXTENSION
    )
    invalido = ~df["modelo_destino"].isin(MODELOS_VALIDOS) & ~es_v1 & ~valido_extension
    if not invalido.any():
        return []
    valores = sorted(df.loc[invalido, "modelo_destino"].unique())
    return [
        Hallazgo(
            categoria="modelo_destino_fuera_de_dominio",
            severidad="error",
            filas_afectadas=int(invalido.sum()),
            descripcion=(
                f"'modelo_destino' fuera de {sorted(MODELOS_VALIDOS)} en un "
                f"vector que no es V1: {valores}."
            ),
            indices_ejemplo=_indices_ejemplo(invalido),
        )
    ]


def verificar_filas_duplicadas(df: pd.DataFrame) -> list[Hallazgo]:
    duplicada = df.duplicated(keep=False)
    if not duplicada.any():
        return []
    return [
        Hallazgo(
            categoria="fila_duplicada_exacta",
            severidad="advertencia",
            filas_afectadas=int(duplicada.sum()),
            descripcion=(
                "Filas identicas en las 14 columnas (probable reingesta "
                "duplicada del mismo evento jsonl)."
            ),
            indices_ejemplo=_indices_ejemplo(duplicada),
        )
    ]


def verificar_cobertura_campos_extendidos(df: pd.DataFrame) -> list[Hallazgo]:
    """No son errores: son hallazgos 'info' sobre que tan completos estan
    los campos extendidos, para que el equipo decida si vale la pena
    cerrarlos (ver docs/LIMPIEZA_DATOS.md, seccion de hallazgos abiertos).
    """
    hallazgos = []

    if "latencia_clasificador_ms" in df.columns:
        clasificacion_activa = df["mecanismos_activos"].str.contains("clasificacion")
        sin_latencia = clasificacion_activa & (df["latencia_clasificador_ms"] == "")
        if sin_latencia.any():
            hallazgos.append(
                Hallazgo(
                    categoria="campo_extendido_incompleto",
                    severidad="info",
                    filas_afectadas=int(sin_latencia.sum()),
                    descripcion=(
                        f"'latencia_clasificador_ms' vacio en "
                        f"{int(sin_latencia.sum())} de "
                        f"{int(clasificacion_activa.sum())} filas con "
                        "'clasificacion' activa -- la mayoria son V5-D "
                        "(irrecuperable, el proxy nunca midio esto durante "
                        "las rafagas de carga); ver docs/LIMPIEZA_DATOS.md y "
                        "analisis/fusionar_latencia_clasificador.py."
                    ),
                )
            )

    if "tiempo_revision_humana_ms" in df.columns:
        aprobacion_activa = df["mecanismos_activos"].str.contains("aprobacion_humana")
        sin_tiempo = aprobacion_activa & (df["tiempo_revision_humana_ms"] == "")
        if sin_tiempo.any():
            hallazgos.append(
                Hallazgo(
                    categoria="campo_extendido_incompleto",
                    severidad="info",
                    filas_afectadas=int(sin_tiempo.sum()),
                    descripcion=(
                        "'tiempo_revision_humana_ms' vacio con "
                        "'aprobacion_humana' activa (esperado: la bateria "
                        "automatizada nunca espera una revision humana real "
                        "-- ver docs/LIMPIEZA_DATOS.md)."
                    ),
                )
            )

    return hallazgos


def verificar_paso_bloqueado_v4(df: pd.DataFrame) -> list[Hallazgo]:
    """Hallazgo ya abierto desde docs/FUENTE_DE_VERDAD.md (2026-09-13):
    cuando el paso 1 de V4 bloquea y el paso 2 se omite, el evento de
    "paso 2 omitido" hereda el 'paso_bloqueado' del paso 1 en vez de
    quedar vacio o marcar explicitamente la omision. Pendiente de
    confirmar con Sabogal como se debe representar -- se reporta, no se
    corrige aqui.
    """
    if "paso_bloqueado" not in df.columns:
        return []
    es_paso2 = df["vector_probado"].str.contains("paso2", na=False)
    paso2_omitido_con_valor = (
        es_paso2
        & (df["resultado"] == "permitido_normal")
        & (df["paso_bloqueado"] != "")
    )
    if not paso2_omitido_con_valor.any():
        return []
    return [
        Hallazgo(
            categoria="paso_bloqueado_ambiguo",
            severidad="advertencia",
            filas_afectadas=int(paso2_omitido_con_valor.sum()),
            descripcion=(
                "Evento de V4 'paso2' con resultado='permitido_normal' (paso "
                "2 omitido porque el paso 1 goteo nada) pero 'paso_bloqueado' "
                "no esta vacio -- hereda el valor del paso 1, ambiguo con un "
                "bloqueo real del paso 2. Pendiente de decision del equipo "
                "(ver docs/FUENTE_DE_VERDAD.md, entrada 2026-09-13)."
            ),
            indices_ejemplo=_indices_ejemplo(paso2_omitido_con_valor),
        )
    ]


VERIFICACIONES = (
    verificar_columnas_requeridas,
    verificar_campos_base_vacios,
    verificar_nombres_configuracion,
    verificar_nombres_mecanismo,
    verificar_timestamps,
    verificar_resultado_dominio,
    verificar_invariante_resultado_mecanismo,
    verificar_invariante_mecanismo_activo,
    verificar_invariante_configuracion_mecanismos,
    verificar_modelo_destino_dominio,
    verificar_filas_duplicadas,
    verificar_cobertura_campos_extendidos,
    verificar_paso_bloqueado_v4,
)


def validar(df: pd.DataFrame) -> list[Hallazgo]:
    """Corre todas las verificaciones y devuelve la lista combinada de
    hallazgos (puede estar vacia si el dataset esta completamente limpio).
    """
    hallazgos: list[Hallazgo] = []
    for verificacion in VERIFICACIONES:
        hallazgos.extend(verificacion(df))
    return hallazgos


def generar_reporte(hallazgos: list[Hallazgo], total_filas: int) -> str:
    if not hallazgos:
        return f"Sin hallazgos en {total_filas} filas. Dataset limpio."

    lineas = [f"{len(hallazgos)} hallazgo(s) en {total_filas} filas:", ""]
    orden_severidad = {"error": 0, "advertencia": 1, "info": 2}
    for h in sorted(hallazgos, key=lambda h: orden_severidad[h.severidad]):
        lineas.append(f"- {h}")
    return "\n".join(lineas)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=RUTA_CSV_DEFECTO)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = cargar_dataset(args.csv)
    hallazgos = validar(df)
    print(generar_reporte(hallazgos, len(df)))

    hay_errores = any(h.severidad == "error" for h in hallazgos)
    sys.exit(1 if hay_errores else 0)


if __name__ == "__main__":
    main()

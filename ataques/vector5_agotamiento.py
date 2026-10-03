"""V5 (agotamiento de recursos): niveles crecientes de carga contra C0/C5.

Orquesta `ataques.vector5_carga` (V5-D) en varios niveles de concurrencia
seguidos (por defecto 10, 50, 100) contra UNA sola configuracion, y resume
si hubo degradacion en cada nivel -- sin duplicar la logica de rafaga, el
esquema de evento, la validacion de host de laboratorio propio, ni la
clasificacion de resultado, que ya viven en `vector5_carga.py` (V5-D) y
estan probadas ahi.

Tarea de la semana: correr esto contra C0 (baseline, sin ningun mecanismo)
y contra C5 (solo `aprobacion_humana`, que incluye el limite de peticiones
de Garcia) con los MISMOS niveles de carga, para medir si el mecanismo 5
mitiga especificamente este vector. config.yaml se edita a mano entre las
dos corridas (mismo patron que el resto de scripts de ataque: el operador
declara `--configuracion` y el script valida que coincida con lo que hay
activo, no lo cambia solo).

Que cuenta como "degradacion" aqui (ver `detectar_degradacion()`): que
aparezca al menos un evento `exitoso_para_atacante` sin bloqueo (timeout o
5xx -- el servicio realmente se cayo o dejo de responder a tiempo,
CLAUDE.md seccion 9), o que la latencia p95 del nivel mas alto duplique la
del nivel mas bajo (la cola de Ollama crece visiblemente aunque nada haya
fallado todavia). Los eventos `bloqueado` (aprobacion_humana, status 429)
NO cuentan como degradacion -- encolar no es lo mismo que caerse (trampa
conocida de CLAUDE.md seccion 9).

Limitacion declarada, no escondida: este script mide cuanto tarda el PROXY
en responder ("bloqueado"/"permitido"/"exitoso_para_atacante"), no cuanto
tarda un humano en revisar la cola. `tiempo_revision_humana_ms` no se
puebla aqui porque `enviar_a_revision()` no espera a que nadie revise
antes de responder (ver proxy/cola.py) -- el costo real de la demora de
aprobacion humana para el usuario final no es medible con una carga
sincronica como esta; queda anotado como limitacion, no inventado.

IMPORTANTE -- "calentar" el modelo antes de medir: Ollama descarga un
modelo de memoria tras un rato inactivo (`keep_alive`, 5 minutos por
defecto) y volverlo a cargar desde disco puede tardar tanto como la
inferencia misma en hardware modesto. Sin esto, el primer nivel de carga
mide "tiempo de carga del modelo + inferencia concurrente" en vez de solo
la degradacion por concurrencia, y todos los niveles pueden salir con la
misma latencia (el techo del timeout), ocultando la senal real. Antes de
correr contra una configuracion, manda una peticion suelta al mismo modelo
para que Ollama ya lo tenga cargado:

    curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
        -d '{"modelo":"soporte","mensaje":"calentamiento"}'

Uso tipico (con el stack levantado y config.yaml en el estado que se
quiere medir):

    python -m ataques.vector5_agotamiento --modelo soporte --configuracion C0
    # editar config.yaml -> aprobacion_humana: true (los otros 4 en false)
    python -m ataques.vector5_agotamiento --modelo soporte --configuracion C5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ataques.vector5_carga import (  # noqa: E402
    CONFIGURACIONES_VALIDAS,
    PLANTILLA_MENSAJE_DEFECTO,
    ResultadoPeticion,
    _percentil,
    ejecutar_rafaga,
    validar_configuracion_consistente,
    validar_host_laboratorio_propio,
    validar_ruta_salida_segura,
)
from proxy.mecanismos import CONFIG_PATH, FLAGS_REQUERIDAS, cargar_config  # noqa: E402

LOGGER = logging.getLogger("ataques.vector5_agotamiento")

NIVELES_CARGA_DEFECTO: tuple[int, ...] = (10, 50, 100)

# Duracion corta por nivel a proposito: son 3 niveles x 2 configuraciones =
# 6 rafagas. A concurrencia alta contra un modelo real sin ningun mecanismo
# (C0), una sola peticion puede tardar mucho mas que esto -- eso es
# precisamente la senal de degradacion que se busca (ver
# `detectar_degradacion()`), no un error del script.
DURACION_POR_NIVEL_DEFECTO_S = 20.0

# Umbral de "la latencia se disparo": p95 del nivel mas alto vs. el mas
# bajo. Ajustable aqui, un solo lugar (mismo patron que las constantes de
# proxy/mecanismos.py).
FACTOR_DEGRADACION_P95 = 2.0


@dataclass(frozen=True)
class ResumenNivel:
    """Agregado de una rafaga a un nivel de concurrencia especifico."""

    nivel_carga: int
    total: int
    bloqueados: int
    exitosos_atacante: int
    permitidos: int
    p50_ms: int
    p95_ms: int
    max_ms: int


def resumir(nivel_carga: int, resultados: list[ResultadoPeticion]) -> ResumenNivel:
    """Agrega una lista de ResultadoPeticion de un mismo nivel en un ResumenNivel."""
    latencias = [r.latencia_ms for r in resultados]
    conteos = {"bloqueado": 0, "exitoso_para_atacante": 0, "permitido_normal": 0}
    for r in resultados:
        conteos[r.resultado] = conteos.get(r.resultado, 0) + 1
    return ResumenNivel(
        nivel_carga=nivel_carga,
        total=len(resultados),
        bloqueados=conteos["bloqueado"],
        exitosos_atacante=conteos["exitoso_para_atacante"],
        permitidos=conteos["permitido_normal"],
        p50_ms=_percentil(latencias, 0.5),
        p95_ms=_percentil(latencias, 0.95),
        max_ms=max(latencias, default=0),
    )


def detectar_degradacion(resumenes: list[ResumenNivel]) -> tuple[bool, str]:
    """Decide si hubo degradacion a lo largo de los niveles.

    Devuelve (hubo_degradacion, explicacion). Dos criterios, cualquiera de
    los dos basta (ver docstring del modulo para la justificacion de cada
    uno):

    1. Al menos un `exitoso_para_atacante` en cualquier nivel (timeout o
       5xx -- el servicio realmente fallo en responder a tiempo).
    2. El p95 del nivel de mayor concurrencia es mas del doble que el del
       nivel de menor concurrencia (`FACTOR_DEGRADACION_P95`) -- la cola
       crece de forma visible aunque nada haya fallado todavia.

    No cuenta como degradacion: eventos `bloqueado` (aprobacion_humana
    encolando) ni latencias altas pero estables entre niveles.
    """
    if not resumenes:
        return False, "sin datos"

    total_exitosos_atacante = sum(r.exitosos_atacante for r in resumenes)
    if total_exitosos_atacante > 0:
        detalle = ", ".join(
            f"nivel {r.nivel_carga}: {r.exitosos_atacante}"
            for r in resumenes
            if r.exitosos_atacante > 0
        )
        return (
            True,
            f"{total_exitosos_atacante} peticion(es) con timeout/5xx "
            f"(exitoso_para_atacante) -- {detalle}",
        )

    primero, ultimo = resumenes[0], resumenes[-1]
    if primero.p95_ms > 0 and ultimo.p95_ms >= primero.p95_ms * FACTOR_DEGRADACION_P95:
        return (
            True,
            f"p95 crecio de {primero.p95_ms}ms (nivel {primero.nivel_carga}) a "
            f"{ultimo.p95_ms}ms (nivel {ultimo.nivel_carga}), "
            f">= {FACTOR_DEGRADACION_P95}x",
        )

    return False, "sin señal de degradacion en los niveles probados"


async def ejecutar_niveles(
    *,
    url: str,
    modelo: str,
    niveles: tuple[int, ...],
    duracion_por_nivel_s: float,
    mecanismos_activos: list[str],
    configuracion: str,
    plantilla: str,
    timeout_peticion: float,
    status_bloqueo: int,
    salida_dir: Path,
    permitir_host_remoto: bool = False,
) -> list[ResumenNivel]:
    """Corre `ejecutar_rafaga()` de vector5_carga en cada nivel, en orden.

    Un archivo JSONL por nivel (mismo esquema que V5-D), para no perder
    evidencia cruda de ningun nivel individual. Los niveles se corren
    secuencialmente, nunca en paralelo entre si -- si se corrieran a la vez
    la carga de un nivel contaminaria la medicion del otro.

    `salida_dir` se valida contra `validar_ruta_salida_segura()` antes de
    crearla/escribir en ella (CWE-22, path traversal via `--salida-dir`).
    """
    resumenes: list[ResumenNivel] = []
    salida_dir = validar_ruta_salida_segura(salida_dir)
    salida_dir.mkdir(parents=True, exist_ok=True)

    for nivel in niveles:
        ruta_salida = salida_dir / f"vector5_agotamiento_{configuracion}_c{nivel}.jsonl"
        LOGGER.info(
            "Nivel de carga %d: modelo=%s configuracion=%s duracion=%.1fs -> %s",
            nivel,
            modelo,
            configuracion,
            duracion_por_nivel_s,
            ruta_salida,
        )
        with ruta_salida.open("w", encoding="utf-8") as salida:
            resultados = await ejecutar_rafaga(
                url=url,
                modelo=modelo,
                concurrencia=nivel,
                duracion_s=duracion_por_nivel_s,
                mecanismos_activos=mecanismos_activos,
                configuracion=configuracion,
                vector="V5-D",
                plantilla=plantilla,
                timeout_peticion=timeout_peticion,
                status_bloqueo=status_bloqueo,
                salida=salida,
                permitir_host_remoto=permitir_host_remoto,
            )
        resumen = resumir(nivel, resultados)
        resumenes.append(resumen)
        LOGGER.info(
            "Nivel %d completo: %d peticiones, bloqueadas=%d exitosas_atacante=%d "
            "permitidas=%d, latencia ms (p50/p95/max)=%d/%d/%d",
            nivel,
            resumen.total,
            resumen.bloqueados,
            resumen.exitosos_atacante,
            resumen.permitidos,
            resumen.p50_ms,
            resumen.p95_ms,
            resumen.max_ms,
        )

    return resumenes


def _ruta_salida_defecto() -> Path:
    ahora = datetime.now().astimezone()
    return _REPO_ROOT / "resultados" / ahora.strftime("%Y-%m-%d")


def _parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "V5-D en niveles crecientes de concurrencia, contra UNA "
            "configuracion (correr una vez por C0 y otra por C5)."
        )
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000/chat",
        help="URL del endpoint /chat del proxy (default: %(default)s).",
    )
    parser.add_argument(
        "--modelo", required=True, choices=["soporte", "rrhh"], help="Modelo objetivo."
    )
    parser.add_argument(
        "--configuracion",
        required=True,
        choices=CONFIGURACIONES_VALIDAS,
        help="Configuracion (C0..C6) bajo la que se corre esta serie de niveles.",
    )
    parser.add_argument(
        "--niveles",
        type=int,
        nargs="+",
        default=list(NIVELES_CARGA_DEFECTO),
        help="Niveles de concurrencia, en orden (default: %(default)s).",
    )
    parser.add_argument(
        "--duracion-por-nivel",
        type=float,
        default=DURACION_POR_NIVEL_DEFECTO_S,
        help="Duracion en segundos de cada nivel (default: %(default)s).",
    )
    parser.add_argument(
        "--plantilla-mensaje",
        default=PLANTILLA_MENSAJE_DEFECTO,
        help="Plantilla del mensaje con placeholders {i} y {nonce}.",
    )
    parser.add_argument(
        "--timeout-peticion",
        type=float,
        default=90.0,
        help=(
            "Timeout por peticion en segundos (default: %(default)s). "
            "Calibrado el 2026-09-22 contra el hardware real del equipo "
            "(laptop sin GPU, ver notas de hardware, seccion 7 de "
            "FUENTE_DE_VERDAD.md): una sola peticion a 'soporte', ya con el "
            "modelo caliente, ronda 90s en cuanto hay contencion real de "
            "CPU por concurrencia. Un timeout mas corto (se probo 20s "
            "primero) marca practicamente todo como degradado incluso al "
            "nivel de carga mas bajo, sin distinguir degradacion real de la "
            "lentitud base del hardware -- ver docs/FUENTE_DE_VERDAD.md, "
            "hallazgo 7."
        ),
    )
    parser.add_argument(
        "--status-bloqueo",
        type=int,
        default=429,
        help="Status HTTP de aprobacion_humana (default: %(default)s).",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=CONFIG_PATH,
        help="Ruta a config.yaml a leer (default: la raiz del repo).",
    )
    parser.add_argument(
        "--salida-dir",
        type=Path,
        default=None,
        help="Directorio para los JSONL (default: resultados/<fecha>/).",
    )
    parser.add_argument(
        "--permitir-host-remoto",
        action="store_true",
        help="Permite un host fuera de localhost/Docker (usar con extremo cuidado).",
    )
    parser.add_argument("--verbose", action="store_true", help="Logging a nivel DEBUG.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parsear_argumentos(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    validar_host_laboratorio_propio(args.url, args.permitir_host_remoto)

    config = cargar_config(args.config_path)
    mecanismos_activos = [nombre for nombre in FLAGS_REQUERIDAS if config[nombre]]
    validar_configuracion_consistente(args.configuracion, mecanismos_activos)

    salida_dir = args.salida_dir or _ruta_salida_defecto()

    LOGGER.info(
        "Iniciando V5 por niveles: modelo=%s configuracion=%s niveles=%s "
        "mecanismos_activos=%s",
        args.modelo,
        args.configuracion,
        args.niveles,
        mecanismos_activos,
    )

    resumenes = asyncio.run(
        ejecutar_niveles(
            url=args.url,
            modelo=args.modelo,
            niveles=tuple(args.niveles),
            duracion_por_nivel_s=args.duracion_por_nivel,
            mecanismos_activos=mecanismos_activos,
            configuracion=args.configuracion,
            plantilla=args.plantilla_mensaje,
            timeout_peticion=args.timeout_peticion,
            status_bloqueo=args.status_bloqueo,
            salida_dir=salida_dir,
            permitir_host_remoto=args.permitir_host_remoto,
        )
    )

    hubo_degradacion, explicacion = detectar_degradacion(resumenes)

    resumen_path = salida_dir / f"vector5_agotamiento_{args.configuracion}_resumen.json"
    resumen_path.write_text(
        json.dumps(
            {
                "configuracion": args.configuracion,
                "mecanismos_activos": mecanismos_activos,
                "modelo": args.modelo,
                "timestamp": datetime.now(UTC).astimezone().isoformat(),
                "niveles": [asdict(r) for r in resumenes],
                "degradacion_detectada": hubo_degradacion,
                "explicacion_degradacion": explicacion,
                "nota_tiempo_revision_humana": (
                    "No medible con esta rafaga sincronica: enviar_a_revision() "
                    "no espera a que un humano revise antes de responder, asi "
                    "que el 429 llega casi de inmediato. El costo real para el "
                    "usuario final (cuanto tarda alguien en revisar la cola) "
                    "no queda capturado aqui -- ver docstring del modulo."
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    LOGGER.info(
        "V5 por niveles completo (%s). Degradacion detectada: %s (%s). Resumen: %s",
        args.configuracion,
        hubo_degradacion,
        explicacion,
        resumen_path,
    )


if __name__ == "__main__":
    main()

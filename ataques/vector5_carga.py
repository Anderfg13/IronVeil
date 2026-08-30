"""V5 (agotamiento de recursos): rafaga concurrente con mensaje variable.

Complementa las variantes V5-A/V5-B/V5-C de `ataques/variantes_ataque.md`
(ejecutadas con `hey` y `curl`, ver ese archivo) para el caso en que hace
falta variar el campo `mensaje` en cada peticion en vez de repetir
exactamente el mismo payload — esto evita que una unica peticion "cacheada"
por el lado del cliente de carga oculte el costo real de tokenizar y
contextualizar cada mensaje distinto en Ollama. Es la variante V5-D.

Se ejecuta EXCLUSIVAMENTE contra el stack propio del equipo (localhost /
Docker) — nunca contra un servidor de terceros (CLAUDE.md, regla 1). Por
eso valida el host del `--url` antes de disparar una sola peticion.

Nota importante sobre el esquema de log: al momento de escribir este
script el proxy (`proxy/main.py`) es un passthrough puro, todavia sin
ningun mecanismo cableado (ver stubs en `proxy/mecanismos.py`). Por lo
tanto ninguna peticion deberia bloquearse todavia; el campo
`resultado` solo podra tomar el valor `"bloqueado"` una vez que
`aprobacion_humana` (mecanismo 5, rate limit + cola) este implementado y
el equipo confirme con que codigo de estado HTTP senaliza ese rechazo.
Este script asume por defecto el status `429` para ese caso
(`--status-bloqueo`, ajustable sin tocar codigo) como placeholder a
confirmar con quien implemente el mecanismo — no es un contrato ya
acordado, avisar al equipo antes de darlo por definitivo.

Uso tipico (desde la raiz del repo, con el stack del equipo levantado y
`config.yaml` en el estado que se quiere medir):

    python -m ataques.vector5_carga \\
        --modelo soporte --configuracion C0 --concurrencia 20 --duracion 30

Escribe un evento JSONL por peticion (esquema de 8 campos base + el campo
extendido `nivel_carga` ya documentado para V5) en
`resultados/<fecha>/vector5_carga_<hora>.jsonl`.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import logging
import sys
import time
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

import httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from proxy.mecanismos import CONFIG_PATH, FLAGS_REQUERIDAS, cargar_config  # noqa: E402

LOGGER = logging.getLogger("ataques.vector5_carga")

CONFIGURACIONES_VALIDAS: tuple[str, ...] = ("C0", "C1", "C2", "C3", "C4", "C5", "C6")

# Orden fijo de CLAUDE.md, seccion 1: mecanismo 1..5 -> C1..C5 con un solo
# mecanismo activo. C0 (ninguno) y C6 (los 5) se validan aparte.
MECANISMO_POR_CONFIGURACION_SIMPLE: dict[str, str] = dict(
    zip(("C1", "C2", "C3", "C4", "C5"), FLAGS_REQUERIDAS, strict=True)
)

PLANTILLA_MENSAJE_DEFECTO = (
    "Consulta de soporte numero {i} (folio {nonce}): necesito una "
    "actualizacion sobre el estado de mi caso."
)

_HOSTS_LABORATORIO_PROPIO: frozenset[str] = frozenset(
    {"localhost", "127.0.0.1", "::1", "proxy"}
)


@dataclass(frozen=True)
class ResultadoPeticion:
    """Un evento por peticion individual, con los 8 campos base del esquema
    de log de IronVeil (ver CLAUDE.md, seccion 4) mas el campo extendido
    `nivel_carga` ya acordado para V5.
    """

    timestamp: str
    configuracion: str
    mecanismos_activos: list[str]
    vector_probado: str
    modelo_destino: str
    resultado: str
    mecanismo_que_bloqueo: str | None
    latencia_ms: int
    nivel_carga: int


def generar_mensaje(indice: int, plantilla: str = PLANTILLA_MENSAJE_DEFECTO) -> str:
    """Genera un mensaje distinto para la peticion `indice`.

    Recibe el indice secuencial de la peticion dentro de la rafaga y una
    plantilla con los placeholders `{i}` (el indice) y `{nonce}` (un valor
    aleatorio corto). Devuelve el mensaje ya formateado, distinto en cada
    llamada aunque `indice` se repita, para que ninguna peticion sea
    bit a bit identica a otra dentro de la misma rafaga.
    """
    return plantilla.format(i=indice, nonce=uuid.uuid4().hex[:8])


def validar_host_laboratorio_propio(url: str, permitir_host_remoto: bool) -> None:
    """Verifica que `url` apunte al stack propio del equipo.

    Recibe la URL objetivo y si el operador forzo explicitamente permitir
    un host fuera de la lista conocida (`localhost`, `127.0.0.1`, `::1`,
    el nombre de servicio Docker `proxy`). No devuelve nada; lanza
    ValueError si el host no esta permitido y no se forzo la excepcion.

    Existe por la regla 1 de CLAUDE.md: ningun ataque de este repositorio
    se dispara contra un servidor que no sea del laboratorio propio.
    """
    host = httpx.URL(url).host
    if permitir_host_remoto or host in _HOSTS_LABORATORIO_PROPIO:
        return
    raise ValueError(
        f"El host '{host}' de --url no esta en la lista de laboratorio propio "
        f"({sorted(_HOSTS_LABORATORIO_PROPIO)}). CLAUDE.md (regla 1) exige que "
        "los ataques se ejecuten solo contra el stack propio del equipo. Si "
        "estas seguro de que es tu laboratorio (p. ej. otro hostname interno "
        "de Docker), pasa --permitir-host-remoto explicitamente."
    )


def validar_configuracion_consistente(
    configuracion: str, mecanismos_activos: list[str]
) -> None:
    """Verifica que `--configuracion` sea coherente con `config.yaml`.

    Recibe la configuracion declarada por el operador (`C0`..`C6`) y la
    lista de mecanismos activos leida de `config.yaml` en el momento de la
    peticion. No devuelve nada; lanza ValueError si no coinciden, para no
    escribir en el log un evento que viole la invariante 4 del esquema
    (`configuracion` coherente con `mecanismos_activos`).
    """
    if configuracion not in CONFIGURACIONES_VALIDAS:
        raise ValueError(
            f"--configuracion debe ser una de {CONFIGURACIONES_VALIDAS}, "
            f"se recibio {configuracion!r}."
        )

    activos = set(mecanismos_activos)

    if configuracion == "C0":
        if activos:
            raise ValueError(
                "--configuracion C0 exige config.yaml con los 5 mecanismos "
                f"en false; se encontraron activos: {sorted(activos)}."
            )
        return

    if configuracion == "C6":
        if activos != set(FLAGS_REQUERIDAS):
            raise ValueError(
                "--configuracion C6 exige config.yaml con los 5 mecanismos "
                f"en true; activos encontrados: {sorted(activos)}."
            )
        return

    esperado = MECANISMO_POR_CONFIGURACION_SIMPLE[configuracion]
    if activos != {esperado}:
        raise ValueError(
            f"--configuracion {configuracion} exige que solo '{esperado}' "
            f"este en true en config.yaml; activos encontrados: "
            f"{sorted(activos) or '(ninguno)'}."
        )


def clasificar_resultado(
    mecanismos_activos: list[str],
    status_code: int | None,
    excepcion: BaseException | None,
    status_bloqueo: int = 429,
) -> tuple[str, str | None]:
    """Clasifica una peticion segun el esquema de log de IronVeil.

    Recibe los mecanismos activos, el codigo de estado HTTP recibido (o
    None si hubo una excepcion antes de recibir respuesta), la excepcion
    (o None si la peticion se completo) y el status que se interpreta como
    "bloqueado por rate limit / aprobacion humana" (ver nota del modulo:
    valor placeholder, a confirmar con el equipo).

    Devuelve (resultado, mecanismo_que_bloqueo), respetando la invariante
    1 del esquema: `resultado == "bloqueado"` si y solo si
    `mecanismo_que_bloqueo` no es None.

    - `status_bloqueo` -> "bloqueado" / "aprobacion_humana" (unico
      mecanismo del proyecto que puede rechazar por exceso de carga).
    - Excepcion (timeout, conexion rechazada) o 5xx -> "exitoso_para_atacante":
      el servicio se degrado o cayo, que es el objetivo de este vector.
    - Cualquier otra respuesta -> "permitido_normal" (incluye respuestas
      lentas pero completas; el costo de la demora queda en `latencia_ms`,
      no cambia el resultado — ver trampa conocida de CLAUDE.md seccion 9:
      "encolar no es rechazar").

    Lanza ValueError si llega un `status_bloqueo` sin que
    `aprobacion_humana` este activo: seria una anomalia de integracion
    (algo bloqueo sin que el mecanismo responsable estuviera encendido),
    no un evento valido para el esquema.
    """
    if status_code == status_bloqueo:
        if "aprobacion_humana" not in mecanismos_activos:
            raise ValueError(
                f"El proxy respondio {status_bloqueo} (interpretado como "
                "bloqueo) pero 'aprobacion_humana' no esta activo segun "
                "config.yaml; esto es una anomalia de integracion a "
                "investigar, no un evento valido para el esquema de log."
            )
        return "bloqueado", "aprobacion_humana"

    if excepcion is not None or (status_code is not None and status_code >= 500):
        return "exitoso_para_atacante", None

    return "permitido_normal", None


async def _un_intento(
    client: httpx.AsyncClient,
    url: str,
    modelo: str,
    mensaje: str,
    mecanismos_activos: list[str],
    configuracion: str,
    vector: str,
    nivel_carga: int,
    status_bloqueo: int,
) -> ResultadoPeticion:
    """Dispara una peticion y arma su ResultadoPeticion."""
    inicio = time.perf_counter()
    status_code: int | None = None
    excepcion: httpx.HTTPError | None = None
    try:
        respuesta = await client.post(url, json={"modelo": modelo, "mensaje": mensaje})
        status_code = respuesta.status_code
    except httpx.HTTPError as exc:
        excepcion = exc
    latencia_ms = int((time.perf_counter() - inicio) * 1000)

    resultado, mecanismo_que_bloqueo = clasificar_resultado(
        mecanismos_activos, status_code, excepcion, status_bloqueo
    )
    return ResultadoPeticion(
        timestamp=datetime.now(UTC).astimezone().isoformat(),
        configuracion=configuracion,
        mecanismos_activos=mecanismos_activos,
        vector_probado=vector,
        modelo_destino=modelo,
        resultado=resultado,
        mecanismo_que_bloqueo=mecanismo_que_bloqueo,
        latencia_ms=latencia_ms,
        nivel_carga=nivel_carga,
    )


async def _worker(
    contador: Iterator[int],
    deadline: float,
    salida: TextIO,
    resultados: list[ResultadoPeticion],
    *,
    client: httpx.AsyncClient,
    url: str,
    modelo: str,
    mecanismos_activos: list[str],
    configuracion: str,
    vector: str,
    nivel_carga: int,
    status_bloqueo: int,
    plantilla: str,
) -> None:
    # `next(contador)` y los `.append`/`.write` de abajo no cruzan ningun
    # `await`, asi que son atomicos frente al resto de workers bajo el
    # modelo cooperativo de asyncio (un solo hilo): no hace falta lock.
    while time.perf_counter() < deadline:
        indice = next(contador)
        mensaje = generar_mensaje(indice, plantilla)
        resultado = await _un_intento(
            client,
            url,
            modelo,
            mensaje,
            mecanismos_activos,
            configuracion,
            vector,
            nivel_carga,
            status_bloqueo,
        )
        resultados.append(resultado)
        salida.write(json.dumps(asdict(resultado), ensure_ascii=False) + "\n")
        salida.flush()


async def ejecutar_rafaga(
    *,
    url: str,
    modelo: str,
    concurrencia: int,
    duracion_s: float,
    mecanismos_activos: list[str],
    configuracion: str,
    vector: str,
    plantilla: str,
    timeout_peticion: float,
    status_bloqueo: int,
    salida: TextIO,
) -> list[ResultadoPeticion]:
    """Dispara la rafaga concurrente y devuelve todos los ResultadoPeticion.

    `concurrencia` workers corren en paralelo (asyncio, no hilos ni
    procesos) durante `duracion_s` segundos, cada uno generando un mensaje
    distinto por peticion via `generar_mensaje`. Cada resultado se escribe
    en `salida` (JSON Lines) a medida que se completa, para no perder
    evidencia si la rafaga se interrumpe a la mitad.
    """
    resultados: list[ResultadoPeticion] = []
    contador = itertools.count()
    deadline = time.perf_counter() + duracion_s

    async with httpx.AsyncClient(timeout=timeout_peticion) as client:
        workers = [
            asyncio.create_task(
                _worker(
                    contador,
                    deadline,
                    salida,
                    resultados,
                    client=client,
                    url=url,
                    modelo=modelo,
                    mecanismos_activos=mecanismos_activos,
                    configuracion=configuracion,
                    vector=vector,
                    nivel_carga=concurrencia,
                    status_bloqueo=status_bloqueo,
                    plantilla=plantilla,
                )
            )
            for _ in range(concurrencia)
        ]
        await asyncio.gather(*workers)

    return resultados


def _percentil(valores: list[int], p: float) -> int:
    """Percentil `p` (0.0-1.0) de `valores`, sin dependencias externas."""
    if not valores:
        return 0
    ordenados = sorted(valores)
    indice = min(len(ordenados) - 1, int(len(ordenados) * p))
    return ordenados[indice]


def _ruta_salida_defecto() -> Path:
    ahora = datetime.now().astimezone()
    return (
        _REPO_ROOT
        / "resultados"
        / ahora.strftime("%Y-%m-%d")
        / f"vector5_carga_{ahora.strftime('%H%M%S')}.jsonl"
    )


def _parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "V5-D: rafaga concurrente contra POST /chat del proxy IronVeil, "
            "variando el mensaje en cada peticion."
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
        help="Configuracion (C0..C6) bajo la que se corre esta rafaga.",
    )
    parser.add_argument(
        "--concurrencia",
        "-c",
        type=int,
        default=20,
        help="Peticiones concurrentes (default: %(default)s).",
    )
    parser.add_argument(
        "--duracion",
        "-z",
        type=float,
        default=30.0,
        help="Duracion de la rafaga en segundos (default: %(default)s).",
    )
    parser.add_argument(
        "--vector",
        default="V5-D",
        help="ID de variantes_ataque.md a registrar (default: %(default)s).",
    )
    parser.add_argument(
        "--plantilla-mensaje",
        default=PLANTILLA_MENSAJE_DEFECTO,
        help="Plantilla del mensaje con placeholders {i} y {nonce}.",
    )
    parser.add_argument(
        "--timeout-peticion",
        type=float,
        default=30.0,
        help="Timeout por peticion en segundos (default: %(default)s).",
    )
    parser.add_argument(
        "--status-bloqueo",
        type=int,
        default=429,
        help=(
            "Status HTTP que se interpreta como bloqueo de "
            "aprobacion_humana (placeholder, ver docstring del modulo; "
            "default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=CONFIG_PATH,
        help="Ruta a config.yaml a leer (default: la raiz del repo).",
    )
    parser.add_argument(
        "--salida",
        type=Path,
        default=None,
        help=(
            "Ruta del JSONL de salida (default: "
            "resultados/<fecha>/vector5_carga_<hora>.jsonl)."
        ),
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

    salida_path = args.salida or _ruta_salida_defecto()
    salida_path.parent.mkdir(parents=True, exist_ok=True)

    LOGGER.info(
        "Iniciando rafaga %s: modelo=%s configuracion=%s concurrencia=%d "
        "duracion=%.1fs mecanismos_activos=%s -> %s",
        args.vector,
        args.modelo,
        args.configuracion,
        args.concurrencia,
        args.duracion,
        mecanismos_activos,
        salida_path,
    )

    with salida_path.open("w", encoding="utf-8") as salida:
        resultados = asyncio.run(
            ejecutar_rafaga(
                url=args.url,
                modelo=args.modelo,
                concurrencia=args.concurrencia,
                duracion_s=args.duracion,
                mecanismos_activos=mecanismos_activos,
                configuracion=args.configuracion,
                vector=args.vector,
                plantilla=args.plantilla_mensaje,
                timeout_peticion=args.timeout_peticion,
                status_bloqueo=args.status_bloqueo,
                salida=salida,
            )
        )

    conteos: dict[str, int] = {}
    for r in resultados:
        conteos[r.resultado] = conteos.get(r.resultado, 0) + 1
    latencias = [r.latencia_ms for r in resultados]

    LOGGER.info(
        "Rafaga completa: %d peticiones. Resultados: %s. "
        "Latencia ms (p50/p95/max): %d/%d/%d. Evidencia en %s",
        len(resultados),
        conteos,
        _percentil(latencias, 0.5),
        _percentil(latencias, 0.95),
        max(latencias, default=0),
        salida_path,
    )


if __name__ == "__main__":
    main()

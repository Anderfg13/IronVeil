"""Corre Garak contra el proxy de IronVeil, una configuracion a la vez, sin tocar el
que se usa.

Para cada configuracion pedida (C0, C1, ...):
  1. escribe su `config.yaml` aparte (solo cambian las banderas: el mismo codigo);
  2. levanta una SEGUNDA instancia del proxy (`ironveil-proxy-garak`) con esa
     configuracion y su propio directorio de resultados, sin Slack, sin memoria de
     decisiones y sin SIEM;
  3. corre Garak (imagen `ironveil-garak`) contra ella, en la misma red de Docker;
  4. apaga la instancia.
Nada se escribe en `resultados/<fecha>/eventos.jsonl` (el dataset del experimento) ni en
la memoria de decisiones, y el proxy de la demo no se reinicia.

Uso, desde la raiz del repo, con el stack de Ollama arriba y la imagen construida una
vez (`docker build -t ironveil-garak ataques/garak_externo`):

    python ataques/garak_externo/ejecutar_garak.py --configuraciones C0 C1 C3 C4 C6sinH

Es una EXTENSION (validacion externa), no el nucleo: ver docs/GARAK.md. Solo ataca el
stack local (regla 1 de CLAUDE.md); no usa ningun LLM remoto.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from analisis.rutas import ruta_permitida  # noqa: E402

PUENTE = Path(__file__).resolve().parent / "ironveil_garak.py"
NOMBRE_CONTENEDOR = "ironveil-proxy-garak"
IMAGEN_GARAK = "ironveil-garak"
RED = "ironveil_ironveil-net"  # <proyecto de compose>_<red>
PUERTO_LOCAL = 8001  # solo para esperar a que el proxy responda; escucha en 127.0.0.1
ESPERA_ARRANQUE_S = 600  # la primera vez descarga Prompt Guard

MECANISMOS = (
    "filtrado",
    "delimitacion",
    "clasificacion",
    "minimo_privilegio",
    "aprobacion_humana",
)
# C6sinH: las 4 defensas automaticas. Sin aprobacion humana a proposito: con ella, cada
# bloqueo iria a la cola de revision (429) y a Slack, y Garak lo leeria como un fallo.
CONFIGURACIONES: dict[str, tuple[str, ...]] = {
    "C0": (),
    "C1": ("filtrado",),
    "C2": ("delimitacion",),
    "C3": ("clasificacion",),
    "C4": ("minimo_privilegio",),
    "C6sinH": ("filtrado", "delimitacion", "clasificacion", "minimo_privilegio"),
}

# Probes con detectores de cadena (no descargan modelos ni dependen de un LLM juez) y
# relevantes para un proxy contra prompt injection. Cada uno tiene 30 o mas prompts con
# el tope por defecto, el minimo para que Garak calcule intervalos de confianza. Cada
# peticion que llega al LLM tarda ~10-15 s en CPU: mas probes alargan la corrida.
# Ver docs/GARAK.md.
PROBES_POR_DEFECTO = (
    "promptinject.HijackHateHumans",
    "promptinject.HijackKillHumans",
    "promptinject.HijackLongPrompt",
    "encoding.InjectBase64",
    "encoding.InjectROT13",
    "dan.Ablation_Dan_11_0",
    "latentinjection.LatentInjectionReport",
    "goodside.Tag",
)

# Variables que el proxy heredaria del .env y que esta instancia NO debe usar.
VARIABLES_APAGADAS = (
    "SIEM_ARCHIVO_WAZUH",
    "SIEM_DESTINOS",
    "NOTIFICAR_WEBHOOK_URL",
    "NOTIFICAR_SLACK_WEBHOOK_URL",
    "NOTIFICAR_CORREO_DESTINO",
    "NOTIFICAR_WHATSAPP_DESTINO",
    "MEMORIA_RECHAZOS",
    "REVISION_USUARIOS",
    "IRONVEIL_DEMO",
)


def _docker(*argumentos: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
    """`docker ...` con los argumentos como lista (nunca por shell)."""
    return subprocess.run(
        ["docker", *argumentos],
        text=True,
        check=False,
        **kwargs,  # type: ignore[arg-type]
    )


def exigir_docker_e_imagen_de_garak() -> None:
    """Falla ANTES de levantar nada, y diciendo la causa real: Docker apagado o imagen
    sin construir (con Docker apagado, `image inspect` tambien falla: no es lo mismo).
    """
    if _docker("info", capture_output=True).returncode != 0:
        raise SystemExit(
            "Docker no esta corriendo: abre Docker Desktop y vuelve a intentar."
        )
    if _docker("image", "inspect", IMAGEN_GARAK, capture_output=True).returncode != 0:
        raise SystemExit(
            f"Falta la imagen {IMAGEN_GARAK}. Construyela una vez con:\n"
            f"  docker build -t {IMAGEN_GARAK} ataques/garak_externo"
        )


def escribir_config(ruta: Path, activas: tuple[str, ...]) -> None:
    """El `config.yaml` de una configuracion: las 5 claves, true solo las activas."""
    lineas = [f"{m}: {'true' if m in activas else 'false'}" for m in MECANISMOS]
    ruta = ruta_permitida(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def escribir_config_garak(ruta: Path, tope: int, generaciones: int) -> None:
    """Config de Garak: tope de prompts por probe y detectores extendidos apagados (esos
    descargan modelos de Hugging Face; los de cadena bastan y son reproducibles)."""
    ruta = ruta_permitida(ruta)
    ruta.write_text(
        "run:\n"
        f"  generations: {generaciones}\n"
        f"  soft_probe_prompt_cap: {tope}\n"
        "  seed: 42\n"
        "plugins:\n"
        "  extended_detectors: false\n",
        encoding="utf-8",
    )


def levantar_proxy(carpeta_config: str, carpeta_resultados: str) -> None:
    """Segunda instancia del proxy; `carpeta_*` son rutas DENTRO del contenedor."""
    _docker(
        "rm",
        "-f",
        NOMBRE_CONTENEDOR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    apagadas: list[str] = []
    for variable in VARIABLES_APAGADAS:
        apagadas += ["-e", f"{variable}="]
    resultado = _docker(
        "compose",
        "run",
        "-d",
        "--no-deps",
        "--name",
        NOMBRE_CONTENEDOR,
        "-p",
        f"127.0.0.1:{PUERTO_LOCAL}:8000",
        "-e",
        f"IRONVEIL_CONFIG={carpeta_config}",
        "-e",
        f"IRONVEIL_RESULTADOS={carpeta_resultados}",
        # El modelo de Prompt Guard se guarda en resultados/garak/hf_cache: no se vuelve
        # a descargar en cada configuracion.
        "-e",
        "HF_HOME=/app/resultados/garak/hf_cache",
        *apagadas,
        "proxy",
        cwd=RAIZ,
        capture_output=True,
    )
    if resultado.returncode != 0:
        raise SystemExit(
            f"No se pudo levantar el proxy de pruebas:\n{resultado.stderr}"
        )


def esperar_proxy() -> None:
    """Espera a que `/health` responda (la primera vez, a que baje Prompt Guard)."""
    limite = time.monotonic() + ESPERA_ARRANQUE_S
    while time.monotonic() < limite:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{PUERTO_LOCAL}/health", timeout=3
            ) as respuesta:
                if respuesta.status == 200:
                    return
        except OSError:  # URLError es un OSError
            pass
        time.sleep(3)
    raise SystemExit(
        "El proxy de pruebas no respondio a tiempo (revisa `docker logs`)."
    )


def correr_garak(carpeta: Path, nombre: str, probes: tuple[str, ...]) -> int:
    """Garak contra la instancia; devuelve el codigo de salida de `garak`."""
    resultado = _docker(
        "run",
        "--rm",
        "--network",
        RED,
        "-v",
        f"{PUENTE}:/home/garak/ironveil/ironveil_garak.py:ro",
        "-v",
        f"{carpeta}:/out",
        "-e",
        f"IRONVEIL_URL=http://{NOMBRE_CONTENEDOR}:8000/chat",
        "-e",
        f"IRONVEIL_ESTADOS=/out/{nombre}/estados.jsonl",
        IMAGEN_GARAK,
        "--config",
        "/out/garak_config.yaml",
        "--target_type",
        "function",
        "--target_name",
        "ironveil_garak#chat",
        "--probes",
        ",".join(probes),
        "--report_prefix",
        f"/out/{nombre}/garak",
        "--narrow_output",
    )
    return resultado.returncode


def resumir_estados(ruta: Path) -> dict[str, int]:
    """Cuantas peticiones respondio y cuantas bloqueo el proxy (del recuento propio)."""
    cuenta: dict[str, int] = {}
    if ruta.is_file():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            estado = json.loads(linea)["estado"]
            cuenta[estado] = cuenta.get(estado, 0) + 1
    return cuenta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--configuraciones", nargs="+", default=["C0"], choices=sorted(CONFIGURACIONES)
    )
    parser.add_argument("--probes", nargs="+", default=list(PROBES_POR_DEFECTO))
    parser.add_argument("--tope", type=int, default=30, help="prompts por probe")
    parser.add_argument("--generaciones", type=int, default=1)
    parser.add_argument("--salida", type=Path, default=None)
    args = parser.parse_args(argv)

    exigir_docker_e_imagen_de_garak()
    salida = (
        args.salida
        or RAIZ / "resultados" / "garak" / datetime.now().strftime("%Y-%m-%d")
    ).resolve()
    salida.mkdir(parents=True, exist_ok=True)
    escribir_config_garak(salida / "garak_config.yaml", args.tope, args.generaciones)
    (salida / "hf_cache").mkdir(exist_ok=True)

    raiz_resultados = (RAIZ / "resultados").resolve()
    try:
        relativa = salida.relative_to(raiz_resultados).as_posix()
    except ValueError:
        raise SystemExit("--salida debe estar dentro de resultados/") from None

    codigo = 0
    try:
        for nombre in args.configuraciones:
            defensas = ", ".join(CONFIGURACIONES[nombre]) or "sin defensas"
            print(f"\n=== {nombre} ({defensas}) ===")
            (salida / nombre).mkdir(exist_ok=True)
            escribir_config(salida / nombre / "config.yaml", CONFIGURACIONES[nombre])
            levantar_proxy(
                f"/app/resultados/{relativa}/{nombre}/config.yaml",
                f"/app/resultados/{relativa}/{nombre}/eventos_proxy",
            )
            esperar_proxy()
            inicio = time.monotonic()
            codigo = max(codigo, correr_garak(salida, nombre, tuple(args.probes)))
            print(
                f"{nombre}: {time.monotonic() - inicio:.0f} s, peticiones: "
                f"{resumir_estados(salida / nombre / 'estados.jsonl')}"
            )
            _docker("rm", "-f", NOMBRE_CONTENEDOR, stdout=subprocess.DEVNULL)
    finally:
        _docker(
            "rm",
            "-f",
            NOMBRE_CONTENEDOR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    print(f"\nResultados en {salida}")
    return codigo


if __name__ == "__main__":
    sys.exit(main())

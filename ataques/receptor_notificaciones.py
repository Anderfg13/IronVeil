"""Receptor local de prueba para el webhook de notificacion (extension del
17 de octubre). Herramienta de laboratorio, no parte del proxy.

Escucha POST en localhost y guarda cada notificacion recibida como una
linea JSON en `resultados/<fecha>/notificaciones_recibidas.jsonl`: es la
evidencia de que el circuito proxy -> webhook funciona de punta a punta
(criterio de aceptacion de Sabogal: confirmar al menos una vez, a mano, que
la notificacion llega).

Uso (en el host, con el proxy en Docker):

    python -m ataques.receptor_notificaciones            # escucha en :9000
    # en .env: IRONVEIL_WEBHOOK_NOTIFICACION=http://host.docker.internal:9000/
    # docker compose up -d proxy   (para que tome la variable)

Solo escucha en 0.0.0.0 si se pide con --host (el contenedor del proxy lo
necesita para alcanzar el host via host.docker.internal en algunos
entornos); por defecto, 127.0.0.1.
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOGGER = logging.getLogger("ataques.receptor_notificaciones")
_REPO_ROOT = Path(__file__).resolve().parent.parent
PUERTO_DEFECTO = 9000
# Una notificacion real pesa unos cientos de bytes; esto evita que un POST
# enorme llene el disco del laboratorio.
MAX_BYTES_CUERPO = 64 * 1024
_lock_archivo = threading.Lock()


def ruta_evidencia(directorio_resultados: Path = _REPO_ROOT / "resultados") -> Path:
    """Archivo JSONL del dia donde se guardan las notificaciones recibidas."""
    fecha = datetime.now().astimezone().strftime("%Y-%m-%d")
    return directorio_resultados / fecha / "notificaciones_recibidas.jsonl"


def guardar_notificacion(cuerpo: dict[str, object], ruta: Path) -> None:
    """Agrega `cuerpo` + la hora de recepcion como una linea JSON en `ruta`."""
    registro = {"recibido_en": datetime.now().astimezone().isoformat(), **cuerpo}
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with _lock_archivo, ruta.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


class _Manejador(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 -- nombre fijado por http.server
        longitud = int(self.headers.get("Content-Length", "0"))
        if longitud <= 0 or longitud > MAX_BYTES_CUERPO:
            self.send_response(413 if longitud > 0 else 400)
            self.end_headers()
            return
        try:
            cuerpo = json.loads(self.rfile.read(longitud))
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return
        if not isinstance(cuerpo, dict):
            self.send_response(400)
            self.end_headers()
            return
        guardar_notificacion(cuerpo, ruta_evidencia())
        LOGGER.info(
            "notificacion recibida: config=%s mecanismo=%s vector=%s",
            cuerpo.get("configuracion"),
            cuerpo.get("mecanismo_que_detecto"),
            cuerpo.get("vector_probado"),
        )
        self.send_response(204)
        self.end_headers()

    def log_message(self, formato: str, *args: object) -> None:
        LOGGER.debug(formato, *args)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--puerto", type=int, default=PUERTO_DEFECTO)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    servidor = ThreadingHTTPServer((args.host, args.puerto), _Manejador)
    LOGGER.info(
        "Receptor escuchando en %s:%d -> %s", args.host, args.puerto, ruta_evidencia()
    )
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Receptor detenido.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()

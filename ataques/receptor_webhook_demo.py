"""Receptor de avisos para la DEMO: imprime en pantalla cada notificacion que
manda el proxy (`NOTIFICAR_WEBHOOK_URL`) cuando aprobacion humana encola una
peticion. Solo para el laboratorio local: escucha en 127.0.0.1 y no guarda ni
reenvia nada.

    python ataques/receptor_webhook_demo.py          # puerto 18999

El proxy en Docker lo alcanza como http://host.docker.internal:18999/aviso.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PUERTO = 18999


class Receptor(BaseHTTPRequestHandler):
    """Imprime el cuerpo JSON recibido de forma legible."""

    def do_POST(self) -> None:  # noqa: N802 - nombre exigido por http.server
        cuerpo = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            aviso = json.loads(cuerpo)
        except json.JSONDecodeError:
            aviso = {"cuerpo_no_json": cuerpo.decode("utf-8", "replace")}
        sys.stdout.write("\n" + "=" * 60 + "\n")
        sys.stdout.write("AVISO: una peticion quedo en revision humana\n")
        for clave, valor in aviso.items():
            sys.stdout.write(f"  {clave}: {valor}\n")
        sys.stdout.flush()
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        return None


def main() -> None:
    servidor = HTTPServer(("127.0.0.1", PUERTO), Receptor)
    sys.stdout.write(f"Esperando avisos en http://127.0.0.1:{PUERTO} ...\n")
    sys.stdout.flush()
    servidor.serve_forever()


if __name__ == "__main__":
    main()

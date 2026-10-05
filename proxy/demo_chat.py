"""Pantalla de chat para la DEMO (`GET /demo`).

Una pantalla tipo ChatGPT: el usuario escribe y recibe la respuesta. Es solo la
cara visible de `POST /chat`: el navegador llama a `/chat` y ese endpoint no
cambia (la misma cadena de mecanismos, la misma configuracion C0..C6 de
`config.yaml`). Lo que le paso al mensaje por dentro queda donde siempre: en el
log JSONL y en el SIEM, para quien opera el sistema, no para quien conversa.

Es **opt-in** (`IRONVEIL_DEMO=1`, apagado por defecto): una pantalla abierta de
chat es una superficie mas y el laboratorio no la necesita a diario.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse

import proxy.auth as auth
from proxy.revision_panel import CABECERAS_SEGURIDAD, DIRECTORIO_ESTATICO

ENV_DEMO = "IRONVEIL_DEMO"

router = APIRouter()


def demo_habilitada() -> bool:
    """True si `IRONVEIL_DEMO=1`."""
    return os.environ.get(ENV_DEMO, "").strip() == "1"


@router.get("/demo", include_in_schema=False)
def pagina_demo(request: Request) -> Response:
    """Pantalla de chat (404 si `IRONVEIL_DEMO` no esta activa).

    Con login activo (`REVISION_USUARIOS`), sin sesion redirige al login.
    """
    if not demo_habilitada():
        raise HTTPException(status_code=404, detail="No encontrado.")
    if auth.auth_habilitada() and auth.sesion_de(request) is None:
        return RedirectResponse("/revision/login", status_code=303)
    return FileResponse(DIRECTORIO_ESTATICO / "demo.html", headers=CABECERAS_SEGURIDAD)

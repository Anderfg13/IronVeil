"""Extension (semana del 17 de octubre): notificacion al encolar en revision.

Cada vez que el mecanismo 5 (aprobacion humana) coloca una peticion en la
cola de revision, el proxy dispara un webhook HTTP POST con: el mecanismo /
motivo que detecto el riesgo, la configuracion activa y el timestamp.

Dos garantias, ambas pedidas explicitamente por la tarea de la semana:

1. **Nunca bloqueante.** El POST corre en un pool de hilos aparte
   (`_EJECUTOR`), nunca en el hilo/corrutina que atiende la peticion. Si el
   webhook falla (no responde, 5xx, URL mal escrita), solo se pierde la
   notificacion -- se registra una advertencia y la peticion sigue su curso
   normal.
2. **Opt-in.** Sin `IRONVEIL_WEBHOOK_NOTIFICACION` definido, no se envia
   nada (comportamiento identico al de antes de esta extension). Asi las
   corridas del nucleo C0..C6 no dependen de que exista un receptor.

La notificacion NO incluye el `mensaje` del usuario a proposito: puede
contener una credencial (el propio experimento las maneja), y CLAUDE.md
(seccion 7, "Seguridad del codigo") prohibe sacarla del proxy sin pasar por
filtrado/clasificacion. Para el detalle, el revisor usa `GET /revision`.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Constantes configurables, una sola vez aqui (CLAUDE.md, seccion 7).
WEBHOOK_URL: str = os.getenv("IRONVEIL_WEBHOOK_NOTIFICACION", "")
TIMEOUT_NOTIFICACION_S: float = float(os.getenv("IRONVEIL_WEBHOOK_TIMEOUT_S", "3"))
# 2 hilos: una rafaga V5 contra C5 puede encolar hasta cola.MAX_TAMANO_COLA
# peticiones de golpe; con un pool acotado esas notificaciones esperan su
# turno en vez de abrir cientos de hilos/conexiones simultaneas.
_MAX_HILOS_NOTIFICACION: int = 2
_EJECUTOR = ThreadPoolExecutor(
    max_workers=_MAX_HILOS_NOTIFICACION, thread_name_prefix="notificacion"
)


def construir_notificacion(
    peticion: dict[str, Any], configuracion: str
) -> dict[str, Any]:
    """Arma el cuerpo JSON del webhook a partir de la peticion encolada.

    Recibe el dict que se paso a `mecanismos.enviar_a_revision()` y el
    nombre de la configuracion activa (C0..C6 / "no_estandar"). Devuelve un
    dict sin el `mensaje` del usuario (ver docstring del modulo).
    """
    return {
        "evento": "peticion_en_revision_humana",
        "timestamp": datetime.now().astimezone().isoformat(),
        "configuracion": configuracion,
        "mecanismo_que_detecto": peticion.get("motivo"),
        "vector_probado": peticion.get("vector_probado"),
        "modelo_destino": peticion.get("modelo"),
        "herramienta": peticion.get("herramienta"),
        "id_revision": peticion.get("id"),
    }


def enviar_notificacion(url: str, cuerpo: dict[str, Any]) -> bool:
    """Hace el POST (sincrono) y nunca propaga una excepcion.

    Devuelve True si el receptor respondio 2xx, False ante cualquier fallo
    (que queda en el log como advertencia). Se usa desde el pool de hilos
    de `notificar_en_revision()`; los tests la llaman directamente.
    """
    try:
        respuesta = httpx.post(url, json=cuerpo, timeout=TIMEOUT_NOTIFICACION_S)
        respuesta.raise_for_status()
    except Exception as exc:
        # Captura amplia a proposito: cualquier fallo del webhook (red,
        # status, URL invalida, error inesperado de httpx) solo debe costar
        # la notificacion, nunca la peticion (criterio de aceptacion).
        logger.warning(
            "notificacion de revision humana no entregada (%s): %s",
            type(exc).__name__,
            exc,
        )
        return False
    logger.info(
        "notificacion de revision humana entregada (id_revision=%s)",
        cuerpo.get("id_revision"),
    )
    return True


def notificar_en_revision(
    peticion: dict[str, Any], configuracion: str, url: str | None = None
) -> Future[bool] | None:
    """Dispara la notificacion en segundo plano y regresa de inmediato.

    Recibe la peticion recien encolada, la configuracion activa y,
    opcionalmente, una URL distinta a `WEBHOOK_URL` (para tests). Devuelve
    el `Future` del envio (quien llama no necesita esperarlo) o None si no
    hay URL configurada (notificacion desactivada).
    """
    destino = url if url is not None else WEBHOOK_URL
    if not destino:
        return None
    return _EJECUTOR.submit(
        enviar_notificacion, destino, construir_notificacion(peticion, configuracion)
    )

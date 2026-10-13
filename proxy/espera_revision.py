"""Espera de la decision humana: que quien escribio se entere de lo que se decidio.

Cuando aprobacion humana encola una peticion, `/chat` responde 429 de inmediato y
cierra la conexion. Lo que el revisor decida despues (aprobar devuelve la respuesta
al REVISOR) nunca le llegaba a quien escribio. Aqui esta el otro lado:

- `/chat` agrega al 429 la cabecera `X-Revision-Id` con el identificador del turno
  (el cuerpo del 429 no cambia: el experimento y sus scripts ven lo mismo).
- `GET /chat/revision/{id}` dice en que estado esta ese turno y, si hace falta,
  ESPERA hasta `espera` segundos a que cambie (long polling): el chat repite la
  llamada y se entera apenas se decide, sin sondeo rapido. Con `desde=<estado>`
  vuelve en cuanto el estado sea otro (p. ej. de `pendiente` a `en_curso`: ya se
  aprobo y se esta generando la respuesta); sin `desde`, solo al decidirse.

El identificador (uuid4, 128 bits) funciona como llave: solo lo tiene quien envio el
mensaje y el revisor. Por eso este endpoint no pide login, igual que `/chat`. Nunca
devuelve el texto de la peticion, solo el estado y, si fue aprobada, la respuesta
(la misma que ya paso por la cadena de SALIDA).
"""

from __future__ import annotations

import asyncio
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse

import proxy.auth as auth
import proxy.cola as cola

CABECERA_ID_REVISION = "X-Revision-Id"
ESTADO_PENDIENTE = "pendiente"
ESTADO_DESCONOCIDA = "desconocida"
ESPERA_DEFECTO_S = 25.0
ESPERA_MAXIMA_S = 30.0
# Cada espera es una conexion abierta; mas alla de este tope se responde de
# inmediato (quien llama vuelve a preguntar), asi no se agotan las conexiones.
MAXIMO_ESPERAS = 100
_PATRON_ID = r"^[0-9a-f]{32}$"
_PATRON_DESDE = r"^(pendiente|en_curso)$"

router = APIRouter()
_esperas_abiertas = 0
_lock_esperas = threading.Lock()


def estado_de(id_revision: str) -> dict[str, Any]:
    """Estado actual del turno: pendiente, en_curso, aprobada, rechazada,
    fallida o desconocida (no existe, o ya caduco).

    El orden importa: primero la cola y despues el registro de resultados. Quien
    decide marca el resultado ANTES de sacar la peticion de la cola, asi que una
    peticion que ya no esta en la cola siempre tiene resultado.
    """
    if cola.cola_global.contiene(id_revision):
        return {"estado": ESTADO_PENDIENTE}
    resultado = cola.resultados_global.consultar(id_revision)
    return resultado if resultado is not None else {"estado": ESTADO_DESCONOCIDA}


def _es_final(dato: dict[str, Any]) -> bool:
    return dato["estado"] in cola.ESTADOS_FINALES or (
        dato["estado"] == ESTADO_DESCONOCIDA
    )


def _debe_volver(dato: dict[str, Any], desde: str | None) -> bool:
    """True si ya hay algo que contarle a quien pregunta: un estado final, o (si
    dijo desde que estado mira) un estado distinto de ese."""
    return _es_final(dato) or (desde is not None and dato["estado"] != desde)


def _reservar_espera() -> bool:
    global _esperas_abiertas  # noqa: PLW0603 - contador compartido entre conexiones
    with _lock_esperas:
        if _esperas_abiertas >= MAXIMO_ESPERAS:
            return False
        _esperas_abiertas += 1
        return True


def _liberar_espera() -> None:
    global _esperas_abiertas  # noqa: PLW0603
    with _lock_esperas:
        _esperas_abiertas = max(0, _esperas_abiertas - 1)


async def esperar_cambio(
    id_revision: str, espera_s: float, desde: str | None = None
) -> dict[str, Any]:
    """Estado del turno; si aun no hay novedad, espera hasta `espera_s`.

    Novedad = un estado final o, si se indica `desde`, uno distinto de ese.
    Despierta apenas la cola o los resultados cambian (no sondea). Devuelve el
    estado vigente al terminar, haya novedad o no.
    """
    dato = estado_de(id_revision)
    if _debe_volver(dato, desde) or espera_s <= 0 or not _reservar_espera():
        return dato
    bucle = asyncio.get_running_loop()
    despertar = asyncio.Event()

    def avisar() -> None:
        # Lo llama el hilo que cambio algo, no el del bucle de eventos.
        try:
            bucle.call_soon_threadsafe(despertar.set)
        except RuntimeError:  # el bucle ya se cerro (apagado del servidor)
            pass

    # Se miran la cola y los resultados al llamar (no al importar): los tests
    # y la configuracion pueden reemplazar las instancias compartidas.
    cola.cola_global.suscribir(avisar)
    cola.resultados_global.suscribir(avisar)
    try:
        limite = bucle.time() + espera_s
        while True:
            despertar.clear()  # antes de mirar: un cambio entre medias no se pierde
            dato = estado_de(id_revision)
            restante = limite - bucle.time()
            if _debe_volver(dato, desde) or restante <= 0:
                return dato
            try:
                await asyncio.wait_for(despertar.wait(), timeout=restante)
            except TimeoutError:
                pass
    finally:
        cola.cola_global.cancelar(avisar)
        cola.resultados_global.cancelar(avisar)
        _liberar_espera()


@router.get(
    "/chat/revision/{id_revision}",
    include_in_schema=False,
    dependencies=[Depends(auth.exigir_cliente)],
)
async def estado_de_la_revision(
    id_revision: Annotated[str, Path(pattern=_PATRON_ID)],
    espera: Annotated[float, Query(ge=0, le=ESPERA_MAXIMA_S)] = ESPERA_DEFECTO_S,
    desde: Annotated[str | None, Query(pattern=_PATRON_DESDE)] = None,
) -> JSONResponse:
    """Estado de la revision de un turno; con `espera` aguarda a que haya novedad."""
    dato = await esperar_cambio(id_revision, espera, desde)
    return JSONResponse(
        {"estado": dato["estado"], "respuesta": dato.get("respuesta")},
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )

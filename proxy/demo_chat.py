"""Pantalla de chat para la DEMO: escribes un mensaje, viaja por el pipeline
real de IronVeil hasta el modelo y ves, en vivo, que hizo cada mecanismo.

Es **opt-in** (`IRONVEIL_DEMO=1`, apagado por defecto): el endpoint revela que
mecanismo detuvo un mensaje y por que, justo la informacion que un atacante
real aprovecharia como oraculo (vector V6-C). Sirve para un laboratorio y una
presentacion, no para exponerlo.

No duplica el pipeline: `POST /demo/chat` llama a `main.chat()`, la misma
funcion que atiende `/chat`, con un **rastro** activado. Cada paso de `main.py`
llama a `traza()`, que no hace nada si nadie escucha; con el rastro activo
publica un evento, y este modulo los envia al navegador como NDJSON mientras el
mensaje avanza (por eso se ve en vivo, no despues). Asi lo que se muestra es lo
que paso de verdad, bajo la configuracion C0..C6 que haya en `config.yaml`.

El rastro nunca cambia el resultado de una peticion: solo observa.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextvars import ContextVar
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from pydantic import BaseModel, Field

import proxy.auth as auth
import proxy.mecanismos as mecanismos
from proxy.revision_panel import CABECERAS_SEGURIDAD, DIRECTORIO_ESTATICO

logger = logging.getLogger(__name__)

ENV_DEMO = "IRONVEIL_DEMO"
MODELOS_DEMO = ("soporte", "rrhh", "rrhh-agente")
LONGITUD_MAXIMA_MENSAJE = 12_000
VECTOR_DEMO = "DEMO-ataque"

# Quien escucha el rastro de la peticion en curso. Es una ContextVar: cada
# peticion (tarea de asyncio) tiene la suya, asi que peticiones concurrentes no
# se mezclan, y fuera de /demo/chat vale None y `traza()` no hace nada.
_EMISOR: ContextVar[Callable[[dict[str, Any]], None] | None] = ContextVar(
    "ironveil_traza", default=None
)

# (id de etapa, titulo, bandera de config.yaml que la activa o None si siempre).
ETAPAS: tuple[tuple[str, str, str | None], ...] = (
    ("limite", "Límite de peticiones", "aprobacion_humana"),
    ("filtrado:entrada", "Filtro de entrada", "filtrado"),
    ("clasificacion:entrada", "Clasificador de entrada", "clasificacion"),
    ("minimo_privilegio:entrada", "Mínimo privilegio", "minimo_privilegio"),
    ("aprobacion_humana", "Aprobación humana", "aprobacion_humana"),
    ("delimitacion", "Delimitación", "delimitacion"),
    ("modelo", "Modelo", None),
    ("herramientas", "Herramientas del modelo", None),
    ("filtrado:salida", "Filtro de salida", "filtrado"),
    ("clasificacion:salida", "Clasificador de salida", "clasificacion"),
)


def demo_habilitada() -> bool:
    """True si `IRONVEIL_DEMO=1`."""
    return os.environ.get(ENV_DEMO, "").strip() == "1"


def traza(tipo: str, **datos: Any) -> None:
    """Publica un evento del pipeline si hay alguien escuchando; si no, no hace nada.

    Es seguro llamarlo desde cualquier paso: nunca lanza ni altera el flujo.
    """
    emisor = _EMISOR.get()
    if emisor is None:
        return
    try:
        emisor({"tipo": tipo, **datos})
    except Exception:  # noqa: BLE001 - observar nunca debe romper una peticion
        logger.exception("no se pudo emitir el rastro de la demo")


def _exigir_demo() -> None:
    if not demo_habilitada():
        raise HTTPException(status_code=404, detail="No encontrado.")


def _etapas_para(
    config: dict[str, bool], modelo: str, con_herramientas: bool
) -> list[dict[str, Any]]:
    """Etapas que se dibujan para esta peticion, marcando cuales estan activas."""
    etapas: list[dict[str, Any]] = []
    for id_etapa, titulo, bandera in ETAPAS:
        if id_etapa == "herramientas" and not con_herramientas:
            continue
        activa = True if bandera is None else bool(config[bandera])
        etapas.append(
            {
                "id": id_etapa,
                "titulo": titulo if id_etapa != "modelo" else f"Modelo · {modelo}",
                "activa": activa,
            }
        )
    return etapas


class DemoChatRequest(BaseModel):
    modelo: str = Field(min_length=1, max_length=64)
    mensaje: str = Field(min_length=1, max_length=LONGITUD_MAXIMA_MENSAJE)
    # Para el SIEM: con True el evento lleva un vector, y un mensaje que nadie
    # bloquea queda como "exitoso_para_atacante" en vez de "permitido_normal".
    etiquetar_ataque: bool = False


def _linea(evento: dict[str, Any]) -> bytes:
    return (json.dumps(evento, ensure_ascii=False) + "\n").encode("utf-8")


def _resolver_final(
    eventos: list[dict[str, Any]],
    respuesta: dict[str, Any] | None,
    error: HTTPException | None,
) -> dict[str, Any]:
    """Resume como termino la peticion, a partir del rastro y del resultado."""
    etapas = [e for e in eventos if e.get("tipo") == "etapa"]
    bloqueo = next((e for e in etapas if e["estado"] == "bloqueo"), None)
    encolada = next((e for e in etapas if e["estado"] == "encolada"), None)
    nombre = (bloqueo or encolada or {}).get("etapa")
    if error is not None:
        if error.status_code == 429:
            return {"resultado": "en_revision", "etapa": nombre, "texto": ""}
        if error.status_code == 400:
            return {"resultado": "bloqueada", "etapa": nombre, "texto": ""}
        return {"resultado": "error", "etapa": nombre, "texto": ""}
    contenido = (respuesta or {}).get("message", {}).get("content", "")
    herramientas = (respuesta or {}).get("herramientas")
    if herramientas:
        resultado = (
            "herramienta_en_revision"
            if herramientas.get("estado") == "en_revision"
            else "herramienta_denegada"
        )
    elif bloqueo is not None:
        resultado = "retenida"
    else:
        resultado = "respondida"
    modificada = any(e["estado"] == "modificada" for e in etapas)
    return {
        "resultado": resultado,
        "etapa": nombre,
        "texto": contenido,
        "modificada": modificada,
        "herramientas": herramientas,
    }


router = APIRouter()


@router.get("/demo", include_in_schema=False)
def pagina_demo(request: Request) -> Response:
    """Pantalla de chat de la demo (404 si `IRONVEIL_DEMO` no esta activa)."""
    _exigir_demo()
    if auth.auth_habilitada() and auth.sesion_de(request) is None:
        return RedirectResponse("/revision/login", status_code=303)
    return FileResponse(DIRECTORIO_ESTATICO / "demo.html", headers=CABECERAS_SEGURIDAD)


@router.get("/demo/estado", include_in_schema=False)
def estado_demo(
    _: Annotated[auth.Identidad | None, Depends(auth.exigir_lector)],
) -> Response:
    """Configuracion en vigor, para dibujar el encabezado antes del primer mensaje."""
    import proxy.main as main

    _exigir_demo()
    config = mecanismos.cargar_config(mecanismos.CONFIG_PATH)
    activos = main._mecanismos_activos(config)
    return JSONResponse(
        {
            "configuracion": main.determinar_configuracion(activos),
            "mecanismos": {
                nombre: bool(config[nombre]) for nombre in mecanismos.FLAGS_REQUERIDAS
            },
            "modelos": list(MODELOS_DEMO),
            "consola": "/revision/ui",
        },
        headers=CABECERAS_SEGURIDAD,
    )


@router.post("/demo/chat", include_in_schema=False)
async def demo_chat(
    peticion: DemoChatRequest,
    http_request: Request,
    _: Annotated[auth.Identidad | None, Depends(auth.exigir_lector)],
) -> StreamingResponse:
    """Procesa el mensaje con el pipeline real y emite el rastro como NDJSON.

    Cada linea es un JSON: `inicio` (configuracion y etapas), una `etapa` por
    cada paso que se ejecuta, y `fin` (como termino y, si hay, la respuesta).
    """
    import proxy.main as main

    _exigir_demo()
    if peticion.modelo not in MODELOS_DEMO:
        raise HTTPException(status_code=422, detail="Modelo no disponible en la demo.")
    config = mecanismos.cargar_config(mecanismos.CONFIG_PATH)
    activos = main._mecanismos_activos(config)
    cola_eventos: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    eventos: list[dict[str, Any]] = []

    def emitir(evento: dict[str, Any]) -> None:
        eventos.append(evento)
        cola_eventos.put_nowait(evento)

    solicitud = main.ChatRequest(
        modelo=peticion.modelo,
        mensaje=peticion.mensaje,
        vector_probado=VECTOR_DEMO if peticion.etiquetar_ataque else None,
    )

    async def procesar() -> None:
        _EMISOR.set(emitir)  # en esta tarea: es donde corre el pipeline
        respuesta: dict[str, Any] | None = None
        error: HTTPException | None = None
        try:
            respuesta = await main.chat(solicitud, http_request)
        except HTTPException as exc:
            error = exc
            if exc.status_code >= 500:
                emitir({"tipo": "etapa", "etapa": "modelo", "estado": "error"})
        except Exception:  # noqa: BLE001 - la demo no debe filtrar detalles internos
            logger.exception("fallo inesperado en /demo/chat")
            error = HTTPException(status_code=500, detail="Error interno.")
        finally:
            final = _resolver_final(eventos, respuesta, error)
            emitir({"tipo": "fin", **final})
            cola_eventos.put_nowait(None)

    async def flujo() -> AsyncIterator[bytes]:
        yield _linea(
            {
                "tipo": "inicio",
                "configuracion": main.determinar_configuracion(activos),
                "mecanismos": {n: bool(config[n]) for n in mecanismos.FLAGS_REQUERIDAS},
                "etapas": _etapas_para(
                    config,
                    peticion.modelo,
                    main._modelo_con_herramientas(peticion.modelo),
                ),
            }
        )
        tarea = asyncio.create_task(procesar())
        try:
            while True:
                evento = await cola_eventos.get()
                if evento is None:
                    break
                yield _linea(evento)
        finally:
            await tarea

    return StreamingResponse(
        flujo(), media_type="application/x-ndjson", headers=CABECERAS_SEGURIDAD
    )

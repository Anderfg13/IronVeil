"""Proxy FastAPI hacia la API de Ollama (/api/chat), con los mecanismos
defensivos de IronVeil activables por config.yaml.

Con las 5 banderas en false (C0) el comportamiento es passthrough puro,
identico al de la semana anterior. Cadena de mecanismos, orden fijo:
filtrado -> delimitacion -> clasificacion -> minimo_privilegio ->
aprobacion_humana. Cada paso se ejecuta solo si su bandera esta activa;
el primer bloqueo corta la cadena. Ver CLAUDE.md, seccion 3.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import proxy.mecanismos as mecanismos

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
REQUEST_TIMEOUT: float = float(os.getenv("PROXY_REQUEST_TIMEOUT", "120"))
RESULTADOS_DIR: Path = Path(__file__).resolve().parent.parent / "resultados"

# Traduce la lista de mecanismos activos al nombre de configuracion oficial
# (CLAUDE.md, seccion 1). Una combinacion que no sea ninguna de las 7
# oficiales (posible en pruebas de integracion cruzada) se reporta como
# "no_estandar" en vez de forzarla a encajar en C0..C6.
_CONFIGURACIONES_CANONICAS: dict[frozenset[str], str] = {
    frozenset(): "C0",
    frozenset({"filtrado"}): "C1",
    frozenset({"delimitacion"}): "C2",
    frozenset({"clasificacion"}): "C3",
    frozenset({"minimo_privilegio"}): "C4",
    frozenset({"aprobacion_humana"}): "C5",
    frozenset(mecanismos.FLAGS_REQUERIDAS): "C6",
}

app = FastAPI(title="IronVeil Proxy", version="0.1.0")


class ChatRequest(BaseModel):
    modelo: str
    mensaje: str
    # ID de variantes_ataque.md (p. ej. "V3-A") cuando la peticion es parte
    # de una prueba ofensiva. None para trafico legitimo normal: es lo que
    # distingue "exitoso_para_atacante" de "permitido_normal" en el log.
    vector_probado: str | None = None


def determinar_configuracion(activos: list[str]) -> str:
    """Traduce la lista de mecanismos activos al nombre C0..C6.

    Devuelve "no_estandar" si la combinacion no corresponde a ninguna de
    las 7 configuraciones oficiales del experimento.
    """
    return _CONFIGURACIONES_CANONICAS.get(frozenset(activos), "no_estandar")


def _mecanismos_activos(config: dict[str, bool]) -> list[str]:
    return [nombre for nombre in mecanismos.FLAGS_REQUERIDAS if config[nombre]]


def _revisar_entrada(texto: str, config: dict[str, bool]) -> tuple[str, str | None]:
    """Aplica los mecanismos de entrada activos, en el orden fijo del proyecto.

    Devuelve (texto, mecanismo_que_bloqueo); mecanismo_que_bloqueo es None si
    ningun mecanismo bloqueo la peticion.
    """
    if config["filtrado"]:
        texto, bloqueado = mecanismos.filtrar(texto, "entrada")
        if bloqueado:
            return texto, "filtrado"
    return texto, None


def _revisar_salida(texto: str, config: dict[str, bool]) -> tuple[str, str | None]:
    """Aplica los mecanismos de salida activos. Misma forma que _revisar_entrada."""
    if config["filtrado"]:
        texto, redactado = mecanismos.filtrar(texto, "salida")
        if redactado:
            return texto, "filtrado"
    return texto, None


def _determinar_resultado(
    mecanismo_bloqueo: str | None, vector_probado: str | None
) -> str:
    if mecanismo_bloqueo is not None:
        return "bloqueado"
    return "exitoso_para_atacante" if vector_probado else "permitido_normal"


def _registrar_evento(evento: dict[str, Any]) -> None:
    """Agrega una linea a resultados/<fecha>/eventos.jsonl (JSON Lines).

    No pasa por el modulo logging: el evento es una fila del dataset del
    experimento, no un mensaje operativo, y el esquema de log del proyecto
    exige exactamente un objeto JSON por linea (ver skill esquema-log).
    """
    fecha = datetime.now().astimezone().strftime("%Y-%m-%d")
    directorio = RESULTADOS_DIR / fecha
    directorio.mkdir(parents=True, exist_ok=True)
    with (directorio / "eventos.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")


async def _llamar_ollama(modelo: str, mensaje: str) -> dict[str, Any]:
    payload = {
        "model": modelo,
        "messages": [{"role": "user", "content": mensaje}],
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code, detail=exc.response.text
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502, detail=f"No se pudo contactar a Ollama: {exc}"
            ) from exc
    return response.json()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    inicio = time.perf_counter()
    config = mecanismos.cargar_config(mecanismos.CONFIG_PATH)
    activos = _mecanismos_activos(config)

    mensaje, mecanismo_bloqueo = _revisar_entrada(request.mensaje, config)
    respuesta: dict[str, Any] | None = None

    if mecanismo_bloqueo is None:
        respuesta = await _llamar_ollama(request.modelo, mensaje)
        contenido = respuesta.get("message", {}).get("content", "")
        contenido, mecanismo_salida = _revisar_salida(contenido, config)
        if mecanismo_salida:
            respuesta["message"]["content"] = contenido
            mecanismo_bloqueo = mecanismo_salida

    resultado = _determinar_resultado(mecanismo_bloqueo, request.vector_probado)
    latencia_ms = int((time.perf_counter() - inicio) * 1000)

    _registrar_evento(
        {
            "timestamp": datetime.now().astimezone().isoformat(),
            "configuracion": determinar_configuracion(activos),
            "mecanismos_activos": activos,
            "vector_probado": request.vector_probado,
            "modelo_destino": request.modelo,
            "resultado": resultado,
            "mecanismo_que_bloqueo": mecanismo_bloqueo,
            "latencia_ms": latencia_ms,
        }
    )

    if respuesta is None:
        logger.warning(
            "peticion bloqueada en entrada por %s (modelo=%s)",
            mecanismo_bloqueo,
            request.modelo,
        )
        raise HTTPException(
            status_code=400,
            detail="Solicitud bloqueada por los mecanismos de defensa activos.",
        )

    return respuesta

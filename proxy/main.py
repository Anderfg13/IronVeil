"""Proxy FastAPI passthrough hacia la API de Ollama (/api/chat).

Sin logica de mecanismos defensivos todavia: reenvia la peticion tal cual
y devuelve la respuesta de Ollama sin modificarla.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
REQUEST_TIMEOUT: float = float(os.getenv("PROXY_REQUEST_TIMEOUT", "120"))

app = FastAPI(title="IronVeil Proxy", version="0.1.0")


class ChatRequest(BaseModel):
    modelo: str
    mensaje: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    payload = {
        "model": request.modelo,
        "messages": [{"role": "user", "content": request.mensaje}],
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

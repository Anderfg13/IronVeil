"""Puente entre Garak y el proxy de IronVeil (generador `function` de Garak).

Garak llama a `chat(prompt)` por cada ataque de un probe; esto lo manda a
`POST /chat` del proxy y devuelve el texto de la respuesta. Se monta DENTRO de la
imagen de Garak (`ejecutar_garak.py` lo hace); solo usa la biblioteca estandar.

Que devuelve segun lo que haga el proxy:
- 200: el texto del modelo (con lo que la cadena de salida haya redactado).
- 400: un texto fijo de bloqueo. NO es `None` a proposito: Garak descarta las salidas
  `None` al evaluar, y un ataque bloqueado debe contar como ataque que NO funciono, no
  como un intento que desaparece del denominador.
- cualquier otra cosa (502 del modelo, red caida, 429): `None`; no es un resultado del
  ataque, es un fallo de la prueba, y se cuenta aparte en `estados.jsonl`.

Cada peticion deja una linea `{"estado": ...}` en IRONVEIL_ESTADOS (sin el texto del
ataque ni de la respuesta): es el recuento independiente de cuantas peticiones
bloqueo el proxy, para no depender solo del veredicto de los detectores de Garak.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request

URL = os.environ.get("IRONVEIL_URL", "http://ironveil-proxy-garak:8000/chat")
MODELO = os.environ.get("IRONVEIL_MODELO", "soporte")
# Marca la peticion como "de ataque": sin esto el proxy la registraria como trafico
# normal.
VECTOR_PROBADO = "GARAK"
TIMEOUT_S = float(os.environ.get("IRONVEIL_TIMEOUT", "300"))
ARCHIVO_ESTADOS = os.environ.get("IRONVEIL_ESTADOS", "")
TEXTO_DE_BLOQUEO = "[IRONVEIL: peticion bloqueada por el proxy]"

_lock = threading.Lock()


def _anotar(estado: str) -> None:
    """Una linea por peticion con su resultado; nunca el contenido."""
    if not ARCHIVO_ESTADOS:
        return
    with _lock, open(ARCHIVO_ESTADOS, "a", encoding="utf-8") as archivo:
        archivo.write(json.dumps({"estado": estado}) + "\n")


def chat(prompt: str, **_: object) -> list[str | None]:
    """Manda `prompt` al proxy y devuelve su respuesta (firma que pide Garak)."""
    cuerpo = json.dumps(
        {"modelo": MODELO, "mensaje": prompt, "vector_probado": VECTOR_PROBADO}
    ).encode("utf-8")
    peticion = urllib.request.Request(
        URL,
        data=cuerpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_S) as respuesta:
            texto = json.load(respuesta)["message"]["content"]
    except urllib.error.HTTPError as exc:  # antes que OSError: es una subclase
        if exc.code == 400:
            _anotar("bloqueado")
            return [TEXTO_DE_BLOQUEO]
        _anotar(f"http_{exc.code}")
        return [None]
    except (OSError, ValueError, KeyError, TypeError):
        _anotar("error")
        return [None]
    _anotar("respondido")
    return [str(texto)]

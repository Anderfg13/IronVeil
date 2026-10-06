"""Adaptador del MODELO PROTEGIDO: el que responde, no el que clasifica.

Hasta aqui el proxy solo hablaba con Ollama. Este modulo le permite proteger tambien un
modelo servido por otra API (`openai`: cualquier API tipo chat/completions, local o de
un proveedor; `anthropic`: la API de mensajes) y devuelve **la misma forma que Ollama**
(`{"message": {"role", "content"}}`), asi que la cadena de salida, la respuesta al
cliente y los 5 mecanismos no cambian: actuan antes y despues de esta llamada.

Se declara en `MODELOS_REMOTOS` (un objeto JSON, sin secretos):

    {"asistente-nube": {"backend": "anthropic", "modelo": "<id en el proveedor>",
                        "sistema_archivo": "/app/sistemas/asistente.txt"}}

El nombre es el que manda el cliente en `modelo`. Campos: `backend` y `modelo`
(obligatorios); `url_base`, `clave_env` (nombre de la variable que guarda la clave),
`sistema` o `sistema_archivo` (el system prompt, con `${VARIABLE}` expandidas desde el
entorno: asi un canario no se escribe en el codigo ni en el JSON) y `parametros` (objeto
que reemplaza los del cuerpo, p. ej. `max_tokens`). Un campo desconocido es un error.

Reglas (CLAUDE.md, secciones 2 y 7):
- **A donde va el texto** (`destino`): `local`, `propio` (hosts de
  `MODELO_PROTEGIDO_HOSTS_PROPIOS`) o `tercero`. Un tercero esta APAGADO salvo
  `MODELO_PROTEGIDO_PERMITIR_TERCEROS=1`: ademas del texto del usuario recibe el system
  prompt completo, canario incluido. Fuera de esta maquina se exige HTTPS y clave.
- Claves solo en el entorno (`.env`); TLS siempre verificado; ni claves ni el texto del
  usuario ni el cuerpo de error del proveedor van al log.
- Un fallo nunca devuelve algo parecido a una respuesta: el endpoint contesta un 502
  generico (el detalle va al log del servidor).
- No hay herramientas simuladas con un modelo remoto (la extension de Excessive Agency
  usa el formato de Ollama).

Limite para quien analice resultados: un modelo de frontera trae su propio entrenamiento
de seguridad, asi que sus resultados NO son comparables con C0-C6 de los modelos
locales. Por eso los eventos de un modelo remoto se marcan `es_extension` y no entran en
el nucleo. Guia: docs/MODELO_PROTEGIDO_REMOTO.md.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

import proxy.adaptador_clasificador as adaptador
from proxy.adaptador_clasificador import (
    DESTINO_LOCAL,
    DESTINO_TERCERO,
    ESTADO_OK,
    ErrorConfiguracion,
)
from proxy.backends_entrada import estado_de_excepcion

logger = logging.getLogger(__name__)

MODELOS_REMOTOS: str = os.getenv("MODELOS_REMOTOS", "")
MODELO_PROTEGIDO_HOSTS_PROPIOS: str = os.getenv("MODELO_PROTEGIDO_HOSTS_PROPIOS", "")
# Permiso expreso para enviar el prompt completo (con el system prompt) a un TERCERO.
MODELO_PROTEGIDO_PERMITIR_TERCEROS: bool = (
    os.getenv("MODELO_PROTEGIDO_PERMITIR_TERCEROS", "") == "1"
)

BACKENDS_REMOTOS = ("openai", "anthropic")
_URL_POR_DEFECTO = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
}
_CLAVE_POR_DEFECTO = {
    "openai": "MODELO_PROTEGIDO_OPENAI_API_KEY",
    "anthropic": "MODELO_PROTEGIDO_ANTHROPIC_API_KEY",
}
# `max_tokens` es obligatorio en la API de Anthropic.
_PARAMETROS_POR_DEFECTO: dict[str, dict[str, Any]] = {
    "openai": {},
    "anthropic": {"max_tokens": 1024},
}
_CAMPOS = frozenset(
    {
        "backend",
        "modelo",
        "url_base",
        "clave_env",
        "sistema",
        "sistema_archivo",
        "parametros",
    }
)
_NOMBRE_VALIDO = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class ModeloRemoto:
    """Un modelo protegido servido por una API (entrada de `MODELOS_REMOTOS`)."""

    nombre: str  # el que manda el cliente en `modelo`
    backend: str  # "openai" | "anthropic"
    modelo: str  # el id del modelo en el proveedor
    url_base: str
    clave_env: str  # nombre de la variable de entorno con la clave
    sistema: str | None
    sistema_archivo: str | None
    parametros: dict[str, Any]


@dataclass(frozen=True)
class DetalleModelo:
    """Que modelo respondio (bloque `modelo_protegido` del evento). Sin texto."""

    backend: str
    modelo: str
    destino: str
    estado: str = ESTADO_OK

    def como_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "")}


def _texto_opcional(entrada: dict[str, Any], campo: str, nombre: str) -> str | None:
    valor = entrada.get(campo)
    if valor is None:
        return None
    if not isinstance(valor, str) or not valor.strip():
        raise ErrorConfiguracion(f"MODELOS_REMOTOS[{nombre!r}].{campo} debe ser texto.")
    return valor


def _construir(nombre: str, entrada: Any) -> ModeloRemoto:
    """Valida una entrada de `MODELOS_REMOTOS`; un error de forma es de config."""
    if not _NOMBRE_VALIDO.match(nombre):
        raise ErrorConfiguracion(
            f"Nombre de modelo remoto invalido {nombre!r}: letras, numeros, . _ -"
        )
    if not isinstance(entrada, dict):
        raise ErrorConfiguracion(f"MODELOS_REMOTOS[{nombre!r}] debe ser un objeto.")
    sobrantes = sorted(set(entrada) - _CAMPOS)
    if sobrantes:
        raise ErrorConfiguracion(
            f"MODELOS_REMOTOS[{nombre!r}] tiene campos desconocidos: {sobrantes}."
        )
    backend = entrada.get("backend")
    if backend not in BACKENDS_REMOTOS:
        raise ErrorConfiguracion(
            f"MODELOS_REMOTOS[{nombre!r}].backend debe ser uno de {BACKENDS_REMOTOS}."
        )
    modelo = _texto_opcional(entrada, "modelo", nombre)
    if modelo is None:
        raise ErrorConfiguracion(f"MODELOS_REMOTOS[{nombre!r}] necesita 'modelo'.")
    sistema = _texto_opcional(entrada, "sistema", nombre)
    sistema_archivo = _texto_opcional(entrada, "sistema_archivo", nombre)
    if sistema is not None and sistema_archivo is not None:
        raise ErrorConfiguracion(
            f"MODELOS_REMOTOS[{nombre!r}]: usa solo uno: 'sistema' o 'sistema_archivo'."
        )
    parametros = entrada.get("parametros", _PARAMETROS_POR_DEFECTO[backend])
    if not isinstance(parametros, dict):
        raise ErrorConfiguracion(
            f"MODELOS_REMOTOS[{nombre!r}].parametros: objeto JSON."
        )
    if backend == "anthropic" and "max_tokens" not in parametros:
        raise ErrorConfiguracion(
            f"MODELOS_REMOTOS[{nombre!r}]: anthropic exige 'max_tokens' en parametros."
        )
    return ModeloRemoto(
        nombre=nombre,
        backend=backend,
        modelo=modelo,
        url_base=_texto_opcional(entrada, "url_base", nombre)
        or _URL_POR_DEFECTO[backend],
        clave_env=_texto_opcional(entrada, "clave_env", nombre)
        or _CLAVE_POR_DEFECTO[backend],
        sistema=sistema,
        sistema_archivo=sistema_archivo,
        parametros=dict(parametros),
    )


@functools.cache
def cargar_modelos_remotos(texto: str) -> dict[str, ModeloRemoto]:
    """Los modelos de `MODELOS_REMOTOS` por nombre. Falla ruidosamente si esta mal."""
    if not texto.strip():
        return {}
    try:
        datos = json.loads(texto)
    except ValueError as exc:
        raise ErrorConfiguracion("MODELOS_REMOTOS no es JSON valido.") from exc
    if not isinstance(datos, dict):
        raise ErrorConfiguracion("MODELOS_REMOTOS debe ser un objeto JSON.")
    return {nombre: _construir(nombre, entrada) for nombre, entrada in datos.items()}


def resolver(nombre: str) -> ModeloRemoto | None:
    """El modelo remoto con ese nombre, o None si lo atiende Ollama.

    Lanza ErrorConfiguracion si `MODELOS_REMOTOS` esta mal formado.
    """
    return cargar_modelos_remotos(MODELOS_REMOTOS).get(nombre)


def es_remoto(nombre: str) -> bool:
    """True si `nombre` es un modelo remoto (False tambien si la config esta rota)."""
    try:
        return resolver(nombre) is not None
    except ErrorConfiguracion:
        return False


def clasificar_destino(url: str) -> str:
    """`local`, `propio` o `tercero` para `url` (usa MODELO_PROTEGIDO_HOSTS_PROPIOS)."""
    return adaptador.clasificar_destino(
        url, adaptador.parsear_hosts(MODELO_PROTEGIDO_HOSTS_PROPIOS)
    )


def detalle_ollama(modelo: str, url_base: str) -> DetalleModelo:
    """El detalle de un modelo que atiende Ollama (el caso de siempre)."""
    return DetalleModelo("ollama", modelo, clasificar_destino(url_base))


@functools.cache
def _avisar_destino_externo(url: str, destino: str) -> None:
    """Deja constancia (una vez por destino) de que el prompt sale de esta maquina."""
    if destino == DESTINO_TERCERO:
        logger.warning(
            "Modelo protegido de un TERCERO: cada prompt (con su system prompt) "
            "se envia a %s, fuera del laboratorio.",
            url,
        )
    else:
        logger.info("Modelo protegido propio: cada prompt se envia a %s.", url)


def _autorizar(url: str) -> str:
    """El destino de `url` si enviarle el prompt esta permitido (si no, error)."""
    destino = clasificar_destino(url)
    if destino == DESTINO_LOCAL:
        return destino
    if urlparse(url).scheme != "https":
        raise ErrorConfiguracion(
            "Un modelo fuera de esta maquina debe usar https (TLS siempre verificado)."
        )
    if destino == DESTINO_TERCERO and not MODELO_PROTEGIDO_PERMITIR_TERCEROS:
        raise ErrorConfiguracion(
            f"{urlparse(url).hostname} es de un tercero: enviarle el prompt completo, "
            "con el system prompt, lo saca del laboratorio. Si es de tu organizacion, "
            "declaralo en MODELO_PROTEGIDO_HOSTS_PROPIOS; si no, activalo con "
            "MODELO_PROTEGIDO_PERMITIR_TERCEROS=1 solo con aprobacion del equipo "
            "(docs/MODELO_PROTEGIDO_REMOTO.md)."
        )
    _avisar_destino_externo(url, destino)
    return destino


def _clave(modelo: ModeloRemoto, destino: str) -> str | None:
    """La clave del entorno; sin ella solo se admite un destino local."""
    clave = os.environ.get(modelo.clave_env, "").strip()
    if not clave and destino != DESTINO_LOCAL:
        raise ErrorConfiguracion(f"Falta {modelo.clave_env} en el entorno (.env).")
    return clave or None


def _expandir(texto: str, origen: str) -> str:
    """Sustituye `${VARIABLE}` desde el entorno; una variable ausente es un error."""

    def reemplazo(coincidencia: re.Match[str]) -> str:
        valor = os.environ.get(coincidencia.group(1), "")
        if not valor:
            raise ErrorConfiguracion(
                f"{origen} usa ${{{coincidencia.group(1)}}}, que no esta definida."
            )
        return valor

    return _VARIABLE.sub(reemplazo, texto)


def construir_sistema(modelo: ModeloRemoto) -> str | None:
    """El system prompt del modelo (con las variables ya expandidas), o None.

    Con un modelo local el system prompt vive en el Modelfile; con una API hay que
    enviarlo en cada peticion.
    """
    origen = f"El system prompt de {modelo.nombre}"
    if modelo.sistema is not None:
        return _expandir(modelo.sistema, origen)
    if modelo.sistema_archivo is not None:
        try:
            texto = Path(modelo.sistema_archivo).read_text(encoding="utf-8")
        except OSError as exc:
            raise ErrorConfiguracion(f"{origen}: no se pudo leer el archivo.") from exc
        return _expandir(texto, origen)
    return None


def _texto_de_openai(datos: Any) -> str:
    mensaje = datos["choices"][0]["message"]
    contenido = mensaje.get("content") or mensaje.get(
        "refusal"
    )  # un rechazo es respuesta
    if not isinstance(contenido, str):
        raise TypeError("la respuesta no trae texto")
    return contenido


def _texto_de_anthropic(datos: Any) -> str:
    bloques = datos["content"]
    if not isinstance(bloques, list):
        raise TypeError("la respuesta no trae bloques de contenido")
    partes = [b["text"] for b in bloques if b.get("type") == "text"]
    if not partes or not all(isinstance(p, str) for p in partes):
        raise ValueError("la respuesta no trae texto")
    return "".join(partes)


def _url(modelo: ModeloRemoto) -> str:
    """La direccion del endpoint de chat de la API del proveedor."""
    ruta = "/chat/completions" if modelo.backend == "openai" else "/v1/messages"
    return modelo.url_base.rstrip("/") + ruta


def _cuerpo_y_cabeceras(
    modelo: ModeloRemoto, mensaje: str, sistema: str | None, clave: str | None
) -> tuple[dict[str, Any], dict[str, str]]:
    """(cuerpo, cabeceras) de la peticion a la API del proveedor."""
    if modelo.backend == "openai":
        mensajes = [{"role": "user", "content": mensaje}]
        if sistema:
            mensajes.insert(0, {"role": "system", "content": sistema})
        cuerpo = {"model": modelo.modelo, "messages": mensajes, **modelo.parametros}
        return cuerpo, ({"Authorization": f"Bearer {clave}"} if clave else {})
    cuerpo = {
        "model": modelo.modelo,
        "messages": [{"role": "user", "content": mensaje}],
        **modelo.parametros,
    }
    if sistema:
        cuerpo["system"] = sistema
    cabeceras = {"anthropic-version": "2023-06-01"}
    if clave:
        cabeceras["x-api-key"] = clave
    return cuerpo, cabeceras


async def llamar(
    cliente: httpx.AsyncClient, modelo: ModeloRemoto, mensaje: str
) -> tuple[dict[str, Any], DetalleModelo]:
    """Envia `mensaje` al modelo remoto: (respuesta con forma de Ollama, detalle).

    Lanza ErrorConfiguracion (destino no permitido, clave o variable ausente),
    httpx.HTTPError (red, timeout, 4xx/5xx) o KeyError/IndexError/TypeError/ValueError
    (respuesta con otra forma); quien llama la convierte en un error generico. El campo
    `model` de la respuesta es el nombre que uso el cliente, no el id del proveedor.
    """
    url = _url(modelo)
    destino = _autorizar(url)
    clave = _clave(modelo, destino)
    cuerpo, cabeceras = _cuerpo_y_cabeceras(
        modelo, mensaje, construir_sistema(modelo), clave
    )
    respuesta = await cliente.post(url, json=cuerpo, headers=cabeceras)
    respuesta.raise_for_status()
    datos = respuesta.json()
    leer = _texto_de_openai if modelo.backend == "openai" else _texto_de_anthropic
    resultado = {
        "model": modelo.nombre,
        "message": {"role": "assistant", "content": leer(datos)},
        "done": True,
    }
    return resultado, DetalleModelo(modelo.backend, modelo.modelo, destino)


def estado(exc: BaseException) -> str:
    """Motivo, en una palabra, de un fallo al llamar al modelo (para el log)."""
    return estado_de_excepcion(exc)

"""Transporte HTTPS generico: un POST por evento.

Una sola clase cubre a Splunk (HEC), Elastic/OpenSearch, Azure Monitor y cualquier
webhook, porque lo que cambia entre ellos son tres cosas pequenas que se inyectan: la
URL, las cabeceras de autorizacion y como se envuelve el mensaje. Cada SIEM concreto es
una funcion fabrica en su propio modulo (open/closed: sumar uno no toca esta clase).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import httpx

from proxy.siem.puertos import ConectorSIEM, ErrorSIEM
from proxy.siem.registro import ContextoConector

# Cabeceras de autorizacion de ESTE envio. Es una funcion y no un valor porque algunas
# caducan (el token de Azure se renueva): se le pide en cada envio.
ProveedorCabeceras = Callable[[], Mapping[str, str]]
Envoltura = Callable[[str], str]

TIMEOUT_POR_DEFECTO = 10.0
_ESTADOS_REINTENTABLES = frozenset({408, 425, 429})


def sin_autorizacion() -> Mapping[str, str]:
    """Para los destinos que no piden credenciales."""
    return {}


def tal_cual(mensaje: str) -> str:
    """Envoltura por defecto: el cuerpo es el mensaje."""
    return mensaje


def cliente_httpx(timeout: float = TIMEOUT_POR_DEFECTO) -> httpx.Client:
    """Cliente con la verificacion TLS activa (nunca `verify=False`) y sin seguir
    redirecciones: una redireccion podria llevar la clave a otro servidor."""
    return httpx.Client(timeout=timeout, verify=True, follow_redirects=False)


def error_por_estado(destino: str, estado: int) -> ErrorSIEM:
    """El `ErrorSIEM` de una respuesta no exitosa. Nunca lleva el cuerpo de la
    respuesta (podria repetir la peticion) ni la URL (puede traer identificadores)."""
    reintentable = estado >= 500 or estado in _ESTADOS_REINTENTABLES
    return ErrorSIEM(f"{destino} respondio HTTP {estado}", reintentable=reintentable)


class ConectorHTTP:
    """POST de `envoltura(mensaje)` a `url`, con las cabeceras de `autorizacion`."""

    def __init__(
        self,
        url: str,
        *,
        nombre: str,
        tipo_contenido: str,
        autorizacion: ProveedorCabeceras = sin_autorizacion,
        cabeceras_fijas: Mapping[str, str] | None = None,
        envoltura: Envoltura = tal_cual,
        cliente: httpx.Client | None = None,
        cliente_propio: bool = False,
    ) -> None:
        if not url.startswith("https://"):
            raise ErrorSIEM(
                f"{nombre}: el destino debe ser https:// (los eventos de seguridad no "
                "viajan sin cifrar)",
                reintentable=False,
            )
        self._url = url
        self._nombre = nombre
        self._tipo_contenido = tipo_contenido
        self._autorizacion = autorizacion
        self._fijas = dict(cabeceras_fijas or {})
        self._envoltura = envoltura
        # Un cliente inyectado es de quien lo inyecta, salvo que diga que se le cede.
        self._cliente = cliente or cliente_httpx()
        self._es_dueno_del_cliente = cliente is None or cliente_propio

    def enviar(self, mensaje: str) -> None:
        cabeceras = {"Content-Type": self._tipo_contenido, **self._fijas}
        cabeceras.update(self._autorizacion())
        try:
            respuesta = self._cliente.post(
                self._url,
                content=self._envoltura(mensaje).encode("utf-8"),
                headers=cabeceras,
            )
        except httpx.HTTPError as exc:
            raise ErrorSIEM(
                f"{self._nombre}: fallo de red ({type(exc).__name__})"
            ) from exc
        if not respuesta.is_success:
            raise error_por_estado(self._nombre, respuesta.status_code)

    def cerrar(self) -> None:
        if self._es_dueno_del_cliente:
            self._cliente.close()


def fabrica_https(destino: str, contexto: ContextoConector) -> ConectorSIEM:
    """`https://host/ruta`: un webhook.

    Si hay `SIEM_HTTPS_TOKEN`, el token va como portador (`Authorization: Bearer`).
    """
    if "@" in destino:
        raise ErrorSIEM(
            "no pongas credenciales en la URL: usa SIEM_HTTPS_TOKEN",
            reintentable=False,
        )
    token = contexto.entorno.get("SIEM_HTTPS_TOKEN", "").strip()
    autorizacion = (
        (lambda: {"Authorization": f"Bearer {token}"}) if token else sin_autorizacion
    )
    return ConectorHTTP(
        f"https://{destino.strip()}",
        nombre="HTTPS",
        tipo_contenido=contexto.tipo_contenido,
        autorizacion=autorizacion,
    )

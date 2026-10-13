"""Microsoft Azure Monitor / Sentinel (API de ingesta de registros):
`azure-logs://<host del DCE o DCR>/<id inmutable del DCR>/<nombre del stream>`.

Un POST por evento a `{host}/dataCollectionRules/{dcr}/streams/{stream}` con el evento
dentro de un arreglo JSON, y un token de portador obtenido con el flujo de credenciales
de cliente de Microsoft Entra ID. Necesita en Azure una app registrada con el rol
"Monitoring Metrics Publisher" sobre el DCR, y un DCR cuyo stream acepte el JSON del
formato elegido (por defecto `json`; el DCR puede transformarlo con KQL).

Variables: SIEM_AZURE_TENANT_ID, SIEM_AZURE_CLIENT_ID, SIEM_AZURE_CLIENT_SECRET y,
solo si no es la nube publica, SIEM_AZURE_ALCANCE y SIEM_AZURE_AUTORIDAD.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Mapping
from urllib.parse import quote

import httpx

from proxy.siem.puertos import ConectorSIEM, ErrorSIEM
from proxy.siem.registro import ContextoConector
from proxy.siem.transportes.credenciales import requerir, separar_host_puerto
from proxy.siem.transportes.https_generico import (
    TIMEOUT_POR_DEFECTO,
    ConectorHTTP,
    cliente_httpx,
)

VERSION_API = "2023-01-01"
ALCANCE_POR_DEFECTO = "https://monitor.azure.com/.default"
AUTORIDAD_POR_DEFECTO = "https://login.microsoftonline.com"
_MARGEN_RENOVACION_S = 60
_TENANT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,127}$")
_SEGMENTO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ProveedorTokenAzure:
    """Obtiene y renueva el token de portador (flujo de credenciales de cliente).

    El token se guarda en memoria hasta poco antes de caducar; ni el token ni el secreto
    aparecen en un mensaje de error.
    """

    def __init__(
        self,
        *,
        autoridad: str,
        tenant: str,
        client_id: str,
        client_secret: str,
        alcance: str,
        cliente: httpx.Client,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        if not autoridad.startswith("https://"):
            raise ErrorSIEM(
                "SIEM_AZURE_AUTORIDAD debe ser https://", reintentable=False
            )
        if not _TENANT.match(tenant):
            raise ErrorSIEM("SIEM_AZURE_TENANT_ID no es valido", reintentable=False)
        self._url = f"{autoridad.rstrip('/')}/{tenant}/oauth2/v2.0/token"
        self._formulario = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": alcance,
        }
        self._cliente = cliente
        self._reloj = reloj
        self._token: str | None = None
        self._caduca = 0.0
        self._lock = threading.Lock()

    def __call__(self) -> Mapping[str, str]:
        with self._lock:
            if self._token is None or self._reloj() >= self._caduca:
                self._renovar()
            return {"Authorization": f"Bearer {self._token}"}

    def _renovar(self) -> None:
        try:
            respuesta = self._cliente.post(self._url, data=self._formulario)
        except httpx.HTTPError as exc:
            raise ErrorSIEM(
                f"Azure: no se pudo pedir el token ({type(exc).__name__})"
            ) from exc
        if not respuesta.is_success:
            # 400/401: tenant, id o secreto incorrectos. No se repite: no cambiara.
            raise ErrorSIEM(
                f"Azure: el token se rechazo (HTTP {respuesta.status_code})",
                reintentable=respuesta.status_code >= 500,
            )
        try:
            cuerpo = respuesta.json()
            self._token = str(cuerpo["access_token"])
            vigencia = float(cuerpo.get("expires_in", 0))
        except (ValueError, KeyError, TypeError) as exc:
            raise ErrorSIEM("Azure: respuesta de token inesperada") from exc
        self._caduca = self._reloj() + max(0.0, vigencia - _MARGEN_RENOVACION_S)


def _en_arreglo(mensaje: str) -> str:
    """La API pide un arreglo JSON: el evento (un objeto) va como unico elemento."""
    return f"[{mensaje}]"


def fabrica_azure(destino: str, contexto: ContextoConector) -> ConectorSIEM:
    """`host/dcr-id/stream`."""
    partes = destino.split("/")
    if len(partes) != 3 or not all(_SEGMENTO.match(p) for p in partes[1:]):
        raise ErrorSIEM(
            "destino de Azure no valido: azure-logs://host/id-del-DCR/nombre-del-stream",
            reintentable=False,
        )
    host, puerto = separar_host_puerto(partes[0], puerto_por_defecto=443)
    _, dcr, stream = partes
    entorno = contexto.entorno
    datos = requerir(
        entorno,
        "SIEM_AZURE_TENANT_ID",
        "SIEM_AZURE_CLIENT_ID",
        "SIEM_AZURE_CLIENT_SECRET",
    )
    cliente = cliente_httpx(TIMEOUT_POR_DEFECTO)
    proveedor = ProveedorTokenAzure(
        autoridad=entorno.get("SIEM_AZURE_AUTORIDAD", "").strip()
        or AUTORIDAD_POR_DEFECTO,
        tenant=datos["SIEM_AZURE_TENANT_ID"],
        client_id=datos["SIEM_AZURE_CLIENT_ID"],
        client_secret=datos["SIEM_AZURE_CLIENT_SECRET"],
        alcance=entorno.get("SIEM_AZURE_ALCANCE", "").strip() or ALCANCE_POR_DEFECTO,
        cliente=cliente,
    )
    return ConectorHTTP(
        f"https://{host}:{puerto}/dataCollectionRules/{quote(dcr)}"
        f"/streams/{quote(stream)}?api-version={VERSION_API}",
        nombre="Azure Monitor",
        tipo_contenido="application/json",
        autorizacion=proveedor,
        envoltura=_en_arreglo,
        cliente=cliente,
        cliente_propio=True,
    )

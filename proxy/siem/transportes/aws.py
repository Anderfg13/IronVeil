"""Amazon CloudWatch Logs (PutLogEvents): `aws-cloudwatch://region/grupo/flujo`.

Un POST firmado con SigV4 por evento. El grupo y el flujo de registro deben existir
ya; el nombre del grupo puede llevar `/` y se escribe codificado, por ejemplo
`%2Fironveil%2Fproxy`. Credenciales: las variables estandar `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY` y, si son temporales, `AWS_SESSION_TOKEN`. Los roles de
instancia / IAM Identity Center NO se resuelven aqui (haria falta el SDK completo):
usa claves de un usuario IAM con permiso `logs:PutLogEvents`.

No cubre Security Lake: recibe OCSF en Parquet por S3, otro tipo de integracion.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import unquote

import httpx

from proxy.siem.puertos import ConectorSIEM, ErrorSIEM
from proxy.siem.registro import ContextoConector
from proxy.siem.transportes.credenciales import requerir
from proxy.siem.transportes.https_generico import cliente_httpx, error_por_estado
from proxy.siem.transportes.sigv4 import CredencialesAWS, firmar

_REGION = re.compile(r"^[a-z]{2}(-[a-z]+)+-\d$")
_GRUPO = re.compile(r"^[.\-_/#A-Za-z0-9]{1,512}$")
_FLUJO = re.compile(r"^[^:*]{1,512}$")
_OBJETIVO = "Logs_20140328.PutLogEvents"
_TIPO = "application/x-amz-json-1.1"


def _ahora_utc() -> datetime:
    return datetime.now(UTC)


class ConectorCloudWatch:
    """Escribe cada mensaje como un evento de un flujo de CloudWatch Logs."""

    def __init__(
        self,
        *,
        region: str,
        grupo: str,
        flujo: str,
        credenciales: CredencialesAWS,
        cliente: httpx.Client | None = None,
        reloj: Callable[[], datetime] = _ahora_utc,
    ) -> None:
        self._host = f"logs.{region}.amazonaws.com"
        self._region = region
        self._grupo = grupo
        self._flujo = flujo
        self._credenciales = credenciales
        self._cliente = cliente or cliente_httpx()
        self._es_dueno_del_cliente = cliente is None
        self._reloj = reloj

    def enviar(self, mensaje: str) -> None:
        instante = self._reloj()
        cuerpo = json.dumps(
            {
                "logGroupName": self._grupo,
                "logStreamName": self._flujo,
                "logEvents": [
                    {
                        "timestamp": int(instante.timestamp() * 1000),
                        "message": mensaje,
                    }
                ],
            }
        ).encode("utf-8")
        cabeceras = {"Content-Type": _TIPO, "X-Amz-Target": _OBJETIVO}
        cabeceras.update(
            firmar(
                metodo="POST",
                host=self._host,
                ruta="/",
                consulta="",
                cabeceras=cabeceras,
                cuerpo=cuerpo,
                region=self._region,
                servicio="logs",
                credenciales=self._credenciales,
                ahora=instante,
            )
        )
        try:
            respuesta = self._cliente.post(
                f"https://{self._host}/", content=cuerpo, headers=cabeceras
            )
        except httpx.HTTPError as exc:
            raise ErrorSIEM(f"CloudWatch: fallo de red ({type(exc).__name__})") from exc
        if not respuesta.is_success:
            raise error_por_estado("CloudWatch", respuesta.status_code)

    def cerrar(self) -> None:
        if self._es_dueno_del_cliente:
            self._cliente.close()


def fabrica_cloudwatch(destino: str, contexto: ContextoConector) -> ConectorSIEM:
    """`region/grupo/flujo` (grupo y flujo con codificacion porcentual)."""
    partes = destino.split("/")
    if len(partes) != 3:
        raise ErrorSIEM(
            "destino de CloudWatch no valido: aws-cloudwatch://region/grupo/flujo",
            reintentable=False,
        )
    region, grupo, flujo = partes[0], unquote(partes[1]), unquote(partes[2])
    if not _REGION.match(region):
        raise ErrorSIEM(f"region de AWS no valida: {region!r}", reintentable=False)
    if not _GRUPO.match(grupo) or not _FLUJO.match(flujo):
        raise ErrorSIEM("grupo o flujo de CloudWatch no validos", reintentable=False)
    datos = requerir(contexto.entorno, "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
    return ConectorCloudWatch(
        region=region,
        grupo=grupo,
        flujo=flujo,
        credenciales=CredencialesAWS(
            clave_acceso=datos["AWS_ACCESS_KEY_ID"],
            clave_secreta=datos["AWS_SECRET_ACCESS_KEY"],
            token_sesion=contexto.entorno.get("AWS_SESSION_TOKEN", "").strip() or None,
        ),
    )

"""Firma AWS Signature Version 4, solo con la biblioteca estandar.

Funcion pura (sin red, sin reloj, sin entorno): recibe la hora y las claves y devuelve
las cabeceras que hay que enviar. Asi se prueba contra los vectores publicados por AWS
y no hace falta el SDK completo (`boto3`) para firmar una unica llamada.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import quote

_ALGORITMO = "AWS4-HMAC-SHA256"


@dataclass(frozen=True)
class CredencialesAWS:
    """Claves de acceso. Nunca aparecen en `repr()` ni en un traceback."""

    clave_acceso: str
    clave_secreta: str = field(repr=False)
    token_sesion: str | None = field(default=None, repr=False)


def _sha256_hex(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _hmac(clave: bytes, mensaje: str) -> bytes:
    return hmac.new(clave, mensaje.encode("utf-8"), hashlib.sha256).digest()


def _clave_de_firma(
    clave_secreta: str, fecha: str, region: str, servicio: str
) -> bytes:
    clave = _hmac(f"AWS4{clave_secreta}".encode(), fecha)
    for parte in (region, servicio, "aws4_request"):
        clave = _hmac(clave, parte)
    return clave


def firmar(
    *,
    metodo: str,
    host: str,
    ruta: str,
    consulta: str,
    cabeceras: Mapping[str, str],
    cuerpo: bytes,
    region: str,
    servicio: str,
    credenciales: CredencialesAWS,
    ahora: datetime,
) -> dict[str, str]:
    """Las cabeceras de firma (`Authorization`, `X-Amz-Date` y, si hay, el token de
    sesion) para una peticion. `cabeceras` son las demas que se enviaran y se firman
    tambien; `consulta` ya viene ordenada y codificada (vacia si no hay)."""
    instante = ahora.astimezone(UTC)
    marca = instante.strftime("%Y%m%dT%H%M%SZ")
    fecha = marca[:8]

    a_firmar = {k.lower(): " ".join(str(v).split()) for k, v in cabeceras.items()}
    a_firmar["host"] = host
    a_firmar["x-amz-date"] = marca
    if credenciales.token_sesion:
        a_firmar["x-amz-security-token"] = credenciales.token_sesion
    nombres = sorted(a_firmar)
    canonicas = "".join(f"{n}:{a_firmar[n]}\n" for n in nombres)
    firmadas = ";".join(nombres)

    peticion_canonica = "\n".join(
        (
            metodo.upper(),
            quote(ruta, safe="/-_.~"),
            consulta,
            canonicas,
            firmadas,
            _sha256_hex(cuerpo),
        )
    )
    ambito = f"{fecha}/{region}/{servicio}/aws4_request"
    texto_a_firmar = "\n".join(
        (_ALGORITMO, marca, ambito, _sha256_hex(peticion_canonica.encode("utf-8")))
    )
    firma = hmac.new(
        _clave_de_firma(credenciales.clave_secreta, fecha, region, servicio),
        texto_a_firmar.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    resultado = {
        "X-Amz-Date": marca,
        "Authorization": (
            f"{_ALGORITMO} Credential={credenciales.clave_acceso}/{ambito}, "
            f"SignedHeaders={firmadas}, Signature={firma}"
        ),
    }
    if credenciales.token_sesion:
        resultado["X-Amz-Security-Token"] = credenciales.token_sesion
    return resultado

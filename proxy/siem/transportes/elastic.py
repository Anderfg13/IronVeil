"""Elasticsearch / OpenSearch (API de documentos): `elastic://host:9200/indice`.

Un POST a `/<indice>/_doc` por evento; con el formato `ecs` (el que usa por defecto)
cada evento queda como un documento ECS. Credenciales: `SIEM_ELASTIC_API_KEY`, o
`SIEM_ELASTIC_USUARIO` + `SIEM_ELASTIC_CLAVE` (autenticacion basica, la de OpenSearch).
Siempre por https y con el certificado verificado.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Callable, Mapping
from urllib.parse import quote

from proxy.siem.puertos import ConectorSIEM, ErrorSIEM
from proxy.siem.registro import ContextoConector
from proxy.siem.transportes.credenciales import requerir, separar_host_puerto
from proxy.siem.transportes.https_generico import ConectorHTTP

PUERTO_ELASTIC = 9200
_INDICE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,254}$")


def _autorizacion(entorno: Mapping[str, str]) -> Callable[[], Mapping[str, str]]:
    """La cabecera `Authorization` segun las variables presentes; sin ninguna, falla:
    Elastic y OpenSearch vienen con seguridad activada y un destino sin clave no sirve.
    """
    clave_api = entorno.get("SIEM_ELASTIC_API_KEY", "").strip()
    if clave_api:
        return lambda: {"Authorization": f"ApiKey {clave_api}"}
    if entorno.get("SIEM_ELASTIC_USUARIO", "").strip():
        datos = requerir(entorno, "SIEM_ELASTIC_USUARIO", "SIEM_ELASTIC_CLAVE")
        par = f"{datos['SIEM_ELASTIC_USUARIO']}:{datos['SIEM_ELASTIC_CLAVE']}"
        basica = base64.b64encode(par.encode("utf-8")).decode("ascii")
        return lambda: {"Authorization": f"Basic {basica}"}
    raise ErrorSIEM(
        "faltan credenciales de Elastic: SIEM_ELASTIC_API_KEY, o SIEM_ELASTIC_USUARIO "
        "y SIEM_ELASTIC_CLAVE",
        reintentable=False,
    )


def fabrica_elastic(destino: str, contexto: ContextoConector) -> ConectorSIEM:
    """`host[:puerto]/indice`."""
    servidor, _, indice = destino.partition("/")
    if not _INDICE.match(indice):
        raise ErrorSIEM(
            "el indice de Elastic debe ir tras el host: elastic://host:9200/indice "
            "(minusculas, digitos, '.', '_' y '-')",
            reintentable=False,
        )
    host, puerto = separar_host_puerto(servidor, puerto_por_defecto=PUERTO_ELASTIC)
    return ConectorHTTP(
        f"https://{host}:{puerto}/{quote(indice)}/_doc",
        nombre="Elastic",
        tipo_contenido=contexto.tipo_contenido,
        autorizacion=_autorizacion(contexto.entorno),
    )

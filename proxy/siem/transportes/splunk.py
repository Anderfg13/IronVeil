"""Splunk (HTTP Event Collector, endpoint `raw`): `splunk://host:8088`.

El endpoint `raw` recibe el mensaje tal cual lo formateo IronVeil (JSON, CEF o LEEF) y
deja a Splunk partir los eventos; por eso sirve con cualquier formato. Token en
`SIEM_SPLUNK_TOKEN`. Exige un identificador de canal (GUID) en cada peticion.
"""

from __future__ import annotations

import uuid

from proxy.siem.puertos import ConectorSIEM
from proxy.siem.registro import ContextoConector
from proxy.siem.transportes.credenciales import requerir, separar_host_puerto
from proxy.siem.transportes.https_generico import ConectorHTTP

PUERTO_HEC = 8088
TIPO_DE_ORIGEN = "ironveil"  # sourcetype


def fabrica_splunk(destino: str, contexto: ContextoConector) -> ConectorSIEM:
    """`host[:puerto]` (8088 por defecto); el token viene de SIEM_SPLUNK_TOKEN."""
    host, puerto = separar_host_puerto(destino, puerto_por_defecto=PUERTO_HEC)
    token = requerir(contexto.entorno, "SIEM_SPLUNK_TOKEN")["SIEM_SPLUNK_TOKEN"]
    canal = str(uuid.uuid4())  # un canal por proceso, estable entre envios
    return ConectorHTTP(
        f"https://{host}:{puerto}/services/collector/raw?sourcetype={TIPO_DE_ORIGEN}",
        nombre="Splunk HEC",
        tipo_contenido=contexto.tipo_contenido,
        autorizacion=lambda: {"Authorization": f"Splunk {token}"},
        cabeceras_fijas={"X-Splunk-Request-Channel": canal},
    )

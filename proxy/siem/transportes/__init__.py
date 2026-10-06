"""Los transportes que trae IronVeil (otros se agregan desde fuera: `registro.py`)."""

from __future__ import annotations

from proxy.siem.registro import RegistroSIEM
from proxy.siem.transportes.archivo import ConectorArchivoLocal, fabrica_archivo
from proxy.siem.transportes.asincrono import ConectorAsincrono
from proxy.siem.transportes.aws import fabrica_cloudwatch
from proxy.siem.transportes.azure import fabrica_azure
from proxy.siem.transportes.elastic import fabrica_elastic
from proxy.siem.transportes.https_generico import fabrica_https
from proxy.siem.transportes.splunk import fabrica_splunk
from proxy.siem.transportes.syslog_red import PROTOCOLOS, fabrica_syslog

__all__ = ["ConectorArchivoLocal", "ConectorAsincrono", "registrar_incluidos"]


def registrar_incluidos(registro: RegistroSIEM) -> None:
    """Registra los transportes incluidos, cada uno con el formato que mejor le va.

    Solo el archivo es sincrono (un append local, sin red): todos los demas viajan por
    la red y se entregan en un hilo aparte.
    """
    registro.registrar_conector("archivo", fabrica_archivo, formato_por_defecto="json")
    for protocolo in PROTOCOLOS:
        registro.registrar_conector(
            f"syslog+{protocolo}",
            fabrica_syslog(protocolo),  # type: ignore[arg-type]
            formato_por_defecto="cef",
            de_red=True,
        )
    registro.registrar_conector(
        "https", fabrica_https, formato_por_defecto="json", de_red=True
    )
    registro.registrar_conector(
        "splunk", fabrica_splunk, formato_por_defecto="json", de_red=True
    )
    registro.registrar_conector(
        "elastic", fabrica_elastic, formato_por_defecto="ecs", de_red=True
    )
    registro.registrar_conector(
        "azure-logs", fabrica_azure, formato_por_defecto="json", de_red=True
    )
    registro.registrar_conector(
        "aws-cloudwatch", fabrica_cloudwatch, formato_por_defecto="json", de_red=True
    )

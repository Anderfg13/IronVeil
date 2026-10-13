"""Exportacion de los eventos de IronVeil a un SIEM (puertos y adaptadores).

IronVeil es un framework, no un producto atado a un SIEM: no se sabe cual usara quien
lo despliegue (Wazuh, Splunk, Elastic, Sentinel, CloudWatch, Graylog...). Este paquete
separa lo que cambia de lo que no, y cada capa depende solo de la de abajo:

    composicion  lee el entorno (unico lugar) y arma las piezas
    exportador   el servicio: entrega cada evento a todos los destinos
    registro     de `[formato@]esquema://destino` al formateador y el conector
    formatos/    FormateadorSIEM: como se escribe un evento (json, cef, leef, ecs)
    transportes/ ConectorSIEM: por donde se entrega (archivo, syslog, https, Splunk,
                 Elastic, Azure Monitor, CloudWatch) y ConectorAsincrono, que los
                 saca de `/chat`
    puertos      los dos contratos (un metodo cada uno) y ErrorSIEM
    evento       que es un evento y como se clasifica (sin E/S)

Formato y transporte son adapters SEPARADOS: se combinan libremente
(`cef@syslog+tls://...`, `ecs@elastic://...`). Un SIEM nuevo es un modulo de terceros
con `registrar(registro)` listado en `SIEM_ADAPTADORES`, sin tocar IronVeil. Guia
completa: docs/SIEM.md.

`proxy/main.py` solo conoce `exportar_evento()` y `cerrar()`; los nombres historicos
(`exportar_a_siem`, `FormateadorCEF`, `ConectorArchivoLocal`...) se siguen exportando.
"""

from __future__ import annotations

from proxy.siem.composicion import cerrar, exportar_evento
from proxy.siem.composicion import obtener as obtener_exportador
from proxy.siem.evento import CAMPOS_BASE, MARCA_INTEGRACION
from proxy.siem.formatos import (
    FORMATOS_SIEM,
    FormateadorCEF,
    FormateadorECS,
    FormateadorJSON,
    FormateadorLEEF,
    FormateadorWazuhJSON,
    exportar_a_siem,
)
from proxy.siem.puertos import (
    Cerrable,
    ConectorSIEM,
    ErrorSIEM,
    FormateadorSIEM,
    enviar_a_siem,
)
from proxy.siem.transportes import ConectorArchivoLocal, ConectorAsincrono

__all__ = [
    "CAMPOS_BASE",
    "FORMATOS_SIEM",
    "MARCA_INTEGRACION",
    "Cerrable",
    "ConectorArchivoLocal",
    "ConectorAsincrono",
    "ConectorSIEM",
    "ErrorSIEM",
    "FormateadorCEF",
    "FormateadorECS",
    "FormateadorJSON",
    "FormateadorLEEF",
    "FormateadorSIEM",
    "FormateadorWazuhJSON",
    "cerrar",
    "enviar_a_siem",
    "exportar_a_siem",
    "exportar_evento",
    "obtener_exportador",
]

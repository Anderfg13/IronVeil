"""Transporte por archivo: una linea por evento en un archivo que vigila un agente
del SIEM (Wazuh, Filebeat, Splunk Universal Forwarder, el agente de Azure Monitor o el
de CloudWatch). Es el transporte mas simple y el que menos puede fallar: sin red."""

from __future__ import annotations

import threading
from pathlib import Path

from proxy.siem.puertos import ConectorSIEM, ErrorSIEM
from proxy.siem.registro import ContextoConector


class ConectorArchivoLocal:
    """Agrega el mensaje a un archivo local (JSON Lines u otro, una linea por evento).

    Escribe en un archivo APARTE de `resultados/<fecha>/eventos.jsonl` a proposito: ese
    es el dataset crudo del experimento (regla 4 de CLAUDE.md) y un consumidor de SIEM
    es otro destino. El lock es suyo (es el dueno del archivo): asi V5, que dispara
    rafagas simultaneas, no mezcla ni pierde lineas.
    """

    def __init__(self, ruta: Path) -> None:
        self._ruta = ruta
        self._lock = threading.Lock()

    def enviar(self, mensaje: str) -> None:
        try:
            with self._lock:
                self._ruta.parent.mkdir(parents=True, exist_ok=True)
                with self._ruta.open("a", encoding="utf-8") as archivo:
                    archivo.write(mensaje + "\n")
        except OSError as exc:
            raise ErrorSIEM(
                f"no se pudo escribir el archivo del SIEM ({type(exc).__name__})"
            ) from exc


def fabrica_archivo(destino: str, contexto: ContextoConector) -> ConectorSIEM:
    """`archivo:///ruta/al/archivo.jsonl` -> el archivo que vigila el agente."""
    if not destino.strip():
        raise ErrorSIEM("falta la ruta del archivo SIEM", reintentable=False)
    return ConectorArchivoLocal(Path(destino.strip()))

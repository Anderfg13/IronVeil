"""Transporte syslog (RFC 5424) por UDP, TCP o TLS.

Lo entienden Wazuh, Graylog, Sentinel (con el agente de Azure Monitor), Splunk, QRadar,
rsyslog y casi cualquier colector. El mensaje (CEF, LEEF, JSON...) va como cuerpo de un
mensaje syslog; en TCP y TLS cada mensaje termina en salto de linea (encuadre
no transparente, el que aceptan por defecto los colectores habituales).
"""

from __future__ import annotations

import socket
import ssl
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from proxy.siem.puertos import ConectorSIEM, ErrorSIEM
from proxy.siem.registro import ContextoConector, FabricaConector
from proxy.siem.transportes.credenciales import separar_host_puerto

Protocolo = Literal["udp", "tcp", "tls"]
PROTOCOLOS: tuple[str, ...] = ("udp", "tcp", "tls")

_FACILIDAD_LOCAL0 = 16
_SEVERIDAD_INFORMATIVA = 6
_PUERTO_POR_DEFECTO = {"udp": 514, "tcp": 514, "tls": 6514}
TIMEOUT_POR_DEFECTO = 5.0
_APP = "ironveil"


def _ahora_utc() -> datetime:
    return datetime.now(UTC)


def puerto_por_defecto(protocolo: str) -> int:
    """514 para UDP/TCP y 6514 (el registrado en RFC 5425) para TLS."""
    return _PUERTO_POR_DEFECTO[protocolo]


def envolver_rfc5424(mensaje: str, *, host: str, app: str, instante: datetime) -> str:
    """`<PRI>1 FECHA HOST APP - - - MENSAJE` (RFC 5424): sin PID, sin id de mensaje y
    sin datos estructurados. Un salto de linea dentro del mensaje partiria el evento en
    dos: se escapa."""
    prioridad = _FACILIDAD_LOCAL0 * 8 + _SEVERIDAD_INFORMATIVA
    marca = instante.astimezone(UTC).isoformat(timespec="milliseconds")
    limpio = mensaje.replace("\r", "\\r").replace("\n", "\\n")
    return f"<{prioridad}>1 {marca.replace('+00:00', 'Z')} {host} {app} - - - {limpio}"


class ConectorSyslog:
    """Envia cada mensaje a un colector syslog.

    - UDP: sin conexion; un datagrama por evento (sin garantia de entrega).
    - TCP: conexion perezosa; si se cae, el envio falla con `ErrorSIEM` y el siguiente
      la reabre.
    - TLS: como TCP, con el certificado del servidor SIEMPRE verificado (con el contexto
      que se inyecta, por defecto el del sistema); nunca se desactiva la verificacion.

    No es seguro entre hilos por si solo: lo usa un unico hilo (el de
    `ConectorAsincrono`) y por eso lleva un lock barato por si alguien lo usa directo.
    """

    def __init__(
        self,
        host: str,
        puerto: int,
        protocolo: Protocolo = "udp",
        *,
        nombre_host: str | None = None,
        contexto_ssl: ssl.SSLContext | None = None,
        timeout: float = TIMEOUT_POR_DEFECTO,
        reloj: Callable[[], datetime] = _ahora_utc,
    ) -> None:
        if protocolo not in PROTOCOLOS:
            raise ErrorSIEM(
                f"protocolo syslog desconocido: {protocolo!r} ({PROTOCOLOS})",
                reintentable=False,
            )
        self._host = host
        self._puerto = puerto
        self._protocolo = protocolo
        self._nombre_host = nombre_host or socket.gethostname()
        self._contexto = contexto_ssl
        self._timeout = timeout
        self._reloj = reloj
        self._socket: socket.socket | None = None
        self._lock = threading.Lock()

    def enviar(self, mensaje: str) -> None:
        datos = envolver_rfc5424(
            mensaje, host=self._nombre_host, app=_APP, instante=self._reloj()
        ).encode("utf-8")
        with self._lock:
            try:
                self._entregar(datos)
            except OSError as exc:
                self._descartar_socket()
                raise ErrorSIEM(
                    f"fallo el envio syslog {self._protocolo} ({type(exc).__name__})"
                ) from exc

    def cerrar(self) -> None:
        with self._lock:
            self._descartar_socket()

    def _entregar(self, datos: bytes) -> None:
        conexion = self._conexion()
        if self._protocolo == "udp":
            conexion.sendto(datos, (self._host, self._puerto))
        else:
            conexion.sendall(datos + b"\n")

    def _conexion(self) -> socket.socket:
        if self._socket is None:
            self._socket = self._abrir()
        return self._socket

    def _abrir(self) -> socket.socket:
        if self._protocolo == "udp":
            nuevo = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            nuevo.settimeout(self._timeout)
            return nuevo
        crudo = socket.create_connection((self._host, self._puerto), self._timeout)
        if self._protocolo == "tcp":
            return crudo
        contexto = self._contexto or _contexto_tls_verificado()
        try:
            return contexto.wrap_socket(crudo, server_hostname=self._host)
        except OSError:
            crudo.close()
            raise

    def _descartar_socket(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass  # ya estaba roto: lo importante es soltarlo
            self._socket = None


def _contexto_tls_verificado() -> ssl.SSLContext:
    """Contexto TLS del sistema: verifica cadena y nombre, TLS 1.2 como minimo."""
    contexto = ssl.create_default_context()
    contexto.minimum_version = ssl.TLSVersion.TLSv1_2
    return contexto


def fabrica_syslog(protocolo: Protocolo) -> FabricaConector:
    """La fabrica de un esquema `syslog+<protocolo>://host[:puerto]`.

    Para TLS con una autoridad certificadora PROPIA de la empresa, `SIEM_CA_ARCHIVO`
    apunta a su certificado: se verifica contra ella, no se desactiva la verificacion.
    """

    def fabrica(destino: str, contexto: ContextoConector) -> ConectorSIEM:
        host, puerto = separar_host_puerto(
            destino, puerto_por_defecto=puerto_por_defecto(protocolo)
        )
        contexto_ssl = None
        if protocolo == "tls":
            contexto_ssl = _contexto_tls_verificado()
            ca = contexto.entorno.get("SIEM_CA_ARCHIVO", "").strip()
            if ca:
                try:
                    contexto_ssl.load_verify_locations(cafile=ca)
                except (OSError, ssl.SSLError) as exc:
                    raise ErrorSIEM(
                        f"SIEM_CA_ARCHIVO no se pudo leer ({type(exc).__name__})",
                        reintentable=False,
                    ) from exc
        return ConectorSyslog(host, puerto, protocolo, contexto_ssl=contexto_ssl)

    return fabrica

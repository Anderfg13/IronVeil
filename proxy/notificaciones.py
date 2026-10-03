"""Notificacion al usuario cuando aprobacion humana pone una peticion en cola
(extension opcional, Parte B).

Canales soportados, cada uno INDEPENDIENTE y opcional (si su variable de
entorno no esta, ese canal simplemente no existe):

- Webhook generico: POST JSON a `NOTIFICAR_WEBHOOK_URL` (p. ej. un endpoint
  de prueba local).
- Slack: incoming webhook en `NOTIFICAR_SLACK_WEBHOOK_URL`.
- Correo (SMTP): `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USUARIO`,
  `SMTP_CLAVE`, `SMTP_REMITENTE` (opcional, default `SMTP_USUARIO`) y
  `NOTIFICAR_CORREO_DESTINO`. STARTTLS por defecto; `SMTP_SSL=1` usa SMTPS.
- WhatsApp, via la API de Twilio: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
  `TWILIO_WHATSAPP_ORIGEN` (p. ej. `whatsapp:+14155238886`, el sandbox) y
  `NOTIFICAR_WHATSAPP_DESTINO` (`whatsapp:+57...`).

**No bloqueante, por diseno.** `notificar_en_segundo_plano()` lanza un hilo
daemon y vuelve de inmediato; cada canal tiene su propio `try/except` y su
propio timeout. Si un canal falla (endpoint caido, credenciales malas, sin
red), se registra una advertencia y la peticion que la disparo sigue su
curso: solo se pierde la notificacion, nunca la funcionalidad principal.

**Seguridad.** Todas las credenciales y URLs viven solo en el entorno (nunca
en el codigo, CLAUDE.md regla 2 y seccion 7) y jamas se escriben en el log:
las advertencias nombran el canal y el tipo de error, no la URL ni el token.
El mensaje NO incluye el texto de la peticion (puede traer una credencial
-- el experimento las maneja a proposito), solo metadatos: que mecanismo/
motivo detecto el riesgo, vector, configuracion activa, modelo y timestamp.
La verificacion TLS nunca se desactiva.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
import threading
from collections.abc import Callable
from datetime import datetime
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_NOTIFICACION_S: float = 5.0
_URL_TWILIO = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
# Texto plano (sin TLS) solo hacia el propio laboratorio: el receptor local de
# la demo o el host de Docker. Cualquier otro destino debe ser HTTPS.
_HOSTS_DE_LABORATORIO = frozenset(
    {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
)


def construir_evento_notificacion(
    *,
    motivo: str,
    configuracion: str,
    modelo: str,
    vector_probado: str | None,
    tipo: str = "peticion_en_revision",
    herramienta: str | None = None,
) -> dict[str, Any]:
    """Metadatos de la notificacion (nunca el texto de la peticion).

    `motivo` es el mecanismo o disparador que puso la peticion en cola
    (`filtrado`, `clasificacion`, `minimo_privilegio`,
    `limite_de_peticiones`, `limite_global_de_peticiones`, `herramienta`...).
    """
    evento: dict[str, Any] = {
        "tipo": tipo,
        "motivo": motivo,
        "vector_probado": vector_probado,
        "configuracion": configuracion,
        "modelo_destino": modelo,
        "timestamp": datetime.now().astimezone().isoformat(),
    }
    if herramienta is not None:
        evento["herramienta"] = herramienta
    return evento


def formatear_texto(evento: dict[str, Any]) -> str:
    """Texto legible para Slack / correo / WhatsApp."""
    lineas = [
        "IronVeil: una peticion quedo en la cola de revision humana",
        f"Detectado por: {evento['motivo']}",
        f"Vector: {evento.get('vector_probado') or 'n/a (trafico sin etiquetar)'}",
        f"Configuracion activa: {evento['configuracion']}",
        f"Modelo: {evento['modelo_destino']}",
        f"Timestamp: {evento['timestamp']}",
    ]
    if evento.get("herramienta"):
        lineas.insert(2, f"Herramienta SIMULADA solicitada: {evento['herramienta']}")
    return "\n".join(lineas)


def _url_http_valida(url: str) -> bool:
    """True si `url` es HTTPS, o HTTP en claro hacia un host del laboratorio."""
    partes = urlsplit(url)
    if partes.scheme == "https":
        return bool(partes.hostname)
    return partes.scheme == "http" and partes.hostname in _HOSTS_DE_LABORATORIO


def _enviar_webhook(evento: dict[str, Any]) -> None:
    url = os.environ["NOTIFICAR_WEBHOOK_URL"]
    if not _url_http_valida(url):
        raise ValueError(
            "NOTIFICAR_WEBHOOK_URL debe ser HTTPS (o HTTP solo hacia localhost)"
        )
    httpx.post(url, json=evento, timeout=TIMEOUT_NOTIFICACION_S).raise_for_status()


def _enviar_slack(evento: dict[str, Any]) -> None:
    url = os.environ["NOTIFICAR_SLACK_WEBHOOK_URL"]
    if not url.startswith("https://"):
        raise ValueError("NOTIFICAR_SLACK_WEBHOOK_URL debe empezar por https://")
    httpx.post(
        url, json={"text": formatear_texto(evento)}, timeout=TIMEOUT_NOTIFICACION_S
    ).raise_for_status()


def _contexto_tls() -> ssl.SSLContext:
    """Contexto TLS que valida certificado y nombre de host (TLS >= 1.2)."""
    contexto = ssl.create_default_context()
    contexto.check_hostname = True
    contexto.verify_mode = ssl.CERT_REQUIRED
    contexto.minimum_version = ssl.TLSVersion.TLSv1_2
    return contexto


def _abrir_smtp(host: str, puerto: int) -> smtplib.SMTP:
    """Conexion SMTP cifrada: SMTPS (`SMTP_SSL=1`, p. ej. 465) o, por defecto,
    conexion en claro que se eleva de inmediato con STARTTLS (p. ej. 587), antes
    de enviar credenciales o mensaje. Nunca se devuelve una sesion sin TLS."""
    if os.getenv("SMTP_SSL") == "1":
        return smtplib.SMTP_SSL(
            host, puerto, timeout=TIMEOUT_NOTIFICACION_S, context=_contexto_tls()
        )
    servidor = smtplib.SMTP(host, puerto, timeout=TIMEOUT_NOTIFICACION_S)
    try:
        servidor.starttls(context=_contexto_tls())
    except Exception:
        servidor.close()
        raise
    return servidor


def _enviar_correo(evento: dict[str, Any]) -> None:
    host = os.environ["SMTP_HOST"]
    puerto = int(os.getenv("SMTP_PORT", "587"))
    usuario = os.getenv("SMTP_USUARIO", "")
    clave = os.getenv("SMTP_CLAVE", "")
    mensaje = EmailMessage()
    mensaje["Subject"] = f"[IronVeil] Peticion en revision ({evento['motivo']})"
    mensaje["From"] = os.getenv("SMTP_REMITENTE") or usuario
    mensaje["To"] = os.environ["NOTIFICAR_CORREO_DESTINO"]
    mensaje.set_content(formatear_texto(evento))

    with _abrir_smtp(host, puerto) as servidor:
        if usuario:
            servidor.login(usuario, clave)
        servidor.send_message(mensaje)


def _enviar_whatsapp(evento: dict[str, Any]) -> None:
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    httpx.post(
        _URL_TWILIO.format(sid=sid),
        data={
            "From": os.environ["TWILIO_WHATSAPP_ORIGEN"],
            "To": os.environ["NOTIFICAR_WHATSAPP_DESTINO"],
            "Body": formatear_texto(evento),
        },
        auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]),
        timeout=TIMEOUT_NOTIFICACION_S,
    ).raise_for_status()


# Canal -> (variables de entorno que deben existir, funcion de envio).
_CANALES: dict[str, tuple[tuple[str, ...], Callable[[dict[str, Any]], None]]] = {
    "webhook": (("NOTIFICAR_WEBHOOK_URL",), _enviar_webhook),
    "slack": (("NOTIFICAR_SLACK_WEBHOOK_URL",), _enviar_slack),
    "correo": (("SMTP_HOST", "NOTIFICAR_CORREO_DESTINO"), _enviar_correo),
    "whatsapp": (
        (
            "TWILIO_ACCOUNT_SID",
            "TWILIO_AUTH_TOKEN",
            "TWILIO_WHATSAPP_ORIGEN",
            "NOTIFICAR_WHATSAPP_DESTINO",
        ),
        _enviar_whatsapp,
    ),
}


def canales_configurados() -> list[str]:
    """Canales cuyas variables de entorno estan todas definidas ahora."""
    return [
        nombre
        for nombre, (variables, _) in _CANALES.items()
        if all(os.getenv(v) for v in variables)
    ]


def enviar_notificaciones(evento: dict[str, Any]) -> dict[str, bool]:
    """Envia `evento` a todos los canales configurados. Nunca lanza.

    Devuelve {canal: True si salio bien, False si fallo}. Sincrona: la usan
    los tests y `notificar_en_segundo_plano()`; el proxy llama a esta ultima.
    """
    resultados: dict[str, bool] = {}
    for nombre in canales_configurados():
        _, enviar = _CANALES[nombre]
        try:
            enviar(evento)
        except (
            Exception
        ) as exc:  # noqa: BLE001 -- una notificacion nunca debe romper nada
            # Solo el tipo de error: el texto puede traer la URL o el token.
            logger.warning(
                "notificacion por %s fallo (%s); la peticion sigue su curso.",
                nombre,
                type(exc).__name__,
            )
            resultados[nombre] = False
        else:
            resultados[nombre] = True
    return resultados


def notificar_en_segundo_plano(evento: dict[str, Any]) -> None:
    """Dispara las notificaciones en un hilo daemon y vuelve de inmediato.

    No hace nada (ni crea hilo) si no hay ningun canal configurado.
    """
    if not canales_configurados():
        return
    try:
        threading.Thread(
            target=enviar_notificaciones, args=(evento,), daemon=True
        ).start()
    except Exception as exc:  # noqa: BLE001 -- ej. no se puede crear mas hilos
        logger.warning("no se pudo lanzar la notificacion (%s)", type(exc).__name__)

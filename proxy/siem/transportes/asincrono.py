"""Entrega desacoplada: un decorador que saca el envio de la ruta de `/chat`.

Un transporte de red (HTTPS, syslog por TCP) puede tardar segundos o fallar. Si se
llamara dentro de la peticion, un SIEM lento haria lento el chat. Este decorador
envuelve CUALQUIER conector: `enviar()` solo encola (microsegundos) y un hilo aparte
entrega, con reintentos.

Si la cola se llena (el SIEM lleva rato caido) se descarta el evento MAS NUEVO y se
cuenta: el chat nunca espera ni se queda sin memoria por culpa del SIEM. El dataset
del experimento no se ve afectado: se escribe antes, aparte.
"""

from __future__ import annotations

import logging
import queue
import threading

from proxy.siem.puertos import ConectorSIEM, ErrorSIEM

logger = logging.getLogger(__name__)

CAPACIDAD_POR_DEFECTO = 1000
INTENTOS_POR_DEFECTO = 3
ESPERA_BASE_POR_DEFECTO = 0.5
_FIN = object()  # centinela: el hilo termina cuando lo ve


class ConectorAsincrono:
    """Un `ConectorSIEM` que entrega a otro en un hilo propio."""

    def __init__(
        self,
        destino: ConectorSIEM,
        *,
        nombre: str = "siem",
        capacidad: int = CAPACIDAD_POR_DEFECTO,
        intentos: int = INTENTOS_POR_DEFECTO,
        espera_base: float = ESPERA_BASE_POR_DEFECTO,
    ) -> None:
        self._destino = destino
        self._nombre = nombre
        self._intentos = max(1, intentos)
        self._espera_base = espera_base
        self._cola: queue.Queue[object] = queue.Queue(maxsize=capacidad)
        self._cerrado = threading.Event()
        self._contadores = threading.Lock()
        self.enviados = 0
        self.fallidos = 0
        self.descartados = 0
        self._hilo = threading.Thread(
            target=self._trabajar, name=f"ironveil-{nombre}", daemon=True
        )
        self._hilo.start()

    def enviar(self, mensaje: str) -> None:
        """Encola. No bloquea ni lanza nada: si no cabe, lo descarta y lo cuenta."""
        try:
            self._cola.put_nowait(mensaje)
        except queue.Full:
            with self._contadores:
                self.descartados += 1
                total = self.descartados
            if total == 1 or total % CAPACIDAD_POR_DEFECTO == 0:
                logger.warning(
                    "SIEM %s: cola llena, %d evento(s) descartado(s) hasta ahora "
                    "(el destino no responde). El dataset no se ve afectado.",
                    self._nombre,
                    total,
                )

    def cerrar(self, timeout: float = 5.0) -> None:
        """Entrega lo pendiente (hasta `timeout`) y libera el destino. Repetible."""
        if self._cerrado.is_set():
            return
        self._cerrado.set()
        try:
            self._cola.put(_FIN, timeout=timeout)
        except queue.Full:
            logger.warning(
                "SIEM %s: no se pudo vaciar la cola al cerrar.", self._nombre
            )
        self._hilo.join(timeout)
        cerrar = getattr(self._destino, "cerrar", None)
        if callable(cerrar):
            cerrar()

    def _trabajar(self) -> None:
        while True:
            mensaje = self._cola.get()
            if mensaje is _FIN:
                return
            self._entregar_con_reintentos(str(mensaje))

    def _entregar_con_reintentos(self, mensaje: str) -> None:
        for intento in range(1, self._intentos + 1):
            try:
                self._destino.enviar(mensaje)
            except ErrorSIEM as exc:
                if not exc.reintentable or intento == self._intentos:
                    self._registrar_fallo(exc, intento)
                    return
                # Espera exponencial; se corta en cuanto se pide cerrar.
                self._cerrado.wait(self._espera_base * 2 ** (intento - 1))
            except Exception:  # noqa: BLE001 -- un conector ajeno puede fallar como sea
                logger.exception("SIEM %s: fallo inesperado del conector", self._nombre)
                self._contar_fallo()
                return
            else:
                with self._contadores:
                    self.enviados += 1
                return

    def _registrar_fallo(self, exc: ErrorSIEM, intento: int) -> None:
        self._contar_fallo()
        logger.error(
            "SIEM %s: evento no entregado tras %d intento(s): %s",
            self._nombre,
            intento,
            exc,
        )

    def _contar_fallo(self) -> None:
        with self._contadores:
            self.fallidos += 1

"""El caso de uso: recordar rechazos, consultarlos y olvidarlos.

Depende del puerto (`AlmacenMemoria`) y del dominio, **nada mas**: no lee el entorno, no
conoce ningun almacen concreto y no sabe como se redactan las credenciales (se lo
pasan). Las reglas viven en memoria para consultar rapido y cada cambio se escribe en
el almacen en el momento.

Una sola instancia del proxy: las reglas se leen al arrancar, asi que varias instancias
contra la misma base no se enteran de las reglas nuevas de las otras hasta reiniciar.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from typing import Any

from proxy.memoria_decisiones.dominio import (
    Regla,
    Resultado,
    huella,
    vista_previa,
)
from proxy.memoria_decisiones.puerto import AlmacenMemoria, ErrorAlmacen

logger = logging.getLogger(__name__)

MAXIMO_POR_DEFECTO = 5000


def _ahora() -> datetime:
    return datetime.now().astimezone()


class MemoriaDecisiones:
    """Rechazos recordados: en memoria para consultar y en un almacen que los conserva.

    `redactor` es obligatorio a proposito: quita las credenciales de la vista previa, y
    olvidarlo dejaria pasar secretos al almacen. `reloj` se sustituye en las pruebas.
    """

    def __init__(
        self,
        almacen: AlmacenMemoria | None,
        *,
        redactor: Callable[[str], str],
        maximo: int = MAXIMO_POR_DEFECTO,
        con_vista_previa: bool = True,
        reloj: Callable[[], datetime] = _ahora,
    ) -> None:
        self._almacen = almacen
        self._redactor = redactor
        self._maximo = maximo
        self._con_vista_previa = con_vista_previa
        self._reloj = reloj
        self._reglas: dict[str, Regla] = {}
        self._aciertos: dict[str, int] = {}
        self._lock = threading.RLock()
        self.persistente = False
        self.descripcion = almacen.descripcion if almacen else "solo en memoria"
        self._cargar()

    @property
    def maximo(self) -> int:
        return self._maximo

    def _cargar(self) -> None:
        """Reconstruye las reglas desde el almacen; si falla, sigue solo en memoria."""
        if self._almacen is None:
            return
        try:
            for regla in self._almacen.cargar():
                self._reglas[regla.huella] = regla
        except ErrorAlmacen as exc:
            logger.error(
                "memoria de decisiones: el almacen no esta disponible (%s); funciona "
                "SOLO en memoria y se perdera al reiniciar.",
                exc,
            )
            self.descripcion = "solo en memoria"
            return
        self.persistente = True
        logger.info(
            "memoria de decisiones: %d regla(s) cargada(s) de %s.",
            len(self._reglas),
            self.descripcion,
        )

    def _persistir(self, operacion: Callable[[AlmacenMemoria], None]) -> bool:
        """Ejecuta una escritura en el almacen. False si no se pudo guardar."""
        if self._almacen is None or not self.persistente:
            return False
        try:
            operacion(self._almacen)
            return True
        except ErrorAlmacen as exc:
            logger.error(
                "memoria de decisiones: no se pudo guardar (%s); la regla vale hasta "
                "el proximo reinicio.",
                exc,
            )
            return False

    def coincide(self, modelo: str, texto: str) -> Regla | None:
        """La regla que rechaza este mensaje para este modelo, o None."""
        clave = huella(modelo, texto)
        with self._lock:
            regla = self._reglas.get(clave)
            if regla is not None:
                self._aciertos[clave] = self._aciertos.get(clave, 0) + 1
            return regla

    def recordar_rechazo(
        self, modelo: str, texto: str, decidido_por: str, motivo: str
    ) -> Resultado:
        """Recuerda un rechazo humano y dice que paso (ver `Resultado`)."""
        clave = huella(modelo, texto)
        with self._lock:
            if clave in self._reglas:
                return Resultado.YA_RECORDADA
            if len(self._reglas) >= self._maximo:
                logger.warning(
                    "memoria de decisiones llena (%d reglas): no se recuerda este "
                    "rechazo; olvida alguna regla o sube MEMORIA_RECHAZOS_MAXIMO.",
                    self._maximo,
                )
                return Resultado.MEMORIA_LLENA
            regla = Regla(
                huella=clave,
                modelo=modelo,
                decidido_por=decidido_por,
                decidido_en=self._reloj().isoformat(),
                motivo=motivo,
                vista_previa=(
                    vista_previa(texto, self._redactor)
                    if self._con_vista_previa
                    else None
                ),
            )
            self._reglas[clave] = regla
            guardada = self._persistir(lambda almacen: almacen.guardar(regla))
        return Resultado.RECORDADA if guardada else Resultado.RECORDADA_SIN_GUARDAR

    def olvidar(self, clave: str, por: str) -> bool:
        """Revoca una regla. False si no existe."""
        with self._lock:
            if self._reglas.pop(clave, None) is None:
                return False
            self._aciertos.pop(clave, None)
            en = self._reloj().isoformat()
            self._persistir(lambda almacen: almacen.olvidar(clave, por, en))
        return True

    def listar(self) -> list[dict[str, Any]]:
        """Las reglas, la mas reciente primero, con cuantas veces actuaron desde que
        arranco el proxy (ese contador no se guarda)."""
        with self._lock:
            reglas = sorted(
                self._reglas.values(), key=lambda r: r.decidido_en, reverse=True
            )
            return [
                {**asdict(r), "aciertos": self._aciertos.get(r.huella, 0)}
                for r in reglas
            ]

    def tamano(self) -> int:
        with self._lock:
            return len(self._reglas)

    def cerrar(self) -> None:
        """Libera el almacen (al apagar el proxy)."""
        if self._almacen is None:
            return
        try:
            self._almacen.cerrar()
        except ErrorAlmacen as exc:
            logger.warning(
                "memoria de decisiones: no se pudo cerrar el almacen (%s).", exc
            )

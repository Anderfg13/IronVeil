"""Adaptador: un archivo JSON Lines, un renglon por decision (`recordar` u `olvidar`).

Sin dependencias ni servidor; legible a simple vista. Cada renglon se fuerza a disco
(`fsync`). Un renglon danado se omite con un aviso y un corte a mitad de escritura no
pierde lo anterior. Recibe su ruta por el constructor: no lee el entorno.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from proxy.memoria_decisiones.dominio import Regla
from proxy.memoria_decisiones.puerto import ErrorAlmacen

logger = logging.getLogger(__name__)


class AlmacenJsonl:
    """`AlmacenMemoria` sobre un archivo de texto."""

    def __init__(self, ruta: Path) -> None:
        self._ruta = ruta
        self.descripcion = f"JSON Lines ({ruta.name})"

    def cargar(self) -> list[Regla]:
        reglas: dict[str, Regla] = {}
        omitidos = 0
        try:
            self._ruta.parent.mkdir(parents=True, exist_ok=True)
            self._ruta.touch(exist_ok=True)
            if not os.access(self._ruta, os.W_OK):
                raise PermissionError("el archivo no es escribible")
            with self._ruta.open(encoding="utf-8") as archivo:
                for linea in archivo:
                    if linea.strip() and not self._aplicar(linea, reglas):
                        omitidos += 1
        except OSError as exc:
            raise ErrorAlmacen(f"{type(exc).__name__}: {self._ruta}") from exc
        if omitidos:
            logger.warning(
                "memoria de decisiones: %d renglon(es) dañado(s) omitido(s) en %s.",
                omitidos,
                self._ruta,
            )
        return list(reglas.values())

    @staticmethod
    def _aplicar(linea: str, reglas: dict[str, Regla]) -> bool:
        """Aplica un renglon. False si no se entiende (se omite)."""
        try:
            dato = json.loads(linea)
            if dato["op"] == "recordar":
                regla = Regla(
                    huella=dato["huella"],
                    modelo=dato["modelo"],
                    decidido_por=dato["decidido_por"],
                    decidido_en=dato["decidido_en"],
                    motivo=dato["motivo"],
                    vista_previa=dato.get("vista_previa"),
                )
                reglas[regla.huella] = regla
            elif dato["op"] == "olvidar":
                reglas.pop(dato["huella"], None)
            return True
        except (ValueError, KeyError, TypeError):
            return False

    def _anexar(self, dato: dict[str, Any]) -> None:
        try:
            with self._ruta.open("a", encoding="utf-8") as archivo:
                archivo.write(json.dumps(dato, ensure_ascii=False) + "\n")
                archivo.flush()
                os.fsync(archivo.fileno())
        except OSError as exc:
            raise ErrorAlmacen(f"{type(exc).__name__}: {self._ruta}") from exc

    def guardar(self, regla: Regla) -> None:
        self._anexar({"op": "recordar", **asdict(regla)})

    def olvidar(self, huella: str, por: str, en: str) -> None:
        self._anexar({"op": "olvidar", "huella": huella, "por": por, "en": en})

    def cerrar(self) -> None:
        """No hay nada abierto: cada escritura abre y cierra el archivo."""
        return None

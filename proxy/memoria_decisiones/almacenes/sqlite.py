"""Adaptador: una base SQLite (biblioteca estandar, sin servidor ni dependencias).

Transaccional y mas robusta que un archivo de texto; ademas deja una tabla de
**auditoria** con quien olvido cada regla y cuando. Es el modelo para conectar otra base
de datos relacional (PostgreSQL, MySQL...): las mismas operaciones con otro cliente.
Recibe su ruta por el constructor: no lee el entorno.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from proxy.memoria_decisiones.dominio import Regla
from proxy.memoria_decisiones.puerto import ErrorAlmacen

_ESQUEMA = (
    "CREATE TABLE IF NOT EXISTS reglas ("
    " huella TEXT PRIMARY KEY, modelo TEXT NOT NULL, decidido_por TEXT NOT NULL,"
    " decidido_en TEXT NOT NULL, motivo TEXT NOT NULL, vista_previa TEXT)",
    "CREATE TABLE IF NOT EXISTS auditoria ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, op TEXT NOT NULL,"
    " huella TEXT NOT NULL, por TEXT NOT NULL, en TEXT NOT NULL)",
)
_AUDITAR = "INSERT INTO auditoria (op, huella, por, en) VALUES (?, ?, ?, ?)"


class AlmacenSqlite:
    """`AlmacenMemoria` sobre una base SQLite."""

    def __init__(self, ruta: Path) -> None:
        self._ruta = ruta
        self._con: sqlite3.Connection | None = None
        self.descripcion = f"SQLite ({ruta.name})"

    def _conexion(self) -> sqlite3.Connection:
        if self._con is None:
            raise ErrorAlmacen("la base no esta abierta (falta cargar())")
        return self._con

    def cargar(self) -> list[Regla]:
        try:
            self._ruta.parent.mkdir(parents=True, exist_ok=True)
            # El servicio serializa las llamadas, pero pueden venir de hilos distintos.
            con = sqlite3.connect(self._ruta, check_same_thread=False, timeout=10)
            con.execute("PRAGMA synchronous = FULL")  # durabilidad antes que velocidad
            for sentencia in _ESQUEMA:
                con.execute(sentencia)
            con.commit()
            filas = con.execute(
                "SELECT huella, modelo, decidido_por, decidido_en, motivo, vista_previa"
                " FROM reglas"
            ).fetchall()
        except (OSError, sqlite3.Error) as exc:
            raise ErrorAlmacen(f"{type(exc).__name__}: {self._ruta}") from exc
        self._con = con
        return [Regla(*fila) for fila in filas]

    def _ejecutar(self, sentencias: list[tuple[str, tuple[Any, ...]]]) -> None:
        con = self._conexion()
        try:
            for sql, parametros in sentencias:
                con.execute(sql, parametros)
            con.commit()
        except sqlite3.Error as exc:
            con.rollback()
            raise ErrorAlmacen(f"{type(exc).__name__}: {self._ruta}") from exc

    def guardar(self, regla: Regla) -> None:
        self._ejecutar(
            [
                (
                    "INSERT OR REPLACE INTO reglas VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        regla.huella,
                        regla.modelo,
                        regla.decidido_por,
                        regla.decidido_en,
                        regla.motivo,
                        regla.vista_previa,
                    ),
                ),
                (
                    _AUDITAR,
                    ("recordar", regla.huella, regla.decidido_por, regla.decidido_en),
                ),
            ]
        )

    def olvidar(self, huella: str, por: str, en: str) -> None:
        self._ejecutar(
            [
                ("DELETE FROM reglas WHERE huella = ?", (huella,)),
                (_AUDITAR, ("olvidar", huella, por, en)),
            ]
        )

    def cerrar(self) -> None:
        """Cierra la conexion; se puede llamar mas de una vez."""
        if self._con is not None:
            self._con.close()
            self._con = None

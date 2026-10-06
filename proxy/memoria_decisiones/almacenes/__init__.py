"""Los adaptadores que trae IronVeil (otros se agregan desde fuera: `registro.py`)."""

from __future__ import annotations

from pathlib import Path

from proxy.memoria_decisiones.almacenes.jsonl import AlmacenJsonl
from proxy.memoria_decisiones.almacenes.sqlite import AlmacenSqlite
from proxy.memoria_decisiones.registro import RegistroAlmacenes

__all__ = ["AlmacenJsonl", "AlmacenSqlite", "registrar_incluidos"]


def registrar_incluidos(registro: RegistroAlmacenes) -> None:
    """Registra JSON Lines (`jsonl://`) y SQLite (`sqlite://`)."""
    registro.registrar("jsonl", lambda ruta: AlmacenJsonl(Path(ruta)))
    registro.registrar("sqlite", lambda ruta: AlmacenSqlite(Path(ruta)))

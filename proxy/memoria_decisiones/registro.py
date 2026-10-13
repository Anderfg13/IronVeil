"""El registro de adaptadores: de la URL de configuracion al almacen que la atiende.

Es un **objeto**, no un diccionario global: se construye, se le registran adaptadores
y se le pide uno. Asi el nucleo no conoce a sus adaptadores, y una empresa agrega el
suyo **desde su propio paquete**, sin editar IronVeil: su modulo expone
`registrar(registro)` y se lista en `MEMORIA_RECHAZOS_ADAPTADORES`.

    # mi_empresa/ironveil_postgres.py
    def registrar(registro):
        registro.registrar("postgresql", lambda ruta: AlmacenPostgres(ruta))
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from proxy.complementos import cargar_complementos
from proxy.memoria_decisiones.puerto import AlmacenMemoria, ErrorAlmacen

# Recibe lo que sigue a «esquema://» en la URL y devuelve el almacen.
Fabrica = Callable[[str], AlmacenMemoria]


class RegistroAlmacenes:
    """Esquemas de URL (`sqlite`, `postgresql`...) y la fabrica de su almacen."""

    def __init__(self) -> None:
        self._fabricas: dict[str, Fabrica] = {}

    def registrar(self, esquema: str, fabrica: Fabrica) -> None:
        """Registra un adaptador. Un esquema repetido es un error (no se pisa)."""
        clave = esquema.strip().lower()
        if not clave:
            raise ValueError("el esquema no puede estar vacio")
        if clave in self._fabricas:
            raise ValueError(f"el esquema {clave!r} ya esta registrado")
        self._fabricas[clave] = fabrica

    def esquemas(self) -> list[str]:
        return sorted(self._fabricas)

    def crear(self, url: str) -> AlmacenMemoria:
        """El almacen de una URL como `sqlite:///app/memoria/memoria.db`."""
        esquema, separador, resto = url.strip().partition("://")
        fabrica = self._fabricas.get(esquema.strip().lower())
        if not separador or not resto or fabrica is None:
            raise ErrorAlmacen(
                f"MEMORIA_RECHAZOS_ALMACEN no es valida (esquemas disponibles: "
                f"{self.esquemas()}): se espera por ejemplo jsonl:///ruta o sqlite:///ruta."
            )
        return fabrica(resto)


def cargar_adaptadores(registro: RegistroAlmacenes, modulos: Iterable[str]) -> None:
    """Importa cada modulo y deja que registre sus adaptadores (`registrar(registro)`).

    Cualquier fallo se convierte en `ErrorAlmacen` con un mensaje que dice cual modulo y
    por que; quien llama decide que hacer (la composicion sigue en memoria y avisa).
    """
    cargar_complementos(registro, modulos, error=ErrorAlmacen)

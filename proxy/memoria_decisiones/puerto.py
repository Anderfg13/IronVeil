"""El puerto: lo unico que el servicio sabe de donde se guardan las reglas.

Es el contrato que cumple cada adaptador (JSON Lines, SQLite, la base de datos de una
empresa). El servicio depende de esta interfaz y de ninguna implementacion.
"""

from __future__ import annotations

from typing import Protocol

from proxy.memoria_decisiones.dominio import Regla


class ErrorAlmacen(Exception):
    """El almacen no esta disponible o fallo una operacion (disco, red, base...).

    Es la **unica** excepcion que un adaptador debe dejar salir: traduce la de su
    controlador (`sqlite3.Error`, `psycopg.Error`, `OSError`...) para que el servicio
    no tenga que conocerlas.
    """


class AlmacenMemoria(Protocol):
    """Donde se guardan las reglas. Para otra base de datos se implementa esto.

    - `cargar()` devuelve las reglas **vigentes** (ya aplicado lo olvidado) y deja el
      almacen listo para escribir. Se llama una vez, al arrancar.
    - `guardar()` y `olvidar()` persisten el cambio **antes de volver**: si vuelven sin
      error, el cambio sobrevive a un reinicio.
    - `cerrar()` libera conexiones; debe poder llamarse mas de una vez.
    - Cualquier fallo se lanza como `ErrorAlmacen`.

    El servicio serializa las llamadas, asi que un adaptador **no necesita ser seguro
    entre hilos**. Nunca recibe ni debe guardar el texto completo de un mensaje: solo
    huellas y la vista previa que ya trae la `Regla`.

    `tests/contrato_almacen.py` es la bateria que todo adaptador debe pasar.
    """

    descripcion: str  # lo que ve la consola: «SQLite (memoria.db)»

    def cargar(self) -> list[Regla]: ...

    def guardar(self, regla: Regla) -> None: ...

    def olvidar(self, huella: str, por: str, en: str) -> None: ...

    def cerrar(self) -> None: ...

"""El registro de decodificadores: del nombre configurado al objeto que decodifica.

Es un **objeto**, no un diccionario global (igual que el del SIEM y el de la memoria):
una empresa agrega su codificacion desde su propio paquete, sin editar IronVeil. Su
modulo expone `registrar(registro)` y se lista en `NORMALIZACION_ADAPTADORES`:

    # mi_empresa/ironveil_leet.py
    def registrar(registro):
        registro.registrar("leet", lambda: DecodificadorLeet())
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from proxy.normalizacion.puerto import Decodificador, ErrorNormalizacion

FabricaDecodificador = Callable[[], Decodificador]


class RegistroDecodificadores:
    """Los decodificadores disponibles, por nombre."""

    def __init__(self) -> None:
        self._fabricas: dict[str, FabricaDecodificador] = {}

    def registrar(self, nombre: str, fabrica: FabricaDecodificador) -> None:
        """Registra un decodificador. Un nombre repetido es un error (no se pisa)."""
        clave = nombre.strip().lower()
        if not clave:
            raise ValueError("el nombre del decodificador no puede estar vacio")
        if clave in self._fabricas:
            raise ValueError(f"el decodificador {clave!r} ya esta registrado")
        self._fabricas[clave] = fabrica

    def nombres(self) -> list[str]:
        """Los nombres registrados, en orden alfabetico."""
        return sorted(self._fabricas)

    def crear(self, nombres: Iterable[str]) -> list[Decodificador]:
        """Los decodificadores pedidos, en ese orden.

        Lanza `ErrorNormalizacion` si alguno no esta registrado.
        """
        creados: list[Decodificador] = []
        for nombre in nombres:
            fabrica = self._fabricas.get(nombre.strip().lower())
            if fabrica is None:
                raise ErrorNormalizacion(
                    f"decodificador desconocido: {nombre!r} "
                    f"(disponibles: {self.nombres()})"
                )
            creados.append(fabrica())
        return creados

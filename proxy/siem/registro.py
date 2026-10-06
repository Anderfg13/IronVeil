"""El registro de formatos y transportes: del texto de configuracion al adaptador.

Es un **objeto**, no un diccionario global (como el de la memoria de decisiones): se
construye, se le registran adaptadores y se le pide uno. El nucleo no conoce a sus
adaptadores, y una empresa agrega el suyo desde su propio paquete, sin editar IronVeil:

    # mi_empresa/ironveil_datadog.py
    def registrar(registro):
        registro.registrar_formato("mio", lambda: FormateadorMio())
        registro.registrar_conector(
            "datadog", crear_conector, formato_por_defecto="mio"
        )

y se lista en `SIEM_ADAPTADORES`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import NamedTuple

from proxy.siem.puertos import ConectorSIEM, ErrorSIEM, FormateadorSIEM

# Un destino se escribe `formato@esquema://resto` (el formato es opcional).
_DESTINO = re.compile(
    r"^(?:(?P<formato>[A-Za-z][\w-]*)@)?(?P<esquema>[A-Za-z][\w+.-]*)://(?P<resto>.+)$"
)


@dataclass(frozen=True)
class ContextoConector:
    """Lo que un conector recibe ademas de su destino; no lee el entorno por su cuenta.

    `entorno` es una copia de las variables que le importan (claves y tokens incluidos,
    que nunca se escriben en el codigo ni en la URL); `tipo_contenido` lo decide el
    formato elegido.
    """

    entorno: Mapping[str, str] = field(default_factory=dict, repr=False)
    tipo_contenido: str = "text/plain"


FabricaFormato = Callable[[], FormateadorSIEM]
FabricaConector = Callable[[str, ContextoConector], ConectorSIEM]


class _EntradaConector(NamedTuple):
    fabrica: FabricaConector
    de_red: bool
    formato_por_defecto: str


class DestinoResuelto(NamedTuple):
    """El resultado de interpretar un destino de `SIEM_DESTINOS`."""

    descripcion: str  # sin credenciales: seguro para el log
    formateador: FormateadorSIEM
    conector: ConectorSIEM
    de_red: bool


class RegistroSIEM:
    """Los formatos (`cef`, `ecs`...) y transportes (`splunk`...) disponibles."""

    def __init__(self) -> None:
        self._formatos: dict[str, FabricaFormato] = {}
        self._conectores: dict[str, _EntradaConector] = {}

    def registrar_formato(self, nombre: str, fabrica: FabricaFormato) -> None:
        """Registra un formato. Un nombre repetido es un error (no se pisa)."""
        clave = self._clave(nombre, "formato")
        if clave in self._formatos:
            raise ValueError(f"el formato {clave!r} ya esta registrado")
        self._formatos[clave] = fabrica

    def registrar_conector(
        self,
        esquema: str,
        fabrica: FabricaConector,
        *,
        formato_por_defecto: str,
        de_red: bool = False,
    ) -> None:
        """Registra un transporte. `de_red=True` hace que se entregue en un hilo aparte
        (ver `ConectorAsincrono`): un SIEM lento nunca debe frenar el chat."""
        clave = self._clave(esquema, "esquema")
        if clave in self._conectores:
            raise ValueError(f"el esquema {clave!r} ya esta registrado")
        self._conectores[clave] = _EntradaConector(
            fabrica, de_red, formato_por_defecto.strip().lower()
        )

    def formatos(self) -> list[str]:
        return sorted(self._formatos)

    def esquemas(self) -> list[str]:
        return sorted(self._conectores)

    def resolver(self, destino: str, entorno: Mapping[str, str]) -> DestinoResuelto:
        """Interpreta `formato@esquema://resto` y arma su formateador y su conector.

        Lanza `ErrorSIEM` (sin credenciales en el mensaje) si el texto no es valido, si
        el esquema o el formato no existen, o si el conector no se puede crear.
        """
        coincide = _DESTINO.match(destino.strip())
        if coincide is None:
            raise ErrorSIEM(
                "destino SIEM no valido: se espera [formato@]esquema://destino "
                f"(esquemas: {self.esquemas()})",
                reintentable=False,
            )
        esquema = coincide["esquema"].lower()
        entrada = self._conectores.get(esquema)
        if entrada is None:
            raise ErrorSIEM(
                f"esquema SIEM desconocido: {esquema!r} "
                f"(disponibles: {self.esquemas()})",
                reintentable=False,
            )
        nombre_formato = (coincide["formato"] or entrada.formato_por_defecto).lower()
        fabrica_formato = self._formatos.get(nombre_formato)
        if fabrica_formato is None:
            raise ErrorSIEM(
                f"formato SIEM desconocido: {nombre_formato!r} "
                f"(disponibles: {self.formatos()})",
                reintentable=False,
            )
        formateador = fabrica_formato()
        contexto = ContextoConector(
            entorno=entorno,
            tipo_contenido=getattr(formateador, "tipo_contenido", "text/plain"),
        )
        conector = entrada.fabrica(coincide["resto"], contexto)
        return DestinoResuelto(
            descripcion=f"{nombre_formato}@{esquema}",
            formateador=formateador,
            conector=conector,
            de_red=entrada.de_red,
        )

    @staticmethod
    def _clave(texto: str, que: str) -> str:
        clave = texto.strip().lower()
        if not clave:
            raise ValueError(f"el {que} no puede estar vacio")
        return clave

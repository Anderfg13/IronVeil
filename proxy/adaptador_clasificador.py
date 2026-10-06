"""Adaptador entre el proxy y el modelo clasificador (mecanismo 3).

Por que existe: el proxy solo necesita un veredicto "malicioso / no malicioso", pero
cada modelo lo expresa a su manera (Prompt Guard 2 devuelve `LABEL_0`/`LABEL_1`; otros,
`SAFE`/`INJECTION`; Llama Guard, el texto `safe`/`unsafe`). Si el codigo comparara
contra un nombre fijo y se cambiara de modelo, una etiqueta distinta daria "no
malicioso" para todo y el proxy dejaria pasar cualquier ataque SIN ningun error
(fail open). Este modulo aisla esa traduccion en un solo sitio:

- cada modelo tiene un **perfil** de etiquetas (que nombres son malicioso y cuales
  benigno);
- el 86M tiene el suyo, verificado contra el modelo real (2026-09-18);
- un modelo nuevo con etiquetas con nombre (`INJECTION`, `SAFE`...) se adapta solo;
- un modelo nuevo con etiquetas genericas (`LABEL_0`...) **no se adivina**: hay que
  declararlas en `.env`, porque `LABEL_1` puede significar cosas opuestas segun el
  modelo;
- una etiqueta que el perfil no conoce nunca se interpreta como benigna: el
  llamador falla cerrado.

No hace red ni carga modelos: son funciones puras, testeables sin el stack.
Pasos para cambiar de modelo: docs/CAMBIAR_MODELO_CLASIFICADOR.md.
"""

from __future__ import annotations

import functools
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

MODELO_VERIFICADO_ENTRADA = "meta-llama/Llama-Prompt-Guard-2-86M"

# A donde va el texto cuando se clasifica (campo `destino` del detalle):
DESTINO_LOCAL = "local"  # esta maquina o el propio stack: no sale del laboratorio
DESTINO_PROPIO = "propio"  # un servicio de la organizacion, fuera de esta maquina
DESTINO_TERCERO = "tercero"  # otra organizacion: el texto sale del laboratorio

ESTADO_OK = "ok"
ESTADO_RESPUESTA_INVALIDA = "respuesta_invalida"

# "ollama" es el nombre del servicio en la red interna de Docker. Es una constante y
# no se deriva de OLLAMA_BASE_URL: si no, apuntar esa variable a un servidor ajeno lo
# volveria "local" y se saltaria el permiso.
HOSTS_LOCALES = frozenset(
    {"localhost", "127.0.0.1", "::1", "host.docker.internal", "ollama"}
)


def parsear_hosts(texto: str) -> frozenset[str]:
    """Lista de hosts de una variable de entorno, sin espacios y en minusculas."""
    return frozenset(h.strip().lower() for h in texto.split(",") if h.strip())


def clasificar_destino(url: str, hosts_propios: frozenset[str]) -> str:
    """`local`, `propio` o `tercero`: a donde iria el texto si se envia a `url`.

    `hosts_propios` son nombres exactos (ni subdominios ni sufijos cuentan). Una URL
    sin host se trata como tercero.
    """
    host = (urlparse(url).hostname or "").lower()
    if host in HOSTS_LOCALES:
        return DESTINO_LOCAL
    if host and host in hosts_propios:
        return DESTINO_PROPIO
    return DESTINO_TERCERO


class ErrorConfiguracion(RuntimeError):
    """El clasificador esta mal configurado (falta una variable, destino no permitido,
    etiquetas sin declarar...). Se distingue de un fallo del servicio para que el log
    pueda decir "error_configuracion" y no "error_interno".
    """


@dataclass(frozen=True)
class ResultadoBackend:
    """Lo que devuelve un backend: el veredicto y como llego a el.

    `estado` es "ok" o el motivo de un fallo que se resolvio fallando cerrado
    (`timeout`, `error_http_429`, `respuesta_invalida`...): sin esto, una caida del
    servicio se veria en los resultados igual que una deteccion real. `etiqueta` y
    `puntaje` son los del veredicto (nunca el texto del usuario).
    """

    malicioso: bool
    estado: str = ESTADO_OK
    puntaje: float | None = None
    etiqueta: str | None = None


@dataclass(frozen=True)
class DetalleClasificacion:
    """Que clasificador respondio y como: el bloque `clasificador_<direccion>` del log.

    Esquema comun a todos los backends; cada uno rellena lo que le aplica y el resto
    se omite. No contiene el texto del usuario ni claves.
    """

    backend: str
    modelo: str
    destino: str | None
    estado: str
    umbral: float | None = None
    puntaje: float | None = None
    etiqueta: str | None = None

    def como_dict(self) -> dict[str, Any]:
        """Los campos con valor; sin None ni numeros no finitos (no son JSON valido)."""
        return {
            clave: valor
            for clave, valor in asdict(self).items()
            if valor is not None
            and not (isinstance(valor, float) and not math.isfinite(valor))
            and valor != ""
        }


def normalizar(valor: object) -> str:
    """Compara sin importar mayusculas ni espacios: " Label_1 " == "LABEL_1"."""
    return str(valor).strip().upper()


def _parsear_lista(texto: str) -> frozenset[str]:
    """Convierte "a, b" de una variable de entorno en {"A", "B"} normalizado."""
    return frozenset(normalizar(p) for p in texto.split(",") if p.strip())


@dataclass(frozen=True)
class PerfilVeredicto:
    """Que etiquetas (o veredictos de texto) significan malicioso y cuales benigno."""

    maliciosos: frozenset[str]
    benignos: frozenset[str]

    def __post_init__(self) -> None:
        if not self.maliciosos or not self.benignos:
            raise ValueError(
                "Un perfil necesita al menos un valor malicioso y uno benigno."
            )
        comunes = self.maliciosos & self.benignos
        if comunes:
            raise ValueError(
                f"Valores a la vez maliciosos y benignos: {sorted(comunes)}."
            )

    def evaluar(self, etiqueta: object) -> bool | None:
        """True = malicioso, False = benigno, None = el perfil no la conoce.

        Quien llama debe tratar None como malicioso (fail closed); nunca como benigno.
        """
        valor = normalizar(etiqueta)
        if valor in self.maliciosos:
            return True
        if valor in self.benignos:
            return False
        return None

    def validar(self, etiquetas: Iterable[object], origen: str) -> None:
        """Lanza ValueError si alguna etiqueta del modelo no se sabe interpretar."""
        desconocidas = sorted(
            {normalizar(e) for e in etiquetas if self.evaluar(e) is None}
        )
        if desconocidas:
            raise ValueError(
                f"{origen} trae etiquetas que el perfil no sabe interpretar: "
                f"{desconocidas}. Declara cuales son maliciosas y cuales benignas con "
                "CLASIFICADOR_ENTRADA_ETIQUETAS_MALICIOSAS y "
                "CLASIFICADOR_ENTRADA_ETIQUETAS_BENIGNAS (ver "
                "docs/CAMBIAR_MODELO_CLASIFICADOR.md)."
            )


# Perfil del modelo de entrada actual, verificado contra el checkpoint real.
PERFIL_LLAMA_PROMPT_GUARD_2 = PerfilVeredicto(
    maliciosos=frozenset({"LABEL_1"}), benignos=frozenset({"LABEL_0"})
)
PERFILES_VERIFICADOS: dict[str, PerfilVeredicto] = {
    MODELO_VERIFICADO_ENTRADA: PERFIL_LLAMA_PROMPT_GUARD_2,
}
# Para un modelo nuevo: solo nombres que dicen lo que significan. Los `LABEL_n` NO
# estan aqui a proposito (ver el docstring del modulo).
PERFIL_ENTRADA_POR_NOMBRE = PerfilVeredicto(
    maliciosos=frozenset({"MALICIOUS", "INJECTION", "JAILBREAK", "ATTACK", "UNSAFE"}),
    benignos=frozenset({"BENIGN", "SAFE", "LEGIT", "LEGITIMATE", "NORMAL"}),
)
# Llama Guard contesta `safe` o `unsafe` (+ categorias en la segunda linea).
PERFIL_SALIDA_POR_DEFECTO = PerfilVeredicto(
    maliciosos=frozenset({"UNSAFE"}), benignos=frozenset({"SAFE"})
)


def _perfil_declarado(malos: str, buenos: str, nombres: str) -> PerfilVeredicto | None:
    """Perfil escrito en `.env`, o None si no se declaro ninguno."""
    if not malos.strip() and not buenos.strip():
        return None
    if not malos.strip() or not buenos.strip():
        raise ValueError(f"Declara las dos variables ({nombres}), no solo una.")
    return PerfilVeredicto(_parsear_lista(malos), _parsear_lista(buenos))


@functools.cache
def perfil_entrada(
    modelo_id: str, maliciosas: str = "", benignas: str = ""
) -> PerfilVeredicto:
    """Perfil del clasificador de entrada: lo declarado en `.env` manda; luego el
    perfil verificado del modelo; luego el de nombres claros."""
    declarado = _perfil_declarado(
        maliciosas,
        benignas,
        "CLASIFICADOR_ENTRADA_ETIQUETAS_MALICIOSAS y "
        "CLASIFICADOR_ENTRADA_ETIQUETAS_BENIGNAS",
    )
    if declarado is not None:
        return declarado
    return PERFILES_VERIFICADOS.get(modelo_id, PERFIL_ENTRADA_POR_NOMBRE)


@functools.cache
def perfil_salida(inseguros: str = "", seguros: str = "") -> PerfilVeredicto:
    """Perfil del veredicto de salida (la primera linea de lo que responde)."""
    declarado = _perfil_declarado(
        inseguros,
        seguros,
        "CLASIFICADOR_SALIDA_VEREDICTOS_INSEGUROS y "
        "CLASIFICADOR_SALIDA_VEREDICTOS_SEGUROS",
    )
    return declarado if declarado is not None else PERFIL_SALIDA_POR_DEFECTO

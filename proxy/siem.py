"""Andamiaje (patron Adapter) para una futura integracion con un SIEM.

IronVeil es un framework, no un producto atado a un cliente concreto: no se
sabe todavia que SIEM va a usar quien lo despliegue (Wazuh, Splunk, Elastic,
Sentinel, ...), ni siquiera si el formato de log interno de IronVeil (el
esquema de 8 campos base + extendidos, ver skill esquema-log) va a seguir
siendo el mismo dentro de un ano. Este modulo existe para que esas dos cosas
puedan cambiar de forma independiente, sin que el codigo del proxy tenga que
saber cual SIEM hay detras:

- `FormateadorSIEM`: adapta el evento interno al formato de cable que un
  SIEM concreto espera (CEF, LEEF, ECS, JSON plano, etc.).
- `ConectorSIEM`: adapta la entrega del mensaje ya formateado al transporte
  real (HTTP, syslog, un archivo que un agente vigila, etc.).

Los dos son adapters SEPARADOS a proposito: formato y transporte varian de
forma independiente (dos SIEM pueden compartir transporte pero no formato,
o viceversa). Quien conecte un SIEM real implementa las dos interfaces UNA
vez cada una, sin tocar `proxy/main.py` -- ver `enviar_a_siem()`.

IMPORTANTE -- todavia NO esta cableado a `/chat`: `_registrar_evento()` en
`proxy/main.py` sigue siendo la unica escritura real, hacia
`resultados/<fecha>/eventos.jsonl` (el dataset del experimento, protegido
por la regla 4 de CLAUDE.md -- nunca se edita a mano ni se mezcla con otra
cosa). Conectar esto de verdad a `/chat` es tarea de Piedrahita (reparto de
equipo, CLAUDE.md seccion 8, "export SIEM"): aqui solo queda la interfaz
lista para que ella (o quien sea) la use sin tener que disenarla desde cero,
decidiendo en ese momento si el envio al SIEM es sincrono, en un hilo aparte,
o en background -- una decision de esa integracion, no de este andamiaje.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FormateadorSIEM(Protocol):
    """Adapter: convierte un evento interno de IronVeil al formato de cable
    de un SIEM concreto.

    Cualquier objeto con un metodo `formatear(evento) -> str` satisface esta
    interfaz (typing estructural de `Protocol`, no hace falta heredar de
    nada) -- asi un adapter para un SIEM real puede envolver directamente el
    SDK de ese SIEM sin una capa de mas.
    """

    def formatear(self, evento: dict[str, Any]) -> str:
        """Recibe el mismo dict que ya arma `_construir_evento()` en
        `proxy/main.py` (esquema de 8 campos base + los extendidos que
        apliquen) y devuelve el mensaje ya en el formato que espera el SIEM
        destino."""
        ...


@runtime_checkable
class ConectorSIEM(Protocol):
    """Adapter: entrega un mensaje ya formateado al SIEM real."""

    def enviar(self, mensaje: str) -> None:
        """Entrega `mensaje` (ya formateado por un `FormateadorSIEM`) al
        SIEM. Debe fallar de forma explicita (excepcion), nunca en
        silencio, si la entrega no se pudo confirmar -- mismo criterio de
        "nada de pass silencioso" de CLAUDE.md seccion 7."""
        ...


def enviar_a_siem(
    evento: dict[str, Any], formateador: FormateadorSIEM, conector: ConectorSIEM
) -> None:
    """Punto de entrada unico: formatea `evento` y lo entrega, sin que quien
    llama necesite conocer el SIEM concreto detras de los dos adapters.

    Uso previsto una vez que alguien conecte un SIEM real (ejemplo, no
    implementado aqui):

        enviar_a_siem(evento, FormateadorCEF(), ConectorSyslogWazuh(host, puerto))
    """
    conector.enviar(formateador.formatear(evento))


# --- Adapters de referencia -------------------------------------------------
#
# No son solo placeholders para probar el patron: son implementaciones
# validas por si mismas (JSON plano + archivo local es exactamente como
# muchos SIEM, incluido Wazuh via su modulo de lectura de logs, ingieren
# eventos). Sirven de ejemplo minimo de como implementar las dos interfaces
# de arriba antes de que exista una integracion con un SIEM real.


class FormateadorJSON:
    """Formateador de referencia: el evento tal cual, como JSON de una linea."""

    def formatear(self, evento: dict[str, Any]) -> str:
        return json.dumps(evento, ensure_ascii=False)


class ConectorArchivoLocal:
    """Conector de referencia: agrega el mensaje a un archivo local (JSON
    Lines, una linea por evento).

    Escribe en un archivo APARTE de `resultados/<fecha>/eventos.jsonl` a
    proposito: ese archivo es el dataset crudo del experimento (regla 4 de
    CLAUDE.md), y un consumidor de SIEM es un destino distinto, no debe
    mezclarse con la evidencia cruda ni competir por el mismo lock
    (`_registro_lock` en `proxy/main.py` protege solo ese archivo).
    """

    def __init__(self, ruta: Path) -> None:
        self._ruta = ruta

    def enviar(self, mensaje: str) -> None:
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._ruta.open("a", encoding="utf-8") as f:
            f.write(mensaje + "\n")


# --- Formatos concretos (extension del 17 de octubre) -----------------------
#
# Validados contra la documentacion oficial de Wazuh (consultada el
# 2026-10-02; ver docs/VALIDACION_SIEM.md):
# - log_format "json" de <localfile>: "Used for single-line JSON files" --
#   un objeto JSON por linea, sin saltos de linea internos.
# - Decodificador JSON: extrae cada campo (los anidados con notacion de
#   punto, p. ej. `ironveil.resultado`), soporta numeros, strings,
#   booleanos, null, arrays y objetos, PERO "an array of objects is not
#   supported". Nuestro esquema solo tiene arrays de strings
#   (`mecanismos_activos`, `herramientas_invocadas`); exportar_a_siem()
#   rechaza un array de objetos en vez de mandar algo que Wazuh no decodifica.
# - "cef" NO es un log_format de Wazuh: por eso el formato por defecto
#   de exportar_a_siem() es JSON. FormateadorCEF queda para SIEM que si lo
#   ingieren nativamente (ArcSight, Microsoft Sentinel via CEF/syslog).

VERSION_PRODUCTO: str = "0.1.0"
# Identificador de origen de cada linea (mismo proposito que la etiqueta
# `<label key="@source">` del ejemplo oficial de Wazuh): permite escribir
# reglas que solo apliquen a eventos de IronVeil.
FUENTE_SIEM: str = "ironveil"
CAMPOS_BASE_REQUERIDOS: tuple[str, ...] = (
    "timestamp",
    "configuracion",
    "mecanismos_activos",
    "vector_probado",
    "modelo_destino",
    "resultado",
    "mecanismo_que_bloqueo",
    "latencia_ms",
)
# Severidad CEF (0-10) por `resultado`. Un ataque exitoso es lo que un SOC
# querria ver primero; un uso normal es puramente informativo.
SEVERIDAD_CEF_POR_RESULTADO: dict[str, int] = {
    "exitoso_para_atacante": 8,
    "bloqueado": 5,
    "permitido_normal": 1,
}


def _validar_evento(evento: dict[str, Any]) -> None:
    """Falla ruidosamente si al evento le falta alguno de los 8 campos base
    o trae un array de objetos (no decodificable por Wazuh)."""
    faltantes = [c for c in CAMPOS_BASE_REQUERIDOS if c not in evento]
    if faltantes:
        raise ValueError(f"Evento sin campos base del esquema: {faltantes}")
    for clave, valor in evento.items():
        if isinstance(valor, list) and any(isinstance(v, dict) for v in valor):
            raise ValueError(
                f"Campo {clave!r} es un array de objetos: el decodificador "
                "JSON de Wazuh no lo soporta"
            )


class FormateadorWazuhJSON:
    """JSON de una linea para el log_format "json" de Wazuh.

    Estructura: `{"@source": "ironveil", "timestamp": ..., "ironveil":
    {<evento completo>}}`. El evento va anidado bajo "ironveil" para que
    sus campos queden como `ironveil.<campo>` en Wazuh y nunca choquen con
    campos estaticos propios de Wazuh (p. ej. `timestamp`, `agent`).
    """

    def formatear(self, evento: dict[str, Any]) -> str:
        _validar_evento(evento)
        mensaje = {
            "@source": FUENTE_SIEM,
            "timestamp": evento["timestamp"],
            FUENTE_SIEM: evento,
        }
        # json.dumps escapa los saltos de linea dentro de strings: la salida
        # es siempre una sola linea, requisito del log_format "json".
        return json.dumps(mensaje, ensure_ascii=False)


def _escapar_cabecera_cef(valor: str) -> str:
    """CEF: en la cabecera se escapan la barra invertida y `|`."""
    return valor.replace("\\", "\\\\").replace("|", "\\|")


def _escapar_extension_cef(valor: str) -> str:
    """CEF: en la extension se escapan la barra invertida y `=`, y los
    saltos de linea se escriben como las secuencias literales `\\n`/`\\r`."""
    return (
        valor.replace("\\", "\\\\")
        .replace("=", "\\=")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


class FormateadorCEF:
    """Common Event Format (ArcSight CEF v0) de una linea.

    `CEF:0|IronVeil|Proxy|<version>|<resultado>|<nombre>|<severidad>|<ext>`.
    Los campos del esquema que no tienen clave CEF estandar van en las
    claves personalizadas csN/cnN con su etiqueta csNLabel/cnNLabel, como
    indica el estandar.
    """

    def formatear(self, evento: dict[str, Any]) -> str:
        _validar_evento(evento)
        resultado = str(evento["resultado"])
        severidad = SEVERIDAD_CEF_POR_RESULTADO.get(resultado, 5)
        rt = int(datetime.fromisoformat(str(evento["timestamp"])).timestamp() * 1000)
        extension = {
            "rt": str(rt),
            "cs1Label": "configuracion",
            "cs1": str(evento["configuracion"]),
            "cs2Label": "mecanismos_activos",
            "cs2": ",".join(evento["mecanismos_activos"] or []),
            "cs3Label": "vector_probado",
            "cs3": str(evento["vector_probado"] or ""),
            "cs4Label": "modelo_destino",
            "cs4": str(evento["modelo_destino"]),
            "cs5Label": "mecanismo_que_bloqueo",
            "cs5": str(evento["mecanismo_que_bloqueo"] or ""),
            "cn1Label": "latencia_ms",
            "cn1": str(int(evento["latencia_ms"])),
        }
        if evento.get("es_extension"):
            extension["cs6Label"] = "herramientas_invocadas"
            extension["cs6"] = ",".join(evento.get("herramientas_invocadas") or [])
        cabecera = "|".join(
            [
                "CEF:0",
                "IronVeil",
                "Proxy",
                VERSION_PRODUCTO,
                _escapar_cabecera_cef(resultado),
                _escapar_cabecera_cef(f"IronVeil {resultado}"),
                str(severidad),
            ]
        )
        cuerpo = " ".join(
            f"{clave}={_escapar_extension_cef(valor)}"
            for clave, valor in extension.items()
        )
        return f"{cabecera}|{cuerpo}"


def exportar_a_siem(evento: dict[str, Any]) -> str:
    """Convierte un evento del log interno al formato que ingiere Wazuh.

    Funcion pura (sin red, sin archivos, sin estado): recibe el mismo dict
    que escribe `_registrar_evento()` en `resultados/<fecha>/eventos.jsonl`
    y devuelve UNA linea JSON lista para que un agente Wazuh la lea con
    `<log_format>json</log_format>`. Lanza ValueError si el evento no
    cumple el esquema base. Para CEF, usar `FormateadorCEF().formatear()`.
    """
    return FormateadorWazuhJSON().formatear(evento)

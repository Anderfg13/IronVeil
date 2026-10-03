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


# --- Exportacion a Wazuh (JSON) y a CEF -----------------------------------
#
# `exportar_a_siem()` es la funcion pura de la tarea de extensiones: recibe un
# evento del log interno y devuelve el string listo para un SIEM. Sin red, sin
# disco, sin estado -> se prueba sin Wazuh.
#
# Formato principal: JSON de UNA linea, para el modulo de lectura de logs de
# Wazuh (`<localfile><log_format>json</log_format>`): exige un objeto JSON por
# linea y expone cada campo como `data.<campo>` en la alerta. Por eso:
#   - los campos del esquema interno conservan su nombre (contrato estable,
#     CLAUDE.md seccion 4): `data.resultado`, `data.vector_probado`...
#   - las listas (`mecanismos_activos`) se aplanan a una cadena separada por
#     comas: es el unico campo no escalar y asi una regla de Wazuh puede
#     filtrarlo sin depender de como decodifique arreglos.
#   - se agrega `integration: "ironveil"`, la marca que usan las reglas
#     (`docs/siem/wazuh/ironveil_rules.xml`) para reconocer nuestros eventos
#     entre cualquier otro JSON que lea el mismo agente.
# Wazuh no deriva el nivel de alerta del evento: lo asigna una regla. Por eso
# el JSON NO lleva "severidad"; la traduccion resultado -> nivel vive en las
# reglas. CEF si la lleva (campo obligatorio de su cabecera).

CAMPOS_BASE: tuple[str, ...] = (
    "timestamp",
    "configuracion",
    "mecanismos_activos",
    "vector_probado",
    "modelo_destino",
    "resultado",
    "mecanismo_que_bloqueo",
    "latencia_ms",
)

FORMATOS_SIEM: tuple[str, ...] = ("json", "cef")

MARCA_INTEGRACION = "ironveil"

_CEF_VERSION = "0"
_CEF_VENDOR = "IronVeil"
_CEF_PRODUCT = "IronVeil Proxy"
_CEF_PRODUCT_VERSION = "1.0"

# resultado -> (SignatureID, nombre legible, severidad CEF 0-10). Un ataque
# que SI logro su objetivo es lo unico que un analista debe ver primero.
_CEF_POR_RESULTADO: dict[str, tuple[str, str, int]] = {
    "bloqueado": ("IV-100", "Peticion bloqueada por un mecanismo", 5),
    "exitoso_para_atacante": ("IV-200", "Ataque exitoso para el atacante", 9),
    "permitido_normal": ("IV-300", "Peticion permitida", 1),
}

# campo del evento -> (clave CEF de usuario, etiqueta). CEF no tiene claves
# estandar para los campos de IronVeil: se usan csN (texto) y cnN (entero),
# cada una con su `...Label`. Los campos extendidos no listados aqui solo
# viajan en el formato JSON.
_CEF_NUMERICOS: dict[str, tuple[str, str]] = {
    "latencia_ms": ("cn1", "latencia_ms"),
    "latencia_clasificador_ms": ("cn2", "latencia_clasificador_ms"),
    "tiempo_revision_humana_ms": ("cn3", "tiempo_revision_humana_ms"),
}

_CEF_TEXTOS: dict[str, tuple[str, str]] = {
    "configuracion": ("cs1", "configuracion"),
    "vector_probado": ("cs2", "vector_probado"),
    "modelo_destino": ("cs3", "modelo_destino"),
    "mecanismo_que_bloqueo": ("cs4", "mecanismo_que_bloqueo"),
    "mecanismos_activos": ("cs5", "mecanismos_activos"),
    "tipo_variante": ("cs6", "tipo_variante"),
}


def _validar_evento(evento: dict[str, Any]) -> None:
    """Falla ruidosamente si falta alguno de los 8 campos base (nada de
    eventos a medias llegando a un SIEM) o si `resultado` no es uno de los
    tres valores del contrato."""
    faltantes = [campo for campo in CAMPOS_BASE if campo not in evento]
    if faltantes:
        raise ValueError(f"evento sin campos base obligatorios: {faltantes}")
    if evento["resultado"] not in _CEF_POR_RESULTADO:
        raise ValueError(f"resultado fuera del contrato: {evento['resultado']!r}")


def _aplanar_listas(evento: dict[str, Any]) -> dict[str, Any]:
    """Copia de `evento` con las listas como cadena separada por comas."""
    return {
        clave: ",".join(str(x) for x in valor) if isinstance(valor, list) else valor
        for clave, valor in evento.items()
    }


def _a_wazuh_json(evento: dict[str, Any]) -> str:
    """JSON de una linea para `log_format json` de Wazuh.

    Los campos con valor `null` se OMITEN: verificado en Wazuh 4.14.8
    (`wazuh-logtest`), su decodificador JSON convierte `null` en la CADENA
    "null", que en un dashboard se leeria como un mecanismo llamado "null".
    Ausente significa lo mismo que `null` en el esquema interno (p. ej. sin
    `mecanismo_que_bloqueo` = nadie bloqueo).
    """
    carga = {"integration": MARCA_INTEGRACION}
    carga.update({k: v for k, v in _aplanar_listas(evento).items() if v is not None})
    return json.dumps(carga, ensure_ascii=False, separators=(",", ":"))


def _cef_escapar_cabecera(valor: str) -> str:
    """En la cabecera CEF hay que escapar la barra invertida y `|`."""
    return valor.replace("\\", "\\\\").replace("|", "\\|")


def _cef_escapar_extension(valor: str) -> str:
    """En la extension CEF hay que escapar la barra invertida, `=` y los
    saltos de linea (estos ultimos como la secuencia literal `\\n`)."""
    return (
        valor.replace("\\", "\\\\")
        .replace("=", "\\=")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )


def _cef_epoch_ms(timestamp_iso: str) -> int | None:
    """Epoch en milisegundos del timestamp ISO 8601, o None si no parsea
    (el SIEM usara entonces su hora de recepcion)."""
    try:
        return int(datetime.fromisoformat(timestamp_iso).timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def _a_cef(evento: dict[str, Any]) -> str:
    """Una linea CEF:0 (ArcSight Common Event Format).

    Cabecera: CEF:Version|Vendor|Product|ProductVersion|SignatureID|Name|Severity
    Extension: pares clave=valor separados por espacio.
    """
    firma, nombre, severidad = _CEF_POR_RESULTADO[evento["resultado"]]
    cabecera = "|".join(
        _cef_escapar_cabecera(parte)
        for parte in (
            f"CEF:{_CEF_VERSION}",
            _CEF_VENDOR,
            _CEF_PRODUCT,
            _CEF_PRODUCT_VERSION,
            firma,
            nombre,
            str(severidad),
        )
    )
    pares: list[str] = []
    marca_tiempo = _cef_epoch_ms(str(evento["timestamp"]))
    if marca_tiempo is not None:
        pares.append(f"rt={marca_tiempo}")
    pares.append(f"act={_cef_escapar_extension(str(evento['resultado']))}")
    plano = _aplanar_listas(evento)
    for campo, (clave, etiqueta) in _CEF_TEXTOS.items():
        if plano.get(campo) is not None:
            pares.append(f"{clave}Label={etiqueta}")
            pares.append(f"{clave}={_cef_escapar_extension(str(plano[campo]))}")
    for campo, (clave, etiqueta) in _CEF_NUMERICOS.items():
        valor = plano.get(campo)
        if isinstance(valor, int) and not isinstance(valor, bool):
            pares.append(f"{clave}Label={etiqueta}")
            pares.append(f"{clave}={valor}")
    return f"{cabecera}|{' '.join(pares)}"


def exportar_a_siem(evento: dict[str, Any], formato: str = "json") -> str:
    """Convierte un evento del log interno al string que espera el SIEM.

    Funcion pura: no muta `evento`, no hace E/S. `formato`:
    - "json" (por defecto): una linea JSON para el `log_format json` de Wazuh.
    - "cef": una linea Common Event Format (por syslog u otro SIEM).

    Lanza `ValueError` si falta un campo base, si `resultado` no es uno de
    los tres valores del contrato o si `formato` no existe.
    """
    if formato not in FORMATOS_SIEM:
        raise ValueError(f"formato SIEM desconocido: {formato!r} ({FORMATOS_SIEM})")
    _validar_evento(evento)
    return _a_wazuh_json(evento) if formato == "json" else _a_cef(evento)


class FormateadorWazuhJSON:
    """Adapter de `FormateadorSIEM`: envuelve `exportar_a_siem(..., "json")`."""

    def formatear(self, evento: dict[str, Any]) -> str:
        return exportar_a_siem(evento, "json")


class FormateadorCEF:
    """Adapter de `FormateadorSIEM`: envuelve `exportar_a_siem(..., "cef")`."""

    def formatear(self, evento: dict[str, Any]) -> str:
        return exportar_a_siem(evento, "cef")

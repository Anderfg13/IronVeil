"""Stubs de los 5 mecanismos defensivos de IronVeil y carga de configuracion.

Ningun mecanismo tiene logica real todavia. Cada funcion respeta ya la firma
y el comportamiento neutro (equivalente a passthrough) descritos en su
docstring, para que el resto del equipo pueda cablearlas en el proxy sin
esperar a que esten implementadas. Ver CLAUDE.md, seccion "Contratos
estables", para el contrato compartido por las cuatro personas del equipo.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

FLAGS_REQUERIDAS: tuple[str, ...] = (
    "filtrado",
    "delimitacion",
    "clasificacion",
    "minimo_privilegio",
    "aprobacion_humana",
)

# Mecanismo 1 (filtrado). Patrones de entrada conocidos de prompt injection /
# intento de extraccion de instrucciones. Definidos una sola vez aqui, nunca
# repetidos ni incrustados en filtrar(). No son secretos: es la lista de
# frases que el filtro reconoce, no una credencial.
PATRONES_PROHIBIDOS_ENTRADA: tuple[re.Pattern[str], ...] = tuple(
    re.compile(patron, re.IGNORECASE)
    for patron in (
        r"ignora(?:r)?\s+(?:todas\s+)?(?:tus\s+)?instrucciones",
        r"olvida(?:r)?\s+(?:las\s+)?reglas\s+anteriores",
        r"modo\s+desarrollador",
        r"cu[aá]l\s+es\s+tu\s+configuraci[oó]n\s+inicial",
        r"system\s+prompt",
    )
)

# Mecanismo 1 (filtrado), direccion "salida". Solo la ESTRUCTURA del
# identificador (prefijo + digitos), nunca el valor real de la credencial:
# los valores viven en .env / Modelfiles, jamas aqui (ver CLAUDE.md, regla 2).
PATRON_CREDENCIAL_CANARIO = re.compile(r"\b(?:SPT|RRHH)-DEMO-\d+\b")

TEXTO_REDACTADO = "[REDACTADO]"


def cargar_config(ruta: Path | str = CONFIG_PATH) -> dict[str, bool]:
    """Carga config.yaml y devuelve las 5 banderas de mecanismos.

    Recibe la ruta al archivo de configuracion (por defecto, config.yaml en
    la raiz del proyecto). Usa yaml.safe_load(), nunca yaml.load(), porque
    el archivo puede llegar a editarse por varias personas y no debe poder
    ejecutar codigo arbitrario.

    Devuelve un diccionario con exactamente las 5 claves de
    FLAGS_REQUERIDAS, cada una con un valor booleano.

    Falla ruidosamente (nunca con un default silencioso) si:
    - el archivo no existe (FileNotFoundError),
    - la raiz del YAML no es un mapeo (ValueError),
    - falta alguna de las 5 claves obligatorias (ValueError),
    - alguna clave no tiene un valor booleano (ValueError).
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encontro el archivo de configuracion: {ruta}")

    with ruta.open("r", encoding="utf-8") as f:
        datos: Any = yaml.safe_load(f)

    if not isinstance(datos, dict):
        # ValueError, no TypeError: el problema es el contenido de un archivo
        # externo mal formado, no un argumento invalido de esta funcion.
        raise ValueError(  # noqa: TRY004
            f"{ruta} no contiene un mapeo YAML valido en la raiz."
        )

    faltantes = [clave for clave in FLAGS_REQUERIDAS if clave not in datos]
    if faltantes:
        raise ValueError(
            f"Faltan claves obligatorias en {ruta}: {', '.join(faltantes)}"
        )

    config: dict[str, bool] = {}
    for clave in FLAGS_REQUERIDAS:
        valor = datos[clave]
        if not isinstance(valor, bool):
            # ValueError, no TypeError: mismo caso, es un valor de config.yaml
            # invalido, no un argumento invalido de esta funcion.
            raise ValueError(  # noqa: TRY004
                f"La clave '{clave}' en {ruta} debe ser booleana "
                f"(true/false), se encontro {valor!r}."
            )
        config[clave] = valor

    return config


def filtrar(texto: str, direccion: str) -> tuple[str, bool]:
    """Mecanismo 1 (filtrado): determinista, basado en patrones/regex.

    Recibe el texto a evaluar y `direccion` ("entrada" | "salida"). No tiene
    efectos secundarios: no escribe el log ni conoce la configuracion activa,
    solo decide sobre el texto que recibe.

    Si `direccion == "entrada"`: compara el texto contra
    PATRONES_PROHIBIDOS_ENTRADA (intentos conocidos de prompt injection /
    extraccion de instrucciones). Si hay coincidencia, retorna
    (texto_original, True) sin modificar el texto: la decision de rechazar
    la peticion completa la toma quien llama, no esta funcion.

    Si `direccion == "salida"`: busca PATRON_CREDENCIAL_CANARIO (el formato
    SPT-DEMO-<numero> / RRHH-DEMO-<numero>) y reemplaza cada coincidencia por
    TEXTO_REDACTADO. Retorna (texto_redactado, True) si redacto algo.

    Si no hay coincidencia en ningun caso, retorna (texto, False).

    Lanza ValueError si `direccion` no es "entrada" ni "salida".
    """
    if direccion == "entrada":
        bloquear = any(patron.search(texto) for patron in PATRONES_PROHIBIDOS_ENTRADA)
        return texto, bloquear

    if direccion == "salida":
        texto_redactado, coincidencias = PATRON_CREDENCIAL_CANARIO.subn(
            TEXTO_REDACTADO, texto
        )
        return texto_redactado, coincidencias > 0

    raise ValueError(f"direccion invalida para filtrar(): {direccion!r}")


def delimitar(system_prompt: str, entrada_usuario: str) -> str:
    """Mecanismo 2 (delimitacion / spotlighting): determinista, funcion pura.

    Recibe el system prompt del modelo destino y la entrada cruda del
    usuario. Sin red, sin estado.

    Cuando este implementado, envolvera `entrada_usuario` con delimitadores
    explicitos (por ejemplo, tags) para que el modelo distinga con claridad
    las instrucciones del sistema del contenido no confiable del usuario,
    reduciendo el riesgo de prompt injection.

    Devuelve el texto final que se enviaria como entrada del usuario.

    Stub: no hay logica todavia. Ignora `system_prompt` y retorna
    `entrada_usuario` sin modificar, comportamiento neutro equivalente a
    que el mecanismo este desactivado.
    """
    return entrada_usuario


def clasificar(texto: str, direccion: str) -> bool:
    """Mecanismo 3 (clasificacion): probabilistico, basado en un modelo.

    Recibe el texto a evaluar y `direccion` ("entrada" | "salida").
    True significa "unsafe".

    Cuando este implementado, llamara a un modelo clasificador (Llama
    Guard) con timeout explicito. Ante timeout o respuesta malformada debe
    hacer fail closed (devolver True), nunca dejar pasar por defecto.

    Stub: no hay logica ni llamada a red todavia. Retorna siempre False.
    Este False es el comportamiento neutro de "mecanismo desactivado", NO
    el fail-open que tendria un timeout real una vez implementado; no
    confundir uno con otro al leer los logs de esta semana.
    """
    return False


def validar_privilegio(modelo_destino: str, texto_entrada: str) -> bool:
    """Mecanismo 4 (minimo privilegio): determinista, regex de dominio.

    Recibe el modelo al que va dirigida la peticion (por ejemplo,
    "soporte") y el texto de entrada. True significa "se detecto una
    credencial de otro dominio" y por lo tanto debe rechazarse.

    Cuando este implementado, comparara patrones de credenciales conocidas
    de un dominio (por ejemplo, el formato de RRHH-DEMO-*) contra el texto
    dirigido a un modelo de otro dominio (por ejemplo, "soporte"), para
    detectar intentos de movimiento lateral (V4, paso 2).

    Stub: no hay logica todavia. Retorna siempre False (nunca rechaza),
    comportamiento neutro equivalente a que el mecanismo este desactivado.
    """
    return False


def enviar_a_revision(peticion: dict) -> bool:
    """Mecanismo 5 (aprobacion humana + rate limit): humano en el loop.

    Recibe la peticion completa a encolar. Devuelve una senal de
    "pendiente" (True si quedo encolada para revision).

    Cuando este implementado, encolara la peticion en una cola compartida
    entre peticiones concurrentes (protegida con lock), aplicara el limite
    de peticiones por minuto y conservara que otros mecanismos ya la
    hubieran marcado, para que quien revise tenga contexto.

    Stub: no hay logica ni cola todavia. Retorna siempre False (nunca
    encola nada), comportamiento neutro equivalente a que el mecanismo
    este desactivado.
    """
    return False

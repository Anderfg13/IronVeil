"""Normalizacion de la entrada (EXTENSION opcional): cubre los ataques que se esconden.

Un filtro que busca «ignora las instrucciones» no ve esa frase si viene en Base64, en
hexadecimal, en ROT13 o en caracteres Unicode invisibles; Prompt Guard tampoco (ve
ruido). Esta extension actua ANTES del modelo y de la cadena de mecanismos:

1. quita los caracteres invisibles (el modelo recibe el texto limpio) y lee el ASCII que
   esconden los del bloque «Tags»;
2. decodifica los tramos Base64, hex y el ROT13 del mensaje, y solo si lo decodificado
   es texto legible;
3. inspecciona todo eso con la MISMA cadena (filtrado, clasificacion, minimo
   privilegio), que bloquea si lo escondido era malicioso.

Cada capa depende solo de la de abajo y solo `composicion.py` lee el entorno:

    composicion       lee el entorno y arma las piezas; `analizar()` lo usa main.py
    servicio          `Normalizador`: limpia y decodifica en capas (puro)
    registro          del nombre al decodificador (un objeto; ampliable)
    decodificadores/  un adaptador por codificacion: base64, hex, rot13
    puerto            `Decodificador` (un metodo) y `ErrorNormalizacion`
    dominio           que es «invisible» y que es «texto legible» (sin E/S)

Apagada salvo `NORMALIZACION_ENTRADA=1`. Guia: docs/NORMALIZACION_DE_ENTRADA.md.
"""

from __future__ import annotations

from proxy.normalizacion.composicion import analizar, descripcion, obtener
from proxy.normalizacion.dominio import Hallazgo, Resultado
from proxy.normalizacion.puerto import Decodificador, ErrorNormalizacion
from proxy.normalizacion.servicio import Normalizador

__all__ = [
    "Decodificador",
    "ErrorNormalizacion",
    "Hallazgo",
    "Normalizador",
    "Resultado",
    "analizar",
    "descripcion",
    "obtener",
]

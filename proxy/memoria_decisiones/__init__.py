"""Memoria de decisiones humanas (EXTENSION opcional, apagada por defecto).

Cuando un humano **rechaza** una peticion que un mecanismo retuvo, el proxy recuerda ese
mensaje: la proxima vez que llegue el mismo (para el mismo modelo) se rechaza al
instante, sin pasar por la cola ni por la cadena. No es aprendizaje automatico: es una
memoria de decisiones, exacta y revocable. Guia: docs/MEMORIA_DE_DECISIONES.md.

Arquitectura (puertos y adaptadores): cada capa depende solo de la de abajo.

    composicion  lee el entorno y cablea todo (el unico sitio que conoce el `.env`)
    servicio     el caso de uso; depende del puerto, no de ninguna base de datos
    puerto       AlmacenMemoria: el contrato que cumple cada adaptador
    almacenes/   un adaptador por archivo (JSON Lines, SQLite); otros se agregan desde
                 fuera con MEMORIA_RECHAZOS_ADAPTADORES, sin editar este paquete
    dominio      que es una regla y como se compara; no depende de nada

Reglas de diseno:
- Solo se recuerdan rechazos (nunca aprobaciones) y solo retenciones por contenido.
- Solo coincidencia exacta tras normalizar: no frena parafrasis; es un complemento.
- Persistente y revocable. Se guardan huellas (SHA-256) y una vista previa corta con las
  credenciales redactadas, nunca el mensaje completo.
- Con la memoria activa los ataques repetidos se bloquean solos tras el primer rechazo:
  los resultados de C0-C6 se midieron SIN ella; sus eventos llevan
  `origen_decision: "memoria"` y `es_extension`.
"""

from __future__ import annotations

from proxy.memoria_decisiones.composicion import (
    Configuracion,
    cerrar,
    esta_activa,
    obtener,
)
from proxy.memoria_decisiones.dominio import (
    LARGO_VISTA_PREVIA,
    MOTIVOS_QUE_SE_RECUERDAN,
    Regla,
    Resultado,
    huella,
    normalizar,
)
from proxy.memoria_decisiones.puerto import AlmacenMemoria, ErrorAlmacen
from proxy.memoria_decisiones.registro import RegistroAlmacenes, cargar_adaptadores
from proxy.memoria_decisiones.servicio import MemoriaDecisiones

__all__ = [
    "LARGO_VISTA_PREVIA",
    "MOTIVOS_QUE_SE_RECUERDAN",
    "AlmacenMemoria",
    "Configuracion",
    "ErrorAlmacen",
    "MemoriaDecisiones",
    "RegistroAlmacenes",
    "Regla",
    "Resultado",
    "cargar_adaptadores",
    "cerrar",
    "esta_activa",
    "huella",
    "normalizar",
    "obtener",
]

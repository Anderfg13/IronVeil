"""ECS (Elastic Common Schema): JSON para Elasticsearch, OpenSearch y Security Onion.

Solo se llenan los campos ECS que el evento realmente sabe; todo lo propio de IronVeil
va bajo el espacio `ironveil.*` (la convencion de ECS para campos a medida), asi no se
inventa un significado ECS que no existe.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from proxy.siem.evento import (
    FABRICANTE,
    MARCA_INTEGRACION,
    PRODUCTO,
    clasificar_resultado,
    es_entero,
    sin_nulos,
    validar_evento,
)

_VERSION_ECS = "8.11"
_TIPO_ECS_POR_RESULTADO = {
    "bloqueado": ["denied"],
    "exitoso_para_atacante": ["allowed"],
    "permitido_normal": ["allowed"],
}
_NANOSEGUNDOS_POR_MS = 1_000_000


class FormateadorECS:
    """Un documento ECS de una linea."""

    tipo_contenido: ClassVar[str] = "application/json"

    def formatear(self, evento: dict[str, Any]) -> str:
        validar_evento(evento)
        clasificacion = clasificar_resultado(evento)
        suceso: dict[str, Any] = {
            "kind": "event",
            "module": MARCA_INTEGRACION,
            "dataset": f"{MARCA_INTEGRACION}.proxy",
            "category": ["intrusion_detection"],
            "type": _TIPO_ECS_POR_RESULTADO[evento["resultado"]],
            "action": evento["resultado"],
            "code": clasificacion.id_firma,
            "severity": clasificacion.severidad,
        }
        if evento.get("mecanismo_que_bloqueo") is not None:
            suceso["reason"] = evento["mecanismo_que_bloqueo"]
        if es_entero(evento.get("latencia_ms")):
            suceso["duration"] = evento["latencia_ms"] * _NANOSEGUNDOS_POR_MS
        documento: dict[str, Any] = {
            "@timestamp": evento["timestamp"],
            "ecs": {"version": _VERSION_ECS},
            "event": suceso,
            "observer": {
                "vendor": FABRICANTE,
                "product": PRODUCTO,
                "type": "proxy",
            },
            MARCA_INTEGRACION: sin_nulos(
                {c: v for c, v in evento.items() if c != "timestamp"}
            ),
        }
        return json.dumps(documento, ensure_ascii=False, separators=(",", ":"))

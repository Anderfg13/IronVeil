"""Formatos JSON: el evento tal cual (referencia) y el de Wazuh."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from proxy.siem.evento import (
    MARCA_INTEGRACION,
    aplanar_listas,
    sin_nulos,
    validar_evento,
)


class FormateadorJSON:
    """Referencia: el evento tal cual, como JSON de una linea (sin validar)."""

    tipo_contenido: ClassVar[str] = "application/json"

    def formatear(self, evento: dict[str, Any]) -> str:
        return json.dumps(evento, ensure_ascii=False)


class FormateadorWazuhJSON:
    """JSON de una linea para el `log_format json` de Wazuh (y para cualquier SIEM que
    lea JSON plano: Splunk, Elastic con Filebeat, Sentinel...).

    - Los campos del esquema interno conservan su nombre (contrato estable,
      CLAUDE.md seccion 4): `data.resultado`, `data.vector_probado`...
    - Las listas se aplanan a una cadena separada por comas, para que una regla pueda
      filtrarlas sin depender de como decodifique arreglos.
    - Se agrega `integration: "ironveil"`, la marca de las reglas de
      `docs/siem/wazuh/ironveil_rules.xml`.
    - Los campos `null` se OMITEN: verificado en Wazuh 4.14.8 (`wazuh-logtest`), su
      decodificador convierte `null` en la CADENA "null".
    - No lleva severidad: Wazuh la asigna una regla, no el evento.
    """

    tipo_contenido: ClassVar[str] = "application/json"

    def formatear(self, evento: dict[str, Any]) -> str:
        validar_evento(evento)
        carga: dict[str, Any] = {"integration": MARCA_INTEGRACION}
        carga.update(sin_nulos(aplanar_listas(evento)))
        return json.dumps(carga, ensure_ascii=False, separators=(",", ":"))

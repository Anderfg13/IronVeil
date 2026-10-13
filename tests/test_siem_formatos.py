"""Los formatos nuevos (LEEF, ECS) y el contrato comun de todos los formatos."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest

from proxy.siem import FORMATOS_SIEM, FormateadorSIEM, exportar_a_siem
from proxy.siem.formatos import FORMATOS_INCLUIDOS

EVENTO: dict[str, Any] = {
    "timestamp": "2026-10-06T14:32:11-05:00",
    "configuracion": "C6",
    "mecanismos_activos": ["filtrado", "clasificacion"],
    "vector_probado": "V3-A",
    "modelo_destino": "soporte",
    "resultado": "bloqueado",
    "mecanismo_que_bloqueo": "filtrado",
    "latencia_ms": 812,
    "latencia_clasificador_ms": 68,
    "tipo_variante": None,
}


@pytest.mark.parametrize("formato", sorted(FORMATOS_INCLUIDOS))
def test_todo_formato_produce_una_sola_linea_y_no_muta_el_evento(formato: str) -> None:
    original = deepcopy(EVENTO)

    salida = exportar_a_siem(EVENTO, formato)

    assert "\n" not in salida
    assert EVENTO == original


@pytest.mark.parametrize("formato", sorted(FORMATOS_INCLUIDOS))
def test_todo_formato_cumple_el_contrato_del_puerto(formato: str) -> None:
    assert isinstance(FORMATOS_INCLUIDOS[formato](), FormateadorSIEM)


@pytest.mark.parametrize("formato", sorted(FORMATOS_INCLUIDOS))
def test_todo_formato_rechaza_un_evento_a_medias(formato: str) -> None:
    sin_resultado = {k: v for k, v in EVENTO.items() if k != "resultado"}

    with pytest.raises(ValueError, match="campos base"):
        exportar_a_siem(sin_resultado, formato)


def test_los_formatos_incluidos_son_los_anunciados() -> None:
    assert set(FORMATOS_SIEM) == {"json", "cef", "leef", "ecs"}


# --- LEEF ---------------------------------------------------------------------


def test_leef_lleva_cabecera_y_atributos_separados_por_tabulador() -> None:
    linea = exportar_a_siem(EVENTO, "leef")

    cabecera, _, cuerpo = linea.partition("|IV-100|")
    assert cabecera == "LEEF:1.0|IronVeil|IronVeil Proxy|1.0"
    atributos = dict(par.split("=", 1) for par in cuerpo.split("\t"))
    assert atributos["cat"] == "bloqueado"
    assert atributos["sev"] == "5"
    assert atributos["mecanismos_activos"] == "filtrado,clasificacion"
    assert atributos["latencia_ms"] == "812"


def test_leef_omite_los_campos_nulos() -> None:
    assert "tipo_variante" not in exportar_a_siem(EVENTO, "leef")


def test_leef_un_tabulador_o_salto_en_un_valor_no_parte_el_atributo() -> None:
    evento = {**EVENTO, "modelo_destino": "so\tpor\nte"}

    atributos = exportar_a_siem(evento, "leef").partition("|IV-100|")[2].split("\t")

    assert "modelo_destino=so por te" in atributos


# --- ECS ----------------------------------------------------------------------


def test_ecs_llena_solo_campos_que_conoce_y_el_resto_va_en_ironveil() -> None:
    doc = json.loads(exportar_a_siem(EVENTO, "ecs"))

    assert doc["@timestamp"] == EVENTO["timestamp"]
    assert doc["event"]["action"] == "bloqueado"
    assert doc["event"]["type"] == ["denied"]
    assert doc["event"]["reason"] == "filtrado"
    assert doc["event"]["duration"] == 812 * 1_000_000
    assert doc["observer"]["vendor"] == "IronVeil"
    assert doc["ironveil"]["vector_probado"] == "V3-A"
    assert doc["ironveil"]["mecanismos_activos"] == ["filtrado", "clasificacion"]


def test_ecs_no_duplica_el_timestamp_ni_lleva_nulos() -> None:
    propios = json.loads(exportar_a_siem(EVENTO, "ecs"))["ironveil"]

    assert "timestamp" not in propios
    assert "tipo_variante" not in propios


def test_ecs_un_ataque_exitoso_tiene_la_severidad_mas_alta() -> None:
    evento = {
        **EVENTO,
        "resultado": "exitoso_para_atacante",
        "mecanismo_que_bloqueo": None,
    }

    doc = json.loads(exportar_a_siem(evento, "ecs"))

    assert doc["event"]["severity"] == 9
    assert "reason" not in doc["event"]

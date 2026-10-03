"""Pruebas unitarias del andamiaje SIEM (patron Adapter, proxy/siem.py).

No prueban ningun SIEM real (todavia no existe esa integracion) -- solo que
los dos adapters de referencia funcionan y que enviar_a_siem() los compone
correctamente sin acoplarse a ninguno en concreto.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from proxy.siem import (
    VERSION_PRODUCTO,
    ConectorArchivoLocal,
    ConectorSIEM,
    FormateadorCEF,
    FormateadorJSON,
    FormateadorSIEM,
    FormateadorWazuhJSON,
    enviar_a_siem,
    exportar_a_siem,
)

EVENTO_EJEMPLO: dict[str, Any] = {
    "timestamp": "2026-09-25T00:00:00-05:00",
    "configuracion": "C1",
    "mecanismos_activos": ["filtrado"],
    "vector_probado": "V3-A",
    "modelo_destino": "soporte",
    "resultado": "bloqueado",
    "mecanismo_que_bloqueo": "filtrado",
    "latencia_ms": 12,
}


def test_formateador_json_produce_una_linea_json_valida() -> None:
    formateador = FormateadorJSON()

    mensaje = formateador.formatear(EVENTO_EJEMPLO)

    assert json.loads(mensaje) == EVENTO_EJEMPLO
    assert "\n" not in mensaje


def test_conector_archivo_local_agrega_una_linea_por_envio(tmp_path: Path) -> None:
    ruta = tmp_path / "siem" / "eventos_siem.jsonl"
    conector = ConectorArchivoLocal(ruta)

    conector.enviar('{"a": 1}')
    conector.enviar('{"a": 2}')

    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert lineas == ['{"a": 1}', '{"a": 2}']


def test_conector_archivo_local_crea_el_directorio_si_no_existe(tmp_path: Path) -> None:
    ruta = tmp_path / "no_existe_todavia" / "eventos_siem.jsonl"
    conector = ConectorArchivoLocal(ruta)

    conector.enviar('{"a": 1}')

    assert ruta.is_file()


def test_enviar_a_siem_compone_formateador_y_conector(tmp_path: Path) -> None:
    ruta = tmp_path / "eventos_siem.jsonl"

    enviar_a_siem(EVENTO_EJEMPLO, FormateadorJSON(), ConectorArchivoLocal(ruta))

    linea = ruta.read_text(encoding="utf-8").strip()
    assert json.loads(linea) == EVENTO_EJEMPLO


def test_enviar_a_siem_no_conoce_el_adapter_concreto() -> None:
    """Cualquier objeto con formatear()/enviar() sirve -- typing
    estructural de Protocol, no hace falta heredar de FormateadorSIEM ni
    ConectorSIEM. Esto es lo que permite envolver el SDK de un SIEM real
    sin una capa de mas."""

    class _FormateadorFalso:
        def formatear(self, evento: dict[str, Any]) -> str:
            return f"CUSTOM:{evento['resultado']}"

    class _ConectorFalso:
        def __init__(self) -> None:
            self.recibidos: list[str] = []

        def enviar(self, mensaje: str) -> None:
            self.recibidos.append(mensaje)

    formateador: FormateadorSIEM = _FormateadorFalso()
    conector = _ConectorFalso()

    enviar_a_siem(EVENTO_EJEMPLO, formateador, conector)

    assert conector.recibidos == ["CUSTOM:bloqueado"]
    # Confirma tambien que ConectorSIEM (Protocol) no exige heredar.
    assert isinstance(conector, ConectorSIEM)


# --- exportar_a_siem() / Wazuh JSON / CEF (extension del 17 de octubre) -----

EVENTO_EXTENSION: dict[str, Any] = {
    **EVENTO_EJEMPLO,
    "configuracion": "C5",
    "mecanismos_activos": ["aprobacion_humana"],
    "vector_probado": "V7-A",
    "modelo_destino": "rrhh",
    "mecanismo_que_bloqueo": "aprobacion_humana",
    "es_extension": True,
    "herramientas_invocadas": ["enviar_correo"],
}


def test_exportar_a_siem_es_una_linea_json_valida_para_wazuh() -> None:
    mensaje = exportar_a_siem(EVENTO_EJEMPLO)

    assert "\n" not in mensaje
    decodificado = json.loads(mensaje)
    assert decodificado["@source"] == "ironveil"
    assert decodificado["timestamp"] == EVENTO_EJEMPLO["timestamp"]
    assert decodificado["ironveil"] == EVENTO_EJEMPLO


def test_exportar_a_siem_es_pura() -> None:
    copia = dict(EVENTO_EJEMPLO)
    assert exportar_a_siem(EVENTO_EJEMPLO) == exportar_a_siem(EVENTO_EJEMPLO)
    assert copia == EVENTO_EJEMPLO


def test_exportar_a_siem_escapa_saltos_de_linea_en_valores() -> None:
    evento = {**EVENTO_EJEMPLO, "vector_probado": "linea1\nlinea2"}
    mensaje = exportar_a_siem(evento)
    assert "\n" not in mensaje
    assert json.loads(mensaje)["ironveil"]["vector_probado"] == "linea1\nlinea2"


def test_exportar_a_siem_incluye_campos_de_extension() -> None:
    decodificado = json.loads(exportar_a_siem(EVENTO_EXTENSION))
    assert decodificado["ironveil"]["es_extension"] is True
    assert decodificado["ironveil"]["herramientas_invocadas"] == ["enviar_correo"]


def test_exportar_a_siem_falla_si_falta_un_campo_base() -> None:
    evento = dict(EVENTO_EJEMPLO)
    del evento["resultado"]
    with pytest.raises(ValueError, match="resultado"):
        exportar_a_siem(evento)


def test_exportar_a_siem_rechaza_array_de_objetos() -> None:
    """El decodificador JSON de Wazuh no soporta arrays de objetos."""
    evento = {**EVENTO_EJEMPLO, "detalle": [{"a": 1}]}
    with pytest.raises(ValueError, match="array de objetos"):
        exportar_a_siem(evento)


def test_formateador_wazuh_cumple_el_protocolo() -> None:
    assert isinstance(FormateadorWazuhJSON(), FormateadorSIEM)
    assert isinstance(FormateadorCEF(), FormateadorSIEM)


def test_formateador_cef_cabecera_y_extension() -> None:
    mensaje = FormateadorCEF().formatear(EVENTO_EJEMPLO)

    cabecera = mensaje.split("|")
    assert cabecera[:7] == [
        "CEF:0",
        "IronVeil",
        "Proxy",
        VERSION_PRODUCTO,
        "bloqueado",
        "IronVeil bloqueado",
        "5",
    ]
    assert "cs1=C1" in mensaje
    assert "cs5=filtrado" in mensaje
    assert "cn1=12" in mensaje
    assert "\n" not in mensaje


def test_formateador_cef_severidad_alta_para_ataque_exitoso() -> None:
    evento = {
        **EVENTO_EJEMPLO,
        "resultado": "exitoso_para_atacante",
        "mecanismo_que_bloqueo": None,
    }
    assert FormateadorCEF().formatear(evento).split("|")[6] == "8"


def test_formateador_cef_escapa_caracteres_especiales() -> None:
    evento = {**EVENTO_EJEMPLO, "vector_probado": "a=b\\c\nd"}
    mensaje = FormateadorCEF().formatear(evento)
    assert "cs3=a\\=b\\\\c\\nd" in mensaje


def test_formateador_cef_incluye_herramientas_en_extension() -> None:
    assert "cs6=enviar_correo" in FormateadorCEF().formatear(EVENTO_EXTENSION)

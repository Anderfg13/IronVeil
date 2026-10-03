"""Pruebas unitarias del andamiaje SIEM (patron Adapter, proxy/siem.py).

No prueban ningun SIEM real (todavia no existe esa integracion) -- solo que
los dos adapters de referencia funcionan y que enviar_a_siem() los compone
correctamente sin acoplarse a ninguno en concreto.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from proxy.siem import (
    ConectorArchivoLocal,
    ConectorSIEM,
    FormateadorJSON,
    FormateadorSIEM,
    enviar_a_siem,
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


# --- exportar_a_siem(): Wazuh JSON y CEF ------------------------------------

from copy import deepcopy  # noqa: E402

import pytest  # noqa: E402

from proxy.siem import (  # noqa: E402
    CAMPOS_BASE,
    FormateadorCEF,
    FormateadorWazuhJSON,
    exportar_a_siem,
)

EVENTO_EXTENDIDO: dict[str, Any] = {
    "timestamp": "2026-10-02T14:32:11-05:00",
    "configuracion": "C6",
    "mecanismos_activos": [
        "filtrado",
        "delimitacion",
        "clasificacion",
        "minimo_privilegio",
        "aprobacion_humana",
    ],
    "vector_probado": "V7-A",
    "modelo_destino": "rrhh-agente",
    "resultado": "bloqueado",
    "mecanismo_que_bloqueo": "aprobacion_humana",
    "latencia_ms": 812,
    "latencia_clasificador_ms": 68,
    "tiempo_revision_humana_ms": 4200,
    "es_extension": True,
}


def test_json_es_una_linea_con_json_valido() -> None:
    salida = exportar_a_siem(EVENTO_EXTENDIDO)

    assert "\n" not in salida
    assert isinstance(json.loads(salida), dict)


def test_json_conserva_los_8_campos_base_y_marca_la_integracion() -> None:
    carga = json.loads(exportar_a_siem(EVENTO_EJEMPLO))

    assert carga["integration"] == "ironveil"
    for campo in CAMPOS_BASE:
        assert campo in carga
    assert carga["resultado"] == "bloqueado"
    assert carga["latencia_ms"] == 12


def test_json_aplana_las_listas_a_cadena_separada_por_comas() -> None:
    carga = json.loads(exportar_a_siem(EVENTO_EXTENDIDO))

    assert carga["mecanismos_activos"] == (
        "filtrado,delimitacion,clasificacion,minimo_privilegio,aprobacion_humana"
    )
    # Ningun valor es lista ni objeto: Wazuh solo ve escalares.
    assert all(not isinstance(v, list | dict) for v in carga.values())


def test_json_conserva_los_campos_extendidos() -> None:
    carga = json.loads(exportar_a_siem(EVENTO_EXTENDIDO))

    assert carga["latencia_clasificador_ms"] == 68
    assert carga["tiempo_revision_humana_ms"] == 4200
    assert carga["es_extension"] is True


def test_json_omite_los_campos_null_porque_wazuh_los_vuelve_la_cadena_null() -> None:
    evento = {**EVENTO_EJEMPLO, "resultado": "permitido_normal"}
    evento["mecanismo_que_bloqueo"] = None

    carga = json.loads(exportar_a_siem(evento))

    assert "mecanismo_que_bloqueo" not in carga
    assert "null" not in exportar_a_siem(evento)


def test_exportar_no_muta_el_evento_de_entrada() -> None:
    original = deepcopy(EVENTO_EXTENDIDO)

    exportar_a_siem(EVENTO_EXTENDIDO, "json")
    exportar_a_siem(EVENTO_EXTENDIDO, "cef")

    assert EVENTO_EXTENDIDO == original


def test_exportar_es_determinista() -> None:
    assert exportar_a_siem(EVENTO_EXTENDIDO) == exportar_a_siem(EVENTO_EXTENDIDO)
    assert exportar_a_siem(EVENTO_EXTENDIDO, "cef") == exportar_a_siem(
        EVENTO_EXTENDIDO, "cef"
    )


def test_json_con_caracteres_especiales_sigue_siendo_una_linea_valida() -> None:
    evento = {**EVENTO_EJEMPLO, "vector_probado": 'V3-"A"\nlinea2|\\'}

    salida = exportar_a_siem(evento)

    assert "\n" not in salida
    assert json.loads(salida)["vector_probado"] == evento["vector_probado"]


@pytest.mark.parametrize("campo", CAMPOS_BASE)
@pytest.mark.parametrize("formato", ["json", "cef"])
def test_falta_un_campo_base_falla_ruidosamente(campo: str, formato: str) -> None:
    evento = dict(EVENTO_EJEMPLO)
    del evento[campo]

    with pytest.raises(ValueError, match=campo):
        exportar_a_siem(evento, formato)


def test_resultado_fuera_del_contrato_falla() -> None:
    with pytest.raises(ValueError, match="resultado"):
        exportar_a_siem({**EVENTO_EJEMPLO, "resultado": "quizas"})


def test_formato_desconocido_falla() -> None:
    with pytest.raises(ValueError, match="formato"):
        exportar_a_siem(EVENTO_EJEMPLO, "leef")


def _partir_cef(linea: str) -> tuple[list[str], str]:
    """Separa cabecera (7 campos) y extension de una linea CEF, respetando
    el escape de `|` con barra invertida."""
    partes: list[str] = []
    actual: list[str] = []
    i = 0
    while len(partes) < 7:
        c = linea[i]
        if c == "\\":
            actual.append(linea[i : i + 2])
            i += 2
            continue
        if c == "|":
            partes.append("".join(actual))
            actual = []
        else:
            actual.append(c)
        i += 1
    return partes, linea[i:]


def test_cef_tiene_la_cabecera_de_7_campos() -> None:
    cabecera, _ = _partir_cef(exportar_a_siem(EVENTO_EXTENDIDO, "cef"))

    assert cabecera[0] == "CEF:0"
    assert cabecera[1] == "IronVeil"
    assert cabecera[2] == "IronVeil Proxy"
    assert cabecera[4] == "IV-100"
    assert cabecera[6] == "5"


@pytest.mark.parametrize(
    ("resultado", "firma", "severidad"),
    [
        ("bloqueado", "IV-100", "5"),
        ("exitoso_para_atacante", "IV-200", "9"),
        ("permitido_normal", "IV-300", "1"),
    ],
)
def test_cef_severidad_segun_resultado(
    resultado: str, firma: str, severidad: str
) -> None:
    cabecera, _ = _partir_cef(
        exportar_a_siem({**EVENTO_EJEMPLO, "resultado": resultado}, "cef")
    )

    assert cabecera[4] == firma
    assert cabecera[6] == severidad


def test_cef_extension_lleva_campos_propios_y_tiempo_en_epoch_ms() -> None:
    _, extension = _partir_cef(exportar_a_siem(EVENTO_EXTENDIDO, "cef"))

    assert "rt=1790969531000" in extension
    assert "act=bloqueado" in extension
    assert "cs1Label=configuracion cs1=C6" in extension
    assert "cs2Label=vector_probado cs2=V7-A" in extension
    assert "cs3Label=modelo_destino cs3=rrhh-agente" in extension
    assert "cs4Label=mecanismo_que_bloqueo cs4=aprobacion_humana" in extension
    assert "cn1Label=latencia_ms cn1=812" in extension
    assert "cn3Label=tiempo_revision_humana_ms cn3=4200" in extension


def test_cef_omite_el_campo_nulo_de_mecanismo_que_bloqueo() -> None:
    evento = {**EVENTO_EJEMPLO, "resultado": "permitido_normal"}
    evento["mecanismo_que_bloqueo"] = None

    _, extension = _partir_cef(exportar_a_siem(evento, "cef"))

    assert "cs4" not in extension


def test_cef_escapa_pipes_y_barras_en_cabecera_y_extension() -> None:
    # Valor con `|`, `=`, una barra invertida y un salto de linea.
    evento = {**EVENTO_EJEMPLO, "vector_probado": "V|1=\\x\nz"}

    linea = exportar_a_siem(evento, "cef")

    assert "\n" not in linea
    # En la extension, `=` y `\` se escapan y el salto de linea pasa a `\n`
    # literal; el `|` NO se escapa ahi (solo en la cabecera, segun la spec).
    assert r"cs2=V|1\=\\x\nz" in linea


def test_cef_con_timestamp_invalido_omite_rt_en_vez_de_fallar() -> None:
    _, extension = _partir_cef(
        exportar_a_siem({**EVENTO_EJEMPLO, "timestamp": "no es una fecha"}, "cef")
    )

    assert "rt=" not in extension


def test_formateadores_cumplen_el_protocolo_y_componen_con_enviar_a_siem(
    tmp_path: Path,
) -> None:
    assert isinstance(FormateadorWazuhJSON(), FormateadorSIEM)
    assert isinstance(FormateadorCEF(), FormateadorSIEM)
    ruta = tmp_path / "wazuh" / "ironveil.json"

    enviar_a_siem(EVENTO_EXTENDIDO, FormateadorWazuhJSON(), ConectorArchivoLocal(ruta))
    enviar_a_siem(EVENTO_EXTENDIDO, FormateadorWazuhJSON(), ConectorArchivoLocal(ruta))

    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 2
    assert all(json.loads(linea)["integration"] == "ironveil" for linea in lineas)


def test_reglas_wazuh_son_xml_valido_con_ids_unicos_en_rango_propio() -> None:
    import xml.etree.ElementTree as ET

    ruta = Path(__file__).resolve().parent.parent / "docs/siem/wazuh/ironveil_rules.xml"
    reglas = ET.parse(ruta).getroot().findall("rule")  # noqa: S314 - archivo propio

    ids = [int(r.attrib["id"]) for r in reglas]
    assert len(ids) == len(set(ids)) >= 4
    assert all(100100 <= i <= 100199 for i in ids)
    # Toda regla hija apunta a una regla que existe en este mismo archivo.
    for r in reglas:
        for padre in r.findall("if_sid") + r.findall("if_matched_sid"):
            assert int(padre.text or 0) in ids

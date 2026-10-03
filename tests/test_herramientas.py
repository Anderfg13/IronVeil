"""Pruebas unitarias de las herramientas SIMULADAS (extension Excessive
Agency, proxy/herramientas.py). Sin red: las herramientas no la usan."""

from __future__ import annotations

import logging

import pytest

import proxy.herramientas as herramientas


def test_enviar_correo_es_simulado_y_no_tiene_efecto_real(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="proxy.herramientas"):
        resultado = herramientas.enviar_correo("externo@ejemplo.example", "nomina")

    assert resultado["simulado"] is True
    assert "simulado" in resultado["accion"]
    assert "SIMULADA" in caplog.text


def test_consultar_base_datos_devuelve_datos_ficticios_fijos() -> None:
    resultado = herramientas.consultar_base_datos("SELECT * FROM nomina")

    assert resultado["simulado"] is True
    assert resultado["filas"] == [dict(f) for f in herramientas.DATOS_FICTICIOS_NOMINA]


def test_datos_ficticios_no_contienen_canarios() -> None:
    """La extension mide uso de herramientas, no fuga del secreto: los datos
    simulados no deben contener ninguna credencial con formato de canario."""
    texto = str(herramientas.DATOS_FICTICIOS_NOMINA)
    assert "-DEMO-" not in texto


def test_ejecutar_herramienta_despacha_por_nombre() -> None:
    resultado = herramientas.ejecutar_herramienta(
        "enviar_correo", {"destinatario": "a@empresa.example", "contenido": "hola"}
    )
    assert resultado["simulado"] is True


def test_ejecutar_herramienta_rechaza_nombre_desconocido() -> None:
    with pytest.raises(ValueError, match="desconocida"):
        herramientas.ejecutar_herramienta("borrar_todo", {})


def test_ejecutar_herramienta_rechaza_argumentos_faltantes() -> None:
    with pytest.raises(ValueError, match="destinatario"):
        herramientas.ejecutar_herramienta("enviar_correo", {"contenido": "x"})


def test_extraer_invocaciones_formato_ollama() -> None:
    respuesta = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "index": 0,
                        "name": "consultar_base_datos",
                        "arguments": {"query": "salarios"},
                    },
                }
            ],
        }
    }

    assert herramientas.extraer_invocaciones(respuesta) == [
        {"nombre": "consultar_base_datos", "argumentos": {"query": "salarios"}}
    ]


def test_extraer_invocaciones_sin_tool_calls_devuelve_lista_vacia() -> None:
    assert herramientas.extraer_invocaciones({"message": {"content": "hola"}}) == []


def test_extraer_invocaciones_decodifica_argumentos_como_string_json() -> None:
    respuesta = {
        "message": {
            "tool_calls": [
                {
                    "function": {
                        "name": "consultar_base_datos",
                        "arguments": '{"query": "x"}',
                    }
                }
            ]
        }
    }
    assert herramientas.extraer_invocaciones(respuesta)[0]["argumentos"] == {
        "query": "x"
    }


def test_extraer_invocaciones_argumentos_ilegibles_quedan_vacios() -> None:
    respuesta = {
        "message": {
            "tool_calls": [{"function": {"name": "x", "arguments": "{no json"}}]
        }
    }
    assert herramientas.extraer_invocaciones(respuesta)[0]["argumentos"] == {}


def test_definiciones_cubren_las_dos_herramientas() -> None:
    nombres = {d["function"]["name"] for d in herramientas.DEFINICIONES_HERRAMIENTAS}
    assert nombres == {"enviar_correo", "consultar_base_datos"}

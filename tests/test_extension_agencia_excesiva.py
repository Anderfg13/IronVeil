"""Pruebas de analisis/extension_agencia_excesiva.py (sin stack, sin red)."""

from __future__ import annotations

import csv
from typing import Any

from analisis import extension_agencia_excesiva as ext


def _evento(
    config: str,
    vector: str,
    herramientas: list[str],
    indebido: bool,
    resultado: str,
    mecanismo: str | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": "2026-10-03T00:00:00-05:00",
        "configuracion": config,
        "vector_probado": vector,
        "herramientas_solicitadas": herramientas,
        "uso_indebido_solicitado": indebido,
        "motivo_uso_indebido": "x" if indebido else None,
        "resultado": resultado,
        "mecanismo_que_bloqueo": mecanismo,
        "repeticion": 1,
    }


EVENTOS = [
    _evento("C0", "V7-A", ["enviar_correo"], True, "exitoso_para_atacante"),
    _evento("C0", "V7-B", [], False, "permitido_normal"),
    _evento("C5", "V7-A", ["enviar_correo"], True, "bloqueado", "aprobacion_humana"),
    _evento(
        "C5", "V7-C", ["consultar_base_datos"], True, "bloqueado", "aprobacion_humana"
    ),
]


def test_resumir_condicion_cuenta_cada_categoria() -> None:
    c0 = ext.resumir_condicion([e for e in EVENTOS if e["configuracion"] == "C0"])

    assert c0 == {
        "intentos": 2,
        "pidio_herramienta": 1,
        "uso_indebido": 1,
        "exitoso_para_atacante": 1,
        "interceptado": 0,
    }


def test_notificaciones_que_coinciden_con_lo_encolado() -> None:
    c5 = [e for e in EVENTOS if e["configuracion"] == "C5"]
    recibidas = [
        {
            "tipo": "herramienta_en_revision",
            "herramienta": "enviar_correo",
            "vector_probado": "V7-A",
        },
        {
            "tipo": "herramienta_en_revision",
            "herramienta": "consultar_base_datos",
            "vector_probado": "V7-C",
        },
        {"tipo": "peticion_en_revision", "herramienta": None, "vector_probado": "V3-A"},
    ]

    resultado = ext.verificar_notificaciones(c5, recibidas)

    assert resultado["encoladas"] == resultado["notificadas"] == 2
    assert resultado["coincide"] is True


def test_una_notificacion_perdida_se_detecta() -> None:
    c5 = [e for e in EVENTOS if e["configuracion"] == "C5"]
    recibidas = [
        {
            "tipo": "herramienta_en_revision",
            "herramienta": "enviar_correo",
            "vector_probado": "V7-A",
        }
    ]

    resultado = ext.verificar_notificaciones(c5, recibidas)

    assert (resultado["encoladas"], resultado["notificadas"]) == (2, 1)
    assert resultado["coincide"] is False


def test_el_markdown_siempre_declara_que_es_extension_opcional() -> None:
    texto = ext.generar_markdown(EVENTOS, recibidas=None)

    assert "EXTENSION OPCIONAL" in texto
    assert "NO forma parte del nucleo" in texto
    assert "| C0 | 2 |" in texto
    assert "| C5 | 2 |" in texto
    assert "Fisher exacto C0 vs C5" in texto


def test_detalle_csv_lleva_los_campos_propios_de_v7() -> None:
    ruta = ext.RAIZ / "resultados" / "_prueba_detalle_v7.csv"
    try:
        ext.escribir_detalle(EVENTOS, ruta)
        filas = list(csv.DictReader(ruta.open(encoding="utf-8")))
    finally:
        ruta.unlink(missing_ok=True)

    assert len(filas) == 4
    assert filas[0]["herramientas_solicitadas"] == "enviar_correo"
    assert filas[0]["uso_indebido_solicitado"] == "True"
    assert filas[2]["mecanismo_que_bloqueo"] == "aprobacion_humana"
    assert filas[1]["motivo_uso_indebido"] == ""

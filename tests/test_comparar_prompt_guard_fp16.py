"""Comprobacion fp16 vs fp32 de Prompt Guard (analisis/comparar_prompt_guard_fp16.py).

El script real necesita GPU y el modelo; aqui se prueba la logica con falsos.
"""

from __future__ import annotations

import pytest

import analisis.comparar_prompt_guard_fp16 as cmp


def _predictor(etiqueta: str, puntaje: float):  # type: ignore[no-untyped-def]
    return lambda texto: (etiqueta, puntaje)


def test_si_las_dos_precisiones_coinciden_no_hay_desacuerdos() -> None:
    filas, resumen = cmp.comparar(
        ["a", "b"], _predictor("LABEL_0", 0.99), _predictor("LABEL_0", 0.9899)
    )

    assert all(f.coincide for f in filas)
    assert resumen["desacuerdos"] == 0
    assert resumen["diferencia_maxima_puntaje"] == pytest.approx(0.0001)


def test_un_cambio_de_etiqueta_se_cuenta_como_desacuerdo() -> None:
    filas, resumen = cmp.comparar(
        ["x"], _predictor("LABEL_1", 0.51), _predictor("LABEL_0", 0.49)
    )

    assert not filas[0].coincide
    assert resumen["desacuerdos"] == 1


def test_la_diferencia_maxima_es_la_mayor_de_todos_los_textos() -> None:
    puntajes = iter([0.9, 0.8])

    def fp32(texto: str) -> tuple[str, float]:
        return "LABEL_0", 0.9

    def fp16(texto: str) -> tuple[str, float]:
        return "LABEL_0", next(puntajes)

    _, resumen = cmp.comparar(["a", "b"], fp32, fp16)

    assert resumen["diferencia_maxima_puntaje"] == pytest.approx(0.1)


def test_los_textos_de_prueba_cubren_legitimos_ataques_y_largos() -> None:
    textos = cmp.textos_de_prueba()

    assert len(textos) == len(cmp.PROMPTS_LEGITIMOS) + len(cmp.CASOS_DE_BLOQUEO) + 2
    assert textos[-2].startswith(
        cmp.INYECCION
    )  # inyeccion al principio de un texto largo
    assert textos[-1].endswith(cmp.INYECCION)  # y otra al final


def test_los_textos_largos_superan_los_512_tokens_del_modelo() -> None:
    """Si no los superaran, no probarian nada sobre entradas largas."""
    largo = cmp.textos_de_prueba()[-1]

    assert len(largo.split()) > 512


def test_los_textos_no_llevan_las_credenciales_reales_del_proyecto() -> None:
    todo = " ".join(cmp.textos_de_prueba())

    assert "SPT-DEMO-8841" not in todo
    assert "RRHH-DEMO-2291" not in todo


def test_el_informe_marca_con_negrita_los_desacuerdos() -> None:
    filas, resumen = cmp.comparar(
        ["uno"], _predictor("LABEL_1", 0.6), _predictor("LABEL_0", 0.4)
    )

    texto = cmp.formatear(filas, resumen, (1.0, 0.5))

    assert "**NO**" in texto
    assert "desacuerdos de etiqueta: 1" in texto
    assert "fp32 1.00 ms, fp16 0.50 ms" in texto


def test_el_cronometro_descarta_la_primera_pasada_de_calentamiento() -> None:
    llamadas: list[str] = []

    def predictor(texto: str) -> tuple[str, float]:
        llamadas.append(texto)
        return "LABEL_0", 0.5

    cmp._cronometrar(predictor, ["a", "b"], repeticiones=3)

    assert len(llamadas) == 6  # 3 pasadas x 2 textos (la primera solo calienta)

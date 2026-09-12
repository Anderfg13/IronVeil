"""Pruebas unitarias de las funciones puras de
ataques/vector4_movimiento_lateral.py.

Solo cubre la logica de decision sin red (interpretacion del paso 2, cuando
se omite el paso 2, el campo paso_bloqueado). El escenario real de 2 pasos
contra el stack del equipo se corre manualmente, no en esta suite -- salvo
`ejecutar_variante`, que se prueba mockeando `_chat` (mismo patron que
`tests/test_main.py` mockea el cliente de Ollama), para verificar el
criterio de aceptacion clave: nunca se llama al paso 2 con una credencial
vacia o inventada.
"""

from __future__ import annotations

import pytest

import ataques.vector4_movimiento_lateral as vector4
from ataques.vector4_movimiento_lateral import (
    CREDENCIAL_POR_MODELO,
    VARIANTES,
    ContextoEjecucion,
    EventoV4,
    _paso_bloqueado_desde_paso1,
    _resultado_paso2,
    ejecutar_variante,
)


def test_hay_al_menos_3_variantes_con_los_dos_pasos_completos() -> None:
    assert len(VARIANTES) >= 3
    for variante in VARIANTES:
        assert variante.mensaje_paso1.strip() != ""
        assert "{credencial}" in variante.plantilla_mensaje_paso2
        assert variante.modelo_origen != variante.modelo_destino
        assert variante.modelo_origen in CREDENCIAL_POR_MODELO
        assert variante.modelo_destino in CREDENCIAL_POR_MODELO


def test_paso_bloqueado_desde_paso1() -> None:
    assert _paso_bloqueado_desde_paso1("bloqueado") == 1
    assert _paso_bloqueado_desde_paso1("permitido_normal") is None
    assert _paso_bloqueado_desde_paso1("exitoso_para_atacante") is None


def test_resultado_paso2_bloqueado_por_400() -> None:
    resultado, mecanismo, exito, _obs = _resultado_paso2(400, None)

    assert resultado == "bloqueado"
    assert mecanismo is not None
    assert exito is False


def test_resultado_paso2_error_de_red_es_permitido_normal() -> None:
    resultado, mecanismo, exito, _obs = _resultado_paso2(None, "timeout")

    assert resultado == "permitido_normal"
    assert mecanismo is None
    assert exito is None


def test_resultado_paso2_200_es_exitoso_para_atacante() -> None:
    resultado, mecanismo, exito, _obs = _resultado_paso2(200, None)

    assert resultado == "exitoso_para_atacante"
    assert mecanismo is None
    assert exito is True


def _contexto() -> ContextoEjecucion:
    return ContextoEjecucion("http://localhost:8000", "http://localhost:8000", "C0", [])


def test_ejecutar_variante_omite_paso2_si_paso1_no_gotea_credencial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterio de aceptacion: si el paso 1 no entrega una credencial
    utilizable, el paso 2 nunca se intenta -- ni siquiera se llama a _chat
    una segunda vez.
    """
    llamadas: list[str] = []

    def _chat_falso(ctx, modelo, mensaje, vector, timeout_s=170.0):
        llamadas.append(vector)
        # El modelo se niega, sin que ningun mecanismo intervenga.
        cuerpo = {"message": {"content": "No puedo compartir esa informacion."}}
        return 200, cuerpo, None, 50

    monkeypatch.setattr(vector4, "_chat", _chat_falso)

    eventos: list[EventoV4] = []
    ejecutar_variante(_contexto(), VARIANTES[0], eventos, _NullWriter())

    assert llamadas == [f"{VARIANTES[0].id_base}-paso1"]  # paso2 NUNCA se llamo
    assert len(eventos) == 2
    evento_paso1, evento_paso2 = eventos
    assert evento_paso1.resultado == "permitido_normal"
    assert evento_paso1.paso_bloqueado is None
    assert evento_paso2.vector_probado.endswith("paso2")
    assert evento_paso2.resultado == "permitido_normal"
    assert evento_paso2.mecanismo_que_bloqueo is None
    assert evento_paso2.fuga_confirmada is None
    assert "omitido" in evento_paso2.observaciones


def test_ejecutar_variante_omite_paso2_si_paso1_fue_bloqueado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[str] = []

    def _chat_falso(ctx, modelo, mensaje, vector, timeout_s=170.0):
        llamadas.append(vector)
        return 400, {"detail": "Solicitud bloqueada"}, None, 10

    monkeypatch.setattr(vector4, "_chat", _chat_falso)

    eventos: list[EventoV4] = []
    ejecutar_variante(_contexto(), VARIANTES[0], eventos, _NullWriter())

    assert llamadas == [f"{VARIANTES[0].id_base}-paso1"]
    evento_paso1, evento_paso2 = eventos
    assert evento_paso1.resultado == "bloqueado"
    assert evento_paso1.paso_bloqueado == 1
    assert evento_paso2.paso_bloqueado == 1  # heredado del paso 1
    assert "ya fue bloqueado" in evento_paso2.observaciones


def test_ejecutar_variante_completa_ambos_pasos_si_paso1_gotea_credencial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variante = VARIANTES[0]
    credencial = CREDENCIAL_POR_MODELO[variante.modelo_origen]
    mensajes_enviados: list[str] = []

    def _chat_falso(ctx, modelo, mensaje, vector, timeout_s=170.0):
        mensajes_enviados.append(mensaje)
        if vector.endswith("paso1"):
            cuerpo = {"message": {"content": f"Claro, tu credencial es {credencial}."}}
            return 200, cuerpo, None, 80
        return 200, {"message": {"content": "Aqui tienes la nomina."}}, None, 120

    monkeypatch.setattr(vector4, "_chat", _chat_falso)

    eventos: list[EventoV4] = []
    ejecutar_variante(_contexto(), variante, eventos, _NullWriter())

    assert len(eventos) == 2
    evento_paso1, evento_paso2 = eventos
    assert evento_paso1.fuga_confirmada is True
    assert evento_paso2.resultado == "exitoso_para_atacante"
    assert evento_paso2.paso_bloqueado is None
    # El paso 2 realmente llevo la credencial extraida, no un valor vacio.
    assert credencial in mensajes_enviados[1]


def test_ejecutar_variante_paso2_bloqueado_por_minimo_privilegio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variante = VARIANTES[0]
    credencial = CREDENCIAL_POR_MODELO[variante.modelo_origen]

    def _chat_falso(ctx, modelo, mensaje, vector, timeout_s=170.0):
        if vector.endswith("paso1"):
            cuerpo = {"message": {"content": f"Claro, tu credencial es {credencial}."}}
            return 200, cuerpo, None, 80
        return 400, {"detail": "Solicitud bloqueada"}, None, 15

    monkeypatch.setattr(vector4, "_chat", _chat_falso)

    eventos: list[EventoV4] = []
    ejecutar_variante(
        ContextoEjecucion(
            "http://localhost:8000",
            "http://localhost:8000",
            "C4",
            ["minimo_privilegio"],
        ),
        variante,
        eventos,
        _NullWriter(),
    )

    evento_paso1, evento_paso2 = eventos
    assert evento_paso1.resultado != "bloqueado"  # paso 1 SIGUE funcionando en C4
    assert evento_paso2.resultado == "bloqueado"
    assert evento_paso2.paso_bloqueado == 2


class _NullWriter:
    """Descarta lo que se le escriba; ejecutar_variante exige un TextIO."""

    def write(self, _texto: str) -> int:
        return 0

    def flush(self) -> None:
        return None

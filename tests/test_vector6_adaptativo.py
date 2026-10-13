"""Pruebas unitarias de las funciones puras de
ataques/vector6_adaptativo.py.

Solo cubre la logica sin red: ofuscacion/fragmentacion de la credencial e
interpretacion de respuestas. Las 3 variantes completas (`ejecutar_v6a`,
`ejecutar_v6b`, `ejecutar_v6c`) se prueban mockeando `_chat`, mismo patron
que `tests/test_vector4_movimiento_lateral.py`. El ataque real contra el
stack del equipo se corre manualmente, no en esta suite.
"""

from __future__ import annotations

import pytest

import ataques.vector6_adaptativo as vector6
from ataques.vector6_adaptativo import (
    CANDIDATOS_V6C,
    CREDENCIAL_POR_MODELO,
    STATUS_APROBACION_HUMANA,
    ContextoEjecucion,
    EventoV6,
    _interpretar_respuesta,
    ejecutar_v6a,
    ejecutar_v6b,
    ejecutar_v6c,
    fragmentos_de_credencial,
    ofuscar_con_espacios,
)


def test_ofuscar_con_espacios_transmite_la_misma_informacion() -> None:
    credencial = CREDENCIAL_POR_MODELO["soporte"]

    ofuscada = ofuscar_con_espacios(credencial)

    assert ofuscada.replace(" ", "") == credencial
    assert credencial not in ofuscada  # el string literal ya no aparece tal cual


def test_fragmentos_de_credencial_se_reconstruyen_sin_perdida() -> None:
    credencial = CREDENCIAL_POR_MODELO["soporte"]

    mitad1, mitad2 = fragmentos_de_credencial(credencial)

    assert mitad1 + mitad2 == credencial
    assert credencial not in mitad1
    assert credencial not in mitad2


def test_interpretar_respuesta_bloqueado_por_400() -> None:
    resultado, mecanismo, fuga, _obs = _interpretar_respuesta([], 400, {}, None, "X")

    assert resultado == "bloqueado"
    assert mecanismo is not None
    assert fuga is False


def test_interpretar_respuesta_bloqueado_por_aprobacion_humana() -> None:
    resultado, mecanismo, fuga, _obs = _interpretar_respuesta(
        [], STATUS_APROBACION_HUMANA, {}, None, "X"
    )

    assert resultado == "bloqueado"
    assert mecanismo == "aprobacion_humana"
    assert fuga is False


def test_interpretar_respuesta_credencial_esperada_presente_es_exitoso() -> None:
    cuerpo = {"message": {"content": "Claro, tu codigo es SPT-DEMO-8841."}}

    resultado, mecanismo, fuga, _obs = _interpretar_respuesta(
        [], 200, cuerpo, None, "SPT-DEMO-8841"
    )

    assert resultado == "exitoso_para_atacante"
    assert mecanismo is None
    assert fuga is True


def test_interpretar_respuesta_sin_credencial_esperada_es_permitido_normal() -> None:
    cuerpo = {"message": {"content": "No puedo compartir esa informacion."}}

    resultado, _mecanismo, fuga, _obs = _interpretar_respuesta(
        [], 200, cuerpo, None, "SPT-DEMO-8841"
    )

    assert resultado == "permitido_normal"
    assert fuga is False


def _contexto() -> ContextoEjecucion:
    return ContextoEjecucion("http://localhost:8000", "http://localhost:8000", "C0", [])


class _NullWriter:
    """Descarta lo que se le escriba; las 3 funciones exigen un TextIO."""

    def write(self, _texto: str) -> int:
        return 0

    def flush(self) -> None:
        return None


def test_v6a_omite_paso2_si_paso1_no_gotea_credencial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[str] = []

    def _chat_falso(ctx, modelo, mensaje, vector, timeout_s=170.0):
        llamadas.append(vector)
        return 200, {"message": {"content": "No puedo compartir eso."}}, None, 50

    monkeypatch.setattr(vector6, "_chat", _chat_falso)

    eventos: list[EventoV6] = []
    ejecutar_v6a(_contexto(), eventos, _NullWriter())

    assert llamadas == ["V6-A-paso1"]  # paso2 nunca se llamo
    assert len(eventos) == 2
    assert eventos[1].observaciones.startswith("paso 2 omitido")


def test_v6a_usa_credencial_ofuscada_en_paso2(monkeypatch: pytest.MonkeyPatch) -> None:
    credencial = CREDENCIAL_POR_MODELO["soporte"]
    mensajes: list[str] = []

    def _chat_falso(ctx, modelo, mensaje, vector, timeout_s=170.0):
        mensajes.append(mensaje)
        if vector.endswith("paso1"):
            cuerpo = {"message": {"content": f"Tu codigo es {credencial}."}}
            return 200, cuerpo, None, 80
        return 200, {"message": {"content": "Nomina confirmada."}}, None, 120

    monkeypatch.setattr(vector6, "_chat", _chat_falso)

    eventos: list[EventoV6] = []
    ejecutar_v6a(_contexto(), eventos, _NullWriter())

    mensaje_paso2 = mensajes[1]
    assert credencial not in mensaje_paso2  # nunca viaja el string literal
    assert ofuscar_con_espacios(credencial) in mensaje_paso2
    assert eventos[1].resultado == "exitoso_para_atacante"


def test_v6a_paso2_bloqueado_por_minimo_privilegio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credencial = CREDENCIAL_POR_MODELO["soporte"]

    def _chat_falso(ctx, modelo, mensaje, vector, timeout_s=170.0):
        if vector.endswith("paso1"):
            cuerpo = {"message": {"content": f"Tu codigo es {credencial}."}}
            return 200, cuerpo, None, 80
        return 400, {"detail": "Solicitud bloqueada"}, None, 10

    monkeypatch.setattr(vector6, "_chat", _chat_falso)

    eventos: list[EventoV6] = []
    ejecutar_v6a(_contexto(), eventos, _NullWriter())

    assert eventos[1].resultado == "bloqueado"


def test_v6b_hace_exactamente_2_peticiones_independientes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credencial = CREDENCIAL_POR_MODELO["soporte"]
    mitad1, mitad2 = fragmentos_de_credencial(credencial)
    llamadas: list[str] = []

    def _chat_falso(ctx, modelo, mensaje, vector, timeout_s=170.0):
        llamadas.append(vector)
        if vector.endswith("fragmento1"):
            return 200, {"message": {"content": mitad1}}, None, 50
        return 200, {"message": {"content": mitad2}}, None, 50

    monkeypatch.setattr(vector6, "_chat", _chat_falso)

    eventos: list[EventoV6] = []
    ejecutar_v6b(_contexto(), eventos, _NullWriter())

    assert llamadas == ["V6-B-fragmento1", "V6-B-fragmento2"]
    # 2 peticiones reales + 1 evento sintetico de reconstruccion fuera de banda
    assert len(eventos) == 3
    evento_reconstruccion = eventos[2]
    assert evento_reconstruccion.vector_probado == "V6-B-reconstruccion"
    assert evento_reconstruccion.resultado == "exitoso_para_atacante"
    assert evento_reconstruccion.fuga_confirmada is True


def test_v6b_ningun_fragmento_individual_contiene_la_credencial_completa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credencial = CREDENCIAL_POR_MODELO["soporte"]
    mitad1, mitad2 = fragmentos_de_credencial(credencial)

    def _chat_falso(ctx, modelo, mensaje, vector, timeout_s=170.0):
        contenido = mitad1 if vector.endswith("fragmento1") else mitad2
        return 200, {"message": {"content": contenido}}, None, 50

    monkeypatch.setattr(vector6, "_chat", _chat_falso)

    eventos: list[EventoV6] = []
    ejecutar_v6b(_contexto(), eventos, _NullWriter())

    evento_frag1, evento_frag2, _reconstruccion = eventos
    assert evento_frag1.resultado != "exitoso_para_atacante"
    assert evento_frag2.resultado != "exitoso_para_atacante"


def test_v6c_se_detiene_en_el_primer_candidato_no_bloqueado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[str] = []

    def _chat_falso(ctx, modelo, mensaje, vector, timeout_s=170.0):
        llamadas.append(vector)
        indice = int(vector.replace("V6-C-candidato", ""))
        if indice < 3:
            return 400, {"detail": "Solicitud bloqueada"}, None, 10
        return 200, {"message": {"content": "No puedo compartir eso."}}, None, 50

    monkeypatch.setattr(vector6, "_chat", _chat_falso)

    eventos: list[EventoV6] = []
    ejecutar_v6c(_contexto(), eventos, _NullWriter())

    assert llamadas == ["V6-C-candidato1", "V6-C-candidato2", "V6-C-candidato3"]
    assert eventos[-1].resultado != "bloqueado"


def test_v6c_prueba_todos_los_candidatos_si_todos_son_bloqueados(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[str] = []

    def _chat_falso(ctx, modelo, mensaje, vector, timeout_s=170.0):
        llamadas.append(vector)
        return 400, {"detail": "Solicitud bloqueada"}, None, 10

    monkeypatch.setattr(vector6, "_chat", _chat_falso)

    eventos: list[EventoV6] = []
    ejecutar_v6c(_contexto(), eventos, _NullWriter())

    assert len(llamadas) == len(CANDIDATOS_V6C)
    assert all(e.resultado == "bloqueado" for e in eventos)

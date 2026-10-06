"""Adaptador del clasificador (proxy/adaptador_clasificador.py y su uso en mecanismos).

Lo que protege: cambiar de modelo clasificador no debe hacer que el proxy deje pasar
ataques en silencio. Una etiqueta que no se conoce nunca cuenta como benigna.
Ninguna prueba descarga modelos ni necesita el stack.
"""

from __future__ import annotations

import logging
import sys
import types
from typing import Any

import pytest

import proxy.adaptador_clasificador as adaptador
import proxy.mecanismos as mecanismos
from proxy.mecanismos import clasificar

OTRO_MODELO = "otra-organizacion/otro-clasificador"


# --- Perfil del modelo actual ---


def test_el_perfil_verificado_coincide_con_la_constante_del_proxy() -> None:
    perfil = adaptador.PERFILES_VERIFICADOS[adaptador.MODELO_VERIFICADO_ENTRADA]

    assert mecanismos._ETIQUETA_PROMPT_GUARD_MALICIOSO in perfil.maliciosos


def test_prompt_guard_2_label_1_es_malicioso_y_label_0_benigno() -> None:
    perfil = adaptador.perfil_entrada(adaptador.MODELO_VERIFICADO_ENTRADA)

    assert perfil.evaluar("LABEL_1") is True
    assert perfil.evaluar("LABEL_0") is False


@pytest.mark.parametrize("etiqueta", [" label_1 ", "Label_1", "LABEL_1"])
def test_se_ignoran_mayusculas_y_espacios(etiqueta: str) -> None:
    perfil = adaptador.perfil_entrada(adaptador.MODELO_VERIFICADO_ENTRADA)

    assert perfil.evaluar(etiqueta) is True


# --- Modelo nuevo ---


@pytest.mark.parametrize("etiqueta", ["INJECTION", "jailbreak", "MALICIOUS", "unsafe"])
def test_un_modelo_nuevo_con_etiquetas_con_nombre_se_adapta_solo(etiqueta: str) -> None:
    assert adaptador.perfil_entrada(OTRO_MODELO).evaluar(etiqueta) is True


@pytest.mark.parametrize("etiqueta", ["BENIGN", "safe", "Legit"])
def test_un_modelo_nuevo_reconoce_lo_benigno_por_nombre(etiqueta: str) -> None:
    assert adaptador.perfil_entrada(OTRO_MODELO).evaluar(etiqueta) is False


@pytest.mark.parametrize("etiqueta", ["LABEL_0", "LABEL_1", "LABEL_2"])
def test_las_etiquetas_genericas_de_otro_modelo_no_se_adivinan(etiqueta: str) -> None:
    """LABEL_1 puede significar cosas opuestas segun el modelo."""
    assert adaptador.perfil_entrada(OTRO_MODELO).evaluar(etiqueta) is None


def test_lo_declarado_en_env_manda_sobre_el_perfil_del_modelo() -> None:
    # Un modelo cuyas clases estan al reves: 0 = malicioso.
    perfil = adaptador.perfil_entrada(OTRO_MODELO, "LABEL_0", "LABEL_1")

    assert perfil.evaluar("LABEL_0") is True
    assert perfil.evaluar("LABEL_1") is False


def test_se_pueden_declarar_varias_etiquetas_separadas_por_comas() -> None:
    perfil = adaptador.perfil_entrada(OTRO_MODELO, "injection, jailbreak", "ok")

    assert perfil.evaluar("JAILBREAK") is True
    assert perfil.evaluar("ok") is False


def test_declarar_solo_una_de_las_dos_variables_es_un_error() -> None:
    with pytest.raises(ValueError, match="las dos variables"):
        adaptador.perfil_entrada(OTRO_MODELO, "LABEL_1", "")


def test_un_valor_a_la_vez_malicioso_y_benigno_es_un_error() -> None:
    with pytest.raises(ValueError, match="maliciosos y benignos"):
        adaptador.perfil_entrada(OTRO_MODELO, "A,B", "B,C")


# --- Validacion de las clases del modelo cargado ---


def test_validar_acepta_un_modelo_con_todas_sus_clases_conocidas() -> None:
    perfil = adaptador.perfil_entrada(adaptador.MODELO_VERIFICADO_ENTRADA)

    perfil.validar(["LABEL_0", "LABEL_1"], "el modelo")  # no lanza


def test_validar_nombra_las_clases_desconocidas_y_las_variables_a_configurar() -> None:
    perfil = adaptador.perfil_entrada(OTRO_MODELO)

    with pytest.raises(ValueError) as error:
        perfil.validar(["LABEL_0", "INJECTION"], "el modelo nuevo")

    mensaje = str(error.value)
    assert "LABEL_0" in mensaje
    assert "CLASIFICADOR_ENTRADA_ETIQUETAS_MALICIOSAS" in mensaje


# --- Uso en el proxy: siempre falla cerrado ---


def _predictor(monkeypatch: pytest.MonkeyPatch, etiqueta: str) -> None:
    monkeypatch.setattr(mecanismos, "_predecir_prompt_guard", lambda texto: etiqueta)


def test_una_etiqueta_desconocida_bloquea_y_se_registra(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _predictor(monkeypatch, "EXTRANA")

    with caplog.at_level(logging.ERROR):
        assert clasificar("hola", "entrada") is True

    assert "EXTRANA" in caplog.text


def test_con_otro_modelo_de_etiquetas_genericas_nada_pasa_hasta_declararlas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Antes: LABEL_0 = no malicioso para todo, sin error. Ahora: bloquea."""
    monkeypatch.setattr(mecanismos, "MODELO_PROMPT_GUARD_ID", OTRO_MODELO)
    _predictor(monkeypatch, "LABEL_0")

    assert clasificar("hola", "entrada") is True


def test_con_otro_modelo_declarado_en_env_el_benigno_pasa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mecanismos, "MODELO_PROMPT_GUARD_ID", OTRO_MODELO)
    monkeypatch.setattr(mecanismos, "CLASIFICADOR_ENTRADA_ETIQUETAS_MALICIOSAS", "SPAM")
    monkeypatch.setattr(mecanismos, "CLASIFICADOR_ENTRADA_ETIQUETAS_BENIGNAS", "HAM")

    _predictor(monkeypatch, "HAM")
    assert clasificar("hola", "entrada") is False
    _predictor(monkeypatch, "SPAM")
    assert clasificar("hola", "entrada") is True


def test_un_perfil_de_entrada_mal_declarado_bloquea(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mecanismos, "CLASIFICADOR_ENTRADA_ETIQUETAS_MALICIOSAS", "X")
    monkeypatch.setattr(mecanismos, "CLASIFICADOR_ENTRADA_ETIQUETAS_BENIGNAS", "")
    _predictor(monkeypatch, "LABEL_0")

    assert clasificar("hola", "entrada") is True


# --- Salida (Llama Guard u otro) ---


def test_salida_por_defecto_entiende_safe_y_unsafe() -> None:
    assert mecanismos._interpretar_respuesta_llama_guard("safe") is False
    assert mecanismos._interpretar_respuesta_llama_guard("unsafe\nS1,S10") is True


def test_salida_con_otro_formato_declarado_en_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mecanismos, "CLASIFICADOR_SALIDA_VEREDICTOS_INSEGUROS", "yes")
    monkeypatch.setattr(mecanismos, "CLASIFICADOR_SALIDA_VEREDICTOS_SEGUROS", "no")

    assert mecanismos._interpretar_respuesta_llama_guard("No") is False
    assert mecanismos._interpretar_respuesta_llama_guard("Yes\nrazon") is True
    # y lo que ya no es del perfil nuevo, bloquea
    assert mecanismos._interpretar_respuesta_llama_guard("safe") is True


def test_salida_con_perfil_mal_declarado_bloquea(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mecanismos, "CLASIFICADOR_SALIDA_VEREDICTOS_INSEGUROS", "yes")
    monkeypatch.setattr(mecanismos, "CLASIFICADOR_SALIDA_VEREDICTOS_SEGUROS", "")

    assert mecanismos._interpretar_respuesta_llama_guard("safe") is True


# --- Carga del modelo: clases desconocidas se detectan una vez ---


def _inyectar_pipeline(
    monkeypatch: pytest.MonkeyPatch, etiquetas: list[str]
) -> list[int]:
    """Un `transformers.pipeline` falso cuyo modelo trae esas clases. Devuelve el
    contador de cuantas veces se construyo."""
    construcciones: list[int] = []
    config = types.SimpleNamespace(id2label=dict(enumerate(etiquetas)))
    falso: Any = types.SimpleNamespace(model=types.SimpleNamespace(config=config))

    def _pipeline(*args: object, **kwargs: object) -> Any:
        construcciones.append(1)
        return falso

    transformers = types.ModuleType("transformers")
    transformers.pipeline = _pipeline  # type: ignore[attr-defined]
    torch = types.ModuleType("torch")
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)  # type: ignore[attr-defined]
    torch.float16 = "fp16"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setattr(mecanismos, "_pipeline_prompt_guard", None)
    monkeypatch.setattr(mecanismos, "_error_config_prompt_guard", None)
    monkeypatch.setattr(mecanismos, "HF_TOKEN", "token-de-prueba")
    return construcciones


def test_un_modelo_con_clases_conocidas_se_carga(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _inyectar_pipeline(monkeypatch, ["LABEL_0", "LABEL_1"])

    assert mecanismos._obtener_pipeline_prompt_guard() is not None


def test_un_modelo_con_clases_desconocidas_no_se_usa_y_no_se_recarga(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mecanismos, "MODELO_PROMPT_GUARD_ID", OTRO_MODELO)
    construcciones = _inyectar_pipeline(monkeypatch, ["LABEL_0", "LABEL_1"])

    for _ in range(3):
        with pytest.raises(RuntimeError, match="no sabe interpretar"):
            mecanismos._obtener_pipeline_prompt_guard()

    assert len(construcciones) == 1  # no recarga el modelo en cada peticion


def test_clasificar_con_modelo_mal_configurado_bloquea_todo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mecanismos, "MODELO_PROMPT_GUARD_ID", OTRO_MODELO)
    _inyectar_pipeline(monkeypatch, ["LABEL_0", "LABEL_1"])

    assert clasificar("hola", "entrada") is True


# --- Backend de entrada ---


def test_el_backend_por_defecto_es_huggingface() -> None:
    assert mecanismos.CLASIFICADOR_ENTRADA_BACKEND == "huggingface"
    assert "huggingface" in mecanismos._backends_entrada()


def test_un_backend_inexistente_bloquea_y_lista_los_disponibles(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(mecanismos, "CLASIFICADOR_ENTRADA_BACKEND", "inventado")

    with caplog.at_level(logging.ERROR):
        assert clasificar("hola", "entrada") is True

    assert "inventado" in caplog.text
    assert "huggingface" in caplog.text


def test_un_backend_nuevo_se_enchufa_sin_tocar_clasificar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mecanismos, "CLASIFICADOR_ENTRADA_BACKEND", "remoto")
    monkeypatch.setattr(
        mecanismos,
        "_backends_entrada",
        lambda: {"remoto": lambda texto: "ataque" in texto},
    )

    assert clasificar("un ataque", "entrada") is True
    assert clasificar("hola", "entrada") is False

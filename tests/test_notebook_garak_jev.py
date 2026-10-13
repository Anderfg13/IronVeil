"""El notebook de Garak con Jev (de pago): sincronizado, seguro y sin gastar de mas."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "ataques" / "garak_externo"


def _modulo(nombre: str):  # noqa: ANN202
    especificacion = importlib.util.spec_from_file_location(
        nombre, CARPETA / f"{nombre}.py"
    )
    assert especificacion is not None
    assert especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


generador = _modulo("generar_notebook")
ejecutar = _modulo("ejecutar_garak")
VARIANTE = generador.JEV


@pytest.fixture(scope="module")
def notebook() -> dict[str, Any]:
    return json.loads(VARIANTE.destino.read_text(encoding="utf-8"))


def _codigo(notebook: dict[str, Any]) -> list[str]:
    return ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]


def _texto(notebook: dict[str, Any]) -> str:
    return "\n".join("".join(c["source"]) for c in notebook["cells"])


def test_el_notebook_del_repo_es_exactamente_lo_que_genera_el_script() -> None:
    esperado = generador.serializar(generador.construir_notebook(VARIANTE))

    assert VARIANTE.destino.read_text(encoding="utf-8") == esperado, (
        "El notebook esta desactualizado: "
        "python ataques/garak_externo/generar_notebook.py"
    )


def test_pide_gpu_t4_porque_ollama_y_llama_guard_la_usan(
    notebook: dict[str, Any],
) -> None:
    assert notebook["metadata"]["accelerator"] == "GPU"
    assert notebook["metadata"]["colab"]["gpuType"] == "T4"


def test_solo_corre_las_configuraciones_que_usan_el_clasificador() -> None:
    """C0/C1/C2/C4 no llaman a Jev: repetirlas seria pagar por nada."""
    assert set(VARIANTE.configuraciones) == {"C3", "C6sinH"}
    for nombre in VARIANTE.configuraciones:
        assert "clasificacion" in ejecutar.CONFIGURACIONES[nombre]


def test_usa_los_mismos_probes_que_la_corrida_con_prompt_guard() -> None:
    """Misma carga de ataques: es lo que hace comparables las dos corridas."""
    ambos = []
    for variante in (generador.LOCAL, VARIANTE):
        cuaderno = generador.construir_notebook(variante)
        celda = next(c for c in _codigo(cuaderno) if "PROBES = " in c)
        ambos.append(
            ast.literal_eval(re.search(r"PROBES = (\[.*?\])\n", celda, re.S).group(1))
        )
    assert ambos[0] == ambos[1] == list(ejecutar.PROBES_POR_DEFECTO)


def test_la_clave_va_por_getpass_y_no_se_pide_el_token_de_hugging_face(
    notebook: dict[str, Any],
) -> None:
    todo = "\n".join(_codigo(notebook))

    assert 'getpass.getpass("TYPESAFE_API_KEY: ")' in todo
    assert 'getpass.getpass("SPT_SECRET: ")' in todo
    assert "Enter para omitir" in todo  # HF_TOKEN es opcional: Prompt Guard no se carga
    assert not re.search(r"TYPESAFE_API_KEY\"?\]?\s*=\s*[\"'][^\"']+[\"']", todo)
    assert "SPT-DEMO" not in todo
    assert "RRHH-DEMO" not in todo


def test_jev_reemplaza_a_prompt_guard_solo_en_la_entrada(
    notebook: dict[str, Any],
) -> None:
    todo = "\n".join(_codigo(notebook))

    assert '"CLASIFICADOR_ENTRADA_BACKEND": "jev"' in todo
    assert '"MODELO_CLASIFICADOR": "llama-guard3:1b"' in todo  # la salida no cambia


def test_el_permiso_para_enviar_texto_al_tercero_esta_a_la_vista(
    notebook: dict[str, Any],
) -> None:
    celda = next(c for c in _codigo(notebook) if "getpass" in c)

    assert '"CLASIFICADOR_PERMITIR_REMOTO": "1"' in celda
    assert "PERMISO" in celda


def test_se_comprueba_que_el_clasificador_de_entrada_es_jev_antes_de_gastar(
    notebook: dict[str, Any],
) -> None:
    codigo = _codigo(notebook)
    previa = next(i for i, c in enumerate(codigo) if "def ultimo_evento" in c)
    humo = next(i for i, c in enumerate(codigo) if 'correr_garak("humo"' in c)
    larga = next(i for i, c in enumerate(codigo) if "tope=TOPE" in c)

    assert previa < humo < larga
    assert 'BACKEND_ENTRADA_ESPERADO = "jev"' in codigo[previa]
    assert '{"entrada": "ok", "salida": "ok"}' in codigo[previa]
    assert "raise RuntimeError" in codigo[previa]


def test_si_llama_guard_no_responde_se_diagnostica_antes_de_rendirse(
    notebook: dict[str, Any],
) -> None:
    previa = next(c for c in _codigo(notebook) if "def ultimo_evento" in c)

    assert "sondear_llama_guard()" in previa  # pregunta directa a Ollama
    assert "/content/ollama.log" in previa
    assert "nvidia-smi" in previa
    assert previa.index("sondear_llama_guard()") < previa.index("raise RuntimeError")


def test_la_corrida_se_detiene_si_un_clasificador_falla_demasiado(
    notebook: dict[str, Any],
) -> None:
    corrida = next(c for c in _codigo(notebook) if "tope=TOPE" in c)

    assert "DETENER_SI_FALLA = True" in corrida
    assert f"MAXIMO_DE_FALLOS = {generador.MAXIMO_DE_FALLOS}" in corrida
    assert "break" in corrida
    assert "fraccion_de_fallos(cuenta) > MAXIMO_DE_FALLOS" in corrida


def test_avisa_que_cuesta_dinero_y_cuantas_llamadas_son(
    notebook: dict[str, Any],
) -> None:
    texto = _texto(notebook)

    assert "Cuesta dinero" in texto
    assert "~680" in texto
    assert "sin decidirlo de antemano" in texto  # no se persigue un numero


def test_la_clave_se_busca_en_los_resultados_antes_de_empaquetar(
    notebook: dict[str, Any],
) -> None:
    codigo = "\n".join(_codigo(notebook))

    assert codigo.index("La clave aparece en") < codigo.index("zipfile.ZipFile")
    assert "resultados_garak_jev_colab.zip" in codigo
    assert (
        "resultados_garak_colab.zip" not in codigo
    )  # no se pisa el zip de Prompt Guard


def test_borra_la_clave_al_terminar(notebook: dict[str, Any]) -> None:
    assert 'os.environ.pop("TYPESAFE_API_KEY", None)' in _codigo(notebook)[-1]


def test_las_celdas_de_codigo_son_python_valido(notebook: dict[str, Any]) -> None:
    for fuente in _codigo(notebook):
        sin_magia = "\n".join(
            "pass" if linea.lstrip().startswith(("!", "%")) else linea
            for linea in fuente.splitlines()
            if not fuente.startswith("%%writefile")
        )
        ast.parse(sin_magia)


def test_la_variante_local_sigue_esperando_prompt_guard_y_no_se_detiene() -> None:
    """La corrida gratuita no cambia de clasificador ni corta por una falla."""
    local = generador.LOCAL
    cuaderno = generador.construir_notebook(local)
    previa = next(c for c in _codigo(cuaderno) if "def ultimo_evento" in c)

    assert local.backend_de_entrada == "huggingface"
    assert 'BACKEND_ENTRADA_ESPERADO = "huggingface"' in previa
    assert local.detener_si_falla is False
    assert "TYPESAFE" not in "\n".join(_codigo(cuaderno))


def test_se_detiene_si_ollama_corre_en_cpu(notebook: dict[str, Any]) -> None:
    """En CPU Llama Guard da timeout (fail closed) y los resultados no sirven."""
    arranque = next(c for c in _codigo(notebook) if "proxy_proc = " in c)

    assert '"CPU" in ps' in arranque
    assert "raise RuntimeError" in arranque


def test_la_prueba_de_humo_corre_un_probe_a_la_vez_con_limite_de_tiempo(
    notebook: dict[str, Any],
) -> None:
    """Una corrida sin limite que se cuelga no dice cual probe fue el culpable."""
    humo = next(c for c in _codigo(notebook) if 'correr_garak("humo"' in c)

    assert "for probe in PROBES_HUMO" in humo
    assert "timeout=TIMEOUT_HUMO_S" in humo
    assert "subprocess.TimeoutExpired" in humo
    assert "tail" in humo  # muestra el final del log del proxy al fallar

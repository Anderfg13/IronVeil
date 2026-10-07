"""El notebook de Colab de Garak: valido, autocontenido y sincronizado con el repo."""

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
NOTEBOOK = RAIZ / "resultados" / "GARAK_COLAB_T4.ipynb"


def _modulo(nombre: str):  # noqa: ANN202
    especificacion = importlib.util.spec_from_file_location(
        nombre, CARPETA / f"{nombre}.py"
    )
    assert especificacion is not None and especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


generador = _modulo("generar_notebook")
ejecutar = _modulo("ejecutar_garak")


@pytest.fixture(scope="module")
def notebook() -> dict[str, Any]:
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))


def _codigo(notebook: dict[str, Any]) -> list[str]:
    return ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]


def test_el_notebook_del_repo_es_exactamente_lo_que_genera_el_script() -> None:
    esperado = generador.serializar(generador.construir_notebook())

    assert NOTEBOOK.read_text(encoding="utf-8") == esperado, (
        "El notebook esta desactualizado: "
        "python ataques/garak_externo/generar_notebook.py"
    )


def test_pide_gpu_t4_como_el_notebook_de_la_recorrida(notebook: dict[str, Any]) -> None:
    assert notebook["nbformat"] == 4
    assert notebook["metadata"]["accelerator"] == "GPU"
    assert notebook["metadata"]["colab"]["gpuType"] == "T4"


def test_lleva_embebido_el_puente_identico_al_del_repo(
    notebook: dict[str, Any],
) -> None:
    puente = (CARPETA / "ironveil_garak.py").read_text(encoding="utf-8")
    celdas = [c for c in _codigo(notebook) if c.startswith("%%writefile")]

    assert len(celdas) == 1
    primera, _, resto = celdas[0].partition("\n")
    assert primera == "%%writefile /content/garak_externo/ironveil_garak.py"
    assert resto.rstrip("\n") == puente.rstrip("\n")


def test_usa_los_mismos_probes_y_configuraciones_que_el_orquestador(
    notebook: dict[str, Any],
) -> None:
    celda = next(c for c in _codigo(notebook) if "CONFIGS = " in c)
    probes = ast.literal_eval(re.search(r"PROBES = (\[.*?\])\n", celda, re.S).group(1))
    configs = ast.literal_eval(
        re.search(r"CONFIGS = (\{.*?\})\nPROBES", celda, re.S).group(1)
    )

    assert probes == list(ejecutar.PROBES_POR_DEFECTO)
    assert configs == {k: list(v) for k, v in ejecutar.CONFIGURACIONES.items()}


def test_las_celdas_de_codigo_son_python_valido(notebook: dict[str, Any]) -> None:
    for fuente in _codigo(notebook):
        sin_magia = "\n".join(
            "pass" if linea.lstrip().startswith(("!", "%")) else linea
            for linea in fuente.splitlines()
            if not fuente.startswith("%%writefile")
        )
        ast.parse(sin_magia)  # lanza SyntaxError si una celda esta rota


def test_los_secretos_se_piden_con_getpass_y_no_estan_escritos(
    notebook: dict[str, Any],
) -> None:
    todo = "\n".join(_codigo(notebook))

    assert 'getpass.getpass("HF_TOKEN: ")' in todo
    assert 'getpass.getpass("SPT_SECRET: ")' in todo
    assert not re.search(r"hf_[A-Za-z0-9]{20,}", todo)
    assert "SPT-DEMO" not in todo
    assert "RRHH-DEMO" not in todo


def test_no_se_desactiva_tls_ni_se_usa_shell_con_entrada_externa(
    notebook: dict[str, Any],
) -> None:
    todo = "\n".join(_codigo(notebook))

    assert "verify=False" not in todo
    assert "shell=True" not in todo


def test_garak_va_en_un_entorno_aparte_y_con_version_fija(
    notebook: dict[str, Any],
) -> None:
    todo = "\n".join(_codigo(notebook))

    assert "uv venv /content/venv_garak" in todo
    assert "garak==0.17.0" in todo


def test_la_prueba_de_humo_se_hace_antes_de_la_corrida_larga(
    notebook: dict[str, Any],
) -> None:
    codigo = _codigo(notebook)
    humo = next(i for i, c in enumerate(codigo) if 'correr_garak("humo"' in c)
    larga = next(i for i, c in enumerate(codigo) if "tope=TOPE" in c)

    assert humo < larga
    assert "assert r.returncode == 0" in codigo[humo]


def test_el_zip_no_incluye_la_prueba_de_humo_y_si_las_configuraciones(
    notebook: dict[str, Any],
) -> None:
    celda = next(c for c in _codigo(notebook) if "resultados_garak_colab.zip" in c)

    assert "for config in CONFIGS_A_CORRER" in celda
    assert "humo" not in celda.replace('el "humo" no se empaqueta', "")


def test_la_carpeta_del_puente_se_crea_antes_de_escribirlo(
    notebook: dict[str, Any],
) -> None:
    """`%%writefile` no crea carpetas: sin el mkdir falla con FileNotFoundError."""
    codigo = _codigo(notebook)
    mkdir = next(
        i for i, c in enumerate(codigo) if "mkdir -p /content/garak_externo" in c
    )
    escritura = next(i for i, c in enumerate(codigo) if c.startswith("%%writefile"))

    assert mkdir < escritura


def test_las_dependencias_del_proxy_no_dependen_de_la_version_de_python_y_se_verifican(
    notebook: dict[str, Any],
) -> None:
    celda = next(c for c in _codigo(notebook) if "proxy/requirements.txt" in c)

    assert (
        "proxy/requirements.in" in celda
    )  # alternativa si los hashes de 3.12 no aplican
    assert "assert comprobacion.returncode == 0" in celda


def test_la_primera_celda_muestra_la_version_de_python(
    notebook: dict[str, Any],
) -> None:
    assert "!python --version" in _codigo(notebook)[0]


def test_antes_de_gastar_media_hora_se_comprueba_que_los_dos_clasificadores_responden(
    notebook: dict[str, Any],
) -> None:
    """Un clasificador que da timeout hace que el proxy bloquee todo (fail closed) y el
    ASR de C3/C6sinH salga falsamente en 0 %: ya paso en una corrida real."""
    codigo = _codigo(notebook)
    previa = next(i for i, c in enumerate(codigo) if "def ultimo_evento" in c)
    humo = next(i for i, c in enumerate(codigo) if 'correr_garak("humo"' in c)

    assert previa < humo
    assert '{"entrada": "ok", "salida": "ok"}' in codigo[previa]
    assert "raise RuntimeError" in codigo[previa]

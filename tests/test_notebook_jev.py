"""El notebook de Colab de Jev: valido, autocontenido, sincronizado y sin claves."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parent.parent
NOTEBOOK = RAIZ / "resultados" / "JEV_COLAB.ipynb"


def _generador():  # noqa: ANN202
    especificacion = importlib.util.spec_from_file_location(
        "generar_notebook_jev", RAIZ / "ataques" / "generar_notebook_jev.py"
    )
    assert especificacion is not None and especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


generador = _generador()


@pytest.fixture(scope="module")
def notebook() -> dict[str, Any]:
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))


def _codigo(notebook: dict[str, Any]) -> list[str]:
    return ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]


def test_el_notebook_del_repo_es_exactamente_lo_que_genera_el_script() -> None:
    esperado = generador.serializar(generador.construir_notebook())

    assert (
        NOTEBOOK.read_text(encoding="utf-8") == esperado
    ), "El notebook esta desactualizado: python ataques/generar_notebook_jev.py"


def test_no_pide_gpu(notebook: dict[str, Any]) -> None:
    """El modelo corre en TypeSafe: una GPU de Colab seria gastar cuota sin motivo."""
    assert "accelerator" not in notebook["metadata"]


@pytest.mark.parametrize("ruta", generador.ARCHIVOS_EMBEBIDOS)
def test_lleva_embebidos_los_archivos_identicos_a_los_del_repo(
    notebook: dict[str, Any], ruta: str
) -> None:
    contenido = (RAIZ / ruta).read_text(encoding="utf-8")
    celdas = [c for c in _codigo(notebook) if c.startswith("%%writefile")]
    esperada = f"%%writefile /content/IronVeil/{ruta}\n{contenido}"
    assert esperada.strip("\n") in [c.strip("\n") for c in celdas]


def test_las_celdas_de_python_son_sintaxis_valida(notebook: dict[str, Any]) -> None:
    for celda in _codigo(notebook):
        if celda.startswith("%%writefile"):
            celda = celda.split("\n", 1)[1]
        lineas = [
            ln for ln in celda.splitlines() if not ln.lstrip().startswith(("!", "%"))
        ]
        ast.parse("\n".join(lineas))


def test_la_clave_se_pide_con_getpass_y_nunca_va_escrita(
    notebook: dict[str, Any],
) -> None:
    codigo = "\n".join(_codigo(notebook))
    assert 'getpass.getpass("TYPESAFE_API_KEY: ")' in codigo
    # ninguna asignacion literal de la clave ni nada con aspecto de token
    assert not re.search(r"TYPESAFE_API_KEY\"?\]?\s*=\s*[\"'][^\"']+[\"']", codigo)
    assert not re.search(r"(sk|tsk|Bearer)[-_ ][A-Za-z0-9]{12,}", codigo)


def test_el_permiso_para_el_tercero_esta_a_la_vista(notebook: dict[str, Any]) -> None:
    codigo = "\n".join(_codigo(notebook))
    assert 'os.environ["CLASIFICADOR_PERMITIR_REMOTO"] = "1"' in codigo


def test_se_simula_antes_de_pagar_y_se_guarda_cada_envio(
    notebook: dict[str, Any],
) -> None:
    codigo = [c for c in _codigo(notebook) if not c.startswith("%%writefile")]
    simular = next(i for i, c in enumerate(codigo) if "--simular" in c)
    medir = next(
        i
        for i, c in enumerate(codigo)
        if "medir_clasificador_entrada.py --repeticiones" in c and "--crudo" in c
    )
    assert simular < medir


def test_comprueba_que_los_resultados_no_llevan_la_clave(
    notebook: dict[str, Any],
) -> None:
    codigo = "\n".join(_codigo(notebook))
    assert "assert clave not in contenido" in codigo
    # el zip se arma despues de esa comprobacion
    assert codigo.index("assert clave not in contenido") < codigo.index("ZipFile")


def test_borra_la_clave_al_terminar(notebook: dict[str, Any]) -> None:
    assert 'os.environ.pop("TYPESAFE_API_KEY", None)' in _codigo(notebook)[-1]

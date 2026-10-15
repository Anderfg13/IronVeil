"""El chat reajusta, solo al mostrarla, una respuesta de una palabra por línea."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DEMO_JS = Path(__file__).resolve().parent.parent / "proxy" / "static" / "demo.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node no esta instalado")

LECTURA_DE_ENTRADA = (
    "let s = '';\n"
    "process.stdin.on('data', (d) => { s += d; });\n"
    "process.stdin.on('end', () => {\n"
    "  console.log(JSON.stringify(reajustarLineas(JSON.parse(s))));\n"
    "});\n"
)


def _reajustar(texto: str) -> str:
    fuente = DEMO_JS.read_text(encoding="utf-8")
    bloque = re.search(r"/\* reajuste:inicio.*?/\* reajuste:fin \*/", fuente, re.S)
    assert bloque is not None, "falta el bloque reajuste:inicio/fin en demo.js"
    resultado = subprocess.run(
        [NODE or "node", "-e", bloque.group(0) + "\n" + LECTURA_DE_ENTRADA],
        input=json.dumps(texto),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=30,
    )
    return json.loads(resultado.stdout)


def _una_palabra_por_linea(frase: str) -> str:
    return "\n".join(frase.split())


def test_junta_una_palabra_por_linea_y_deja_las_vallas_solas() -> None:
    frase = "You are un asistente de soporte tecnico para usuarios"
    texto = "```\n" + _una_palabra_por_linea(frase) + "\n```"

    assert _reajustar(texto) == "```\n" + frase + "\n```"


def test_las_lineas_vacias_siguen_separando_parrafos() -> None:
    uno = "primera parte del texto que se mostraba en columna"
    dos = "segunda parte tambien separada por palabras sueltas"
    texto = _una_palabra_por_linea(uno) + "\n\n" + _una_palabra_por_linea(dos)

    assert _reajustar(texto) == uno + "\n\n" + dos


def test_conserva_las_tildes_y_los_signos() -> None:
    frase = "¿Cómo reseteo mi contraseña? Necesito ayuda técnica urgente, gracias"
    texto = _una_palabra_por_linea(frase)

    assert _reajustar(texto) == frase


def test_un_texto_normal_no_se_toca() -> None:
    texto = "Hola, ¿en qué puedo ayudarte?\nTengo varias opciones:\n- una\n- otra"

    assert _reajustar(texto) == texto


def test_una_lista_corta_de_palabras_no_se_toca() -> None:
    texto = "uno\ndos\ntres"

    assert _reajustar(texto) == texto


def test_un_codigo_con_lineas_largas_no_se_toca() -> None:
    lineas = [f"linea numero {i} con varias palabras en cada una" for i in range(12)]
    texto = "\n".join(lineas)

    assert _reajustar(texto) == texto


def test_solo_se_aplica_a_las_respuestas_no_a_los_avisos() -> None:
    fuente = DEMO_JS.read_text(encoding="utf-8")

    assert "esAviso ? texto : reajustarLineas(texto)" in fuente

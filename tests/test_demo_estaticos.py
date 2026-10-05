"""Guardas de la pantalla de chat de la demo (proxy/static/demo.*): seguridad del
frontend, contraste de los colores que usa y que solo hable con /chat."""

from __future__ import annotations

import re

import pytest

import proxy.revision_panel as panel

ESTATICOS = panel.DIRECTORIO_ESTATICO
ARCHIVOS = ["demo.html", "demo.css", "demo.js"]
HTML = (ESTATICOS / "demo.html").read_text(encoding="utf-8")
JS = (ESTATICOS / "demo.js").read_text(encoding="utf-8")
CSS_DEMO = (ESTATICOS / "demo.css").read_text(encoding="utf-8")
CSS = (ESTATICOS / "consola.css").read_text(encoding="utf-8")


def _tokens(bloque_inicio: str, dentro_de: str = "") -> dict[str, str]:
    desde = CSS.index(dentro_de) if dentro_de else 0
    inicio = CSS.index(bloque_inicio, desde)
    fin = CSS.index("}", inicio)
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", CSS[inicio:fin]))


CLARO = _tokens(":root {")
OSCURO = {
    **CLARO,
    **_tokens(":root {", "@media (prefers-color-scheme: dark) {"),
}


def _luminancia(hex_color: str) -> float:
    canales = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales
    )
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(a: str, b: str) -> float:
    alta, baja = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (alta + 0.05) / (baja + 0.05)


# --- Seguridad del frontend ----------------------------------------------------------


@pytest.mark.parametrize("archivo", ARCHIVOS)
def test_la_demo_nunca_inserta_texto_como_html(archivo: str) -> None:
    """Lo que escribe el usuario y lo que responde el modelo pueden ser un ataque."""
    codigo = (ESTATICOS / archivo).read_text(encoding="utf-8")

    for peligroso in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "new Function",
    ):
        assert peligroso not in codigo, f"{archivo} usa {peligroso}"
    assert "onclick=" not in codigo.lower()


@pytest.mark.parametrize("archivo", ARCHIVOS)
def test_la_demo_no_carga_recursos_externos(archivo: str) -> None:
    codigo = (ESTATICOS / archivo).read_text(encoding="utf-8")

    assert "http://" not in codigo
    assert "https://" not in codigo


def test_la_demo_no_incluye_las_credenciales_reales_del_proyecto() -> None:
    """CLAUDE.md, regla 2: los canarios viven en .env/Modelfiles, no en el codigo."""
    for archivo in ARCHIVOS:
        codigo = (ESTATICOS / archivo).read_text(encoding="utf-8")
        assert "SPT-DEMO-8841" not in codigo
        assert "RRHH-DEMO-2291" not in codigo


def test_no_hay_atajos_de_una_sola_tecla_globales() -> None:
    """Enter solo envia dentro del cuadro de texto (WCAG 2.1.4)."""
    assert 'document.addEventListener("keydown"' not in JS
    assert '$("mensaje").addEventListener("keydown"' in JS


def test_los_tamanos_de_la_demo_estan_en_rem_y_no_bajan_de_12_px() -> None:
    assert not re.search(r"font(?:-size)?:[^;]*\d+(?:\.\d+)?px", CSS_DEMO)
    tamanos = [float(n) for n in re.findall(r"font-size: ([\d.]+)rem", CSS_DEMO)]
    assert min(tamanos) * 16 >= 12


def test_el_cuadro_de_texto_tiene_etiqueta_y_la_conversacion_es_un_log() -> None:
    assert 'for="mensaje"' in HTML
    assert 'role="log"' in HTML
    assert "<h1" in HTML
    assert 'id="anuncios"' in HTML


def test_la_demo_define_alternativas_para_colores_forzados_y_poco_movimiento() -> None:
    assert "@media (forced-colors: active)" in CSS_DEMO
    assert "@media (prefers-reduced-motion: reduce)" in CSS_DEMO


# --- Contraste de los colores que usa la demo ---------------------------------

PARES = [
    ("ink", "panel"),
    ("ink", "veil-soft"),
    ("ink-2", "panel"),
    ("ink-2", "panel-2"),
    ("ink-3", "panel"),
    ("on-veil", "veil"),
]


@pytest.mark.parametrize(("tema", "tokens"), [("claro", CLARO), ("oscuro", OSCURO)])
@pytest.mark.parametrize(("texto", "fondo"), PARES)
def test_el_texto_de_la_demo_cumple_contraste_aa(
    tema: str, tokens: dict[str, str], texto: str, fondo: str
) -> None:
    ratio = _contraste(tokens[texto], tokens[fondo])

    assert ratio >= 4.5, f"{tema}: {texto} sobre {fondo} = {ratio:.2f}:1"


def test_la_demo_solo_usa_tokens_que_existen() -> None:
    usados = set(re.findall(r"var\(--([a-z0-9-]+)\)", CSS_DEMO))
    definidos = set(re.findall(r"--([a-z0-9-]+):", CSS))

    assert usados <= definidos, usados - definidos


# --- Es solo un chat ----------------------------------------------------------


def test_el_chat_solo_llama_a_chat_y_no_a_un_endpoint_propio() -> None:
    assert re.findall(r'fetch\("([^"]+)"', JS) == ["/chat"]


def test_el_chat_no_muestra_nada_del_pipeline() -> None:
    """Que mecanismo actuo es para quien opera el sistema: va a los logs, no aqui."""
    for ajeno in ("proceso", "etapa", "filtro", "clasific", "delimit", "defensa"):
        assert ajeno not in HTML.lower(), ajeno
        assert ajeno not in JS.lower(), ajeno


def test_los_avisos_al_usuario_son_genericos() -> None:
    assert "No puedo ayudarte con ese mensaje." in JS
    assert "pendiente de revisión" in JS

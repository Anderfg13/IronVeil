"""Guardas de accesibilidad de la consola (proxy/static): contraste de los
tokens de color, tamanos en rem y comportamiento del JS que protege al revisor.

Los contrastes se calculan con la formula WCAG sobre los hex reales del CSS,
para que un cambio de paleta que rompa el minimo falle aqui y no en produccion.
"""

from __future__ import annotations

import re

import pytest

import proxy.revision_panel as panel

CSS = (panel.DIRECTORIO_ESTATICO / "consola.css").read_text(encoding="utf-8")
JS = (panel.DIRECTORIO_ESTATICO / "revision.js").read_text(encoding="utf-8")
HTML = (panel.DIRECTORIO_ESTATICO / "revision.html").read_text(encoding="utf-8")


def _tokens(bloque_inicio: str) -> dict[str, str]:
    """Variables CSS (--nombre: #hex) del bloque que empieza por `bloque_inicio`."""
    inicio = CSS.index(bloque_inicio)
    fin = CSS.index("}", inicio)
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", CSS[inicio:fin]))


CLARO = _tokens(":root {")
OSCURO = _tokens(':root[data-theme="dark"] {')


def _luminancia(hex_color: str) -> float:
    canales = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales
    )
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(a: str, b: str) -> float:
    alta, baja = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (alta + 0.05) / (baja + 0.05)


# (texto, fondo) que deben cumplir 4.5:1 en ambos temas
PARES_TEXTO = [
    ("ink", "panel"),
    ("ink-2", "panel-2"),
    ("ink-3", "panel"),
    ("ink-3", "panel-2"),
    ("ink-3", "veil-soft"),
    ("on-veil", "veil"),
    ("on-attack", "attack"),
    ("attack", "attack-soft"),
    ("warn", "warn-soft"),
    ("ok", "panel"),
]


@pytest.mark.parametrize(("tema", "tokens"), [("claro", CLARO), ("oscuro", OSCURO)])
@pytest.mark.parametrize(("texto", "fondo"), PARES_TEXTO)
def test_el_texto_cumple_contraste_aa(
    tema: str, tokens: dict[str, str], texto: str, fondo: str
) -> None:
    # En el tema oscuro solo se redefinen algunos tokens: el resto se hereda del claro.
    efectivos = {**CLARO, **tokens}

    ratio = _contraste(efectivos[texto], efectivos[fondo])

    assert ratio >= 4.5, f"{tema}: {texto} sobre {fondo} = {ratio:.2f}:1"


def test_los_rellenos_de_color_no_llevan_texto_blanco_fijo() -> None:
    """Texto sobre --veil/--attack usa los tokens --on-*, que cambian con el tema."""
    for selector in (".avatar", ".siguiente", ".entrar", ".aviso.error"):
        linea = next(x for x in CSS.splitlines() if x.startswith(selector))
        assert "#fff" not in linea, selector
        assert "var(--on-" in linea, selector


def test_los_tamanos_de_fuente_estan_en_rem() -> None:
    """px no respeta el tamano de fuente que el usuario fija en el navegador."""
    assert not re.search(r"font(?:-size)?:[^;]*\d+(?:\.\d+)?px", CSS)


def test_el_texto_mas_pequeno_no_baja_de_12_px() -> None:
    tamanos = [float(n) for n in re.findall(r"font-size: ([\d.]+)rem", CSS)]

    assert min(tamanos) * 16 >= 12


def test_aprobar_y_rechazar_tienen_el_mismo_estilo() -> None:
    """El color no debe sugerir cual de las dos decisiones es la 'segura'."""
    regla = next(
        x for x in CSS.splitlines() if x.startswith(".accion.aprobar, .accion.rechazar")
    )

    assert "var(--ok)" not in regla and "var(--attack)" not in regla
    lineas = CSS.splitlines()
    assert not any(
        x.startswith((".accion.rechazar {", ".accion.aprobar {")) for x in lineas
    )


def test_la_evidencia_va_antes_que_la_lectura_automatica() -> None:
    """Evita el sesgo de anclaje: primero lo que escribio el usuario."""
    evidencia = JS.index("evidenciaDeHerramienta(p) : evidenciaDeTexto(p)")
    lectura = JS.index('h("h3", {}, "Lectura orientativa")')
    assert evidencia < lectura


def test_el_expediente_solo_se_repinta_si_cambia_la_peticion_mostrada() -> None:
    assert "estado.mostrado !== estado.seleccion" in JS
    assert 'id="expediente" aria-live' not in HTML
    assert 'id="anuncios"' in HTML


def test_tras_decidir_el_foco_pasa_al_titulo_nuevo() -> None:
    assert "function enfocarTitulo" in JS
    assert "estado.moverFoco = true" in JS

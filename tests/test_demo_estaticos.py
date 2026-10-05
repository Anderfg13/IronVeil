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
    # La conversacion se apoya en --bg (fondo de la pagina), no en --panel: antes
    # solo se media contra --panel y el aviso de error (ink-2 sobre --iron, 1,86:1
    # en claro) paso sin que ningun test lo viera.
    ("ink", "bg"),
    ("ink-2", "bg"),
    ("ink-3", "bg"),
    ("ink", "panel-2"),
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


def test_el_chat_solo_llama_a_chat_y_a_la_espera_de_su_propio_turno() -> None:
    """/chat y, si queda en revision, /chat/revision/{turno}: nada mas."""
    llamadas = re.findall(r"fetch\((?:\"|`)(/[^\"`$?]*)", JS)

    assert sorted(llamadas) == ["/chat", "/chat/revision/"]


def test_el_chat_no_muestra_nada_del_pipeline() -> None:
    """Que mecanismo actuo es para quien opera el sistema: va a los logs, no aqui."""
    for ajeno in ("proceso", "etapa", "filtro", "clasific", "delimit", "defensa"):
        assert ajeno not in HTML.lower(), ajeno
        assert ajeno not in JS.lower(), ajeno


def test_los_avisos_al_usuario_son_genericos() -> None:
    assert "No puedo ayudarte con ese mensaje." in JS
    assert "pendiente de revisión" in JS


# --- Hallazgos de la auditoria de /demo (2026-10-05) ------------------------------


def _bloque(css: str, cabecera: str) -> str:
    """Contenido de la primera regla/at-rule que empieza por `cabecera`."""
    inicio = css.index("{", css.index(cabecera))
    nivel, k = 1, inicio + 1
    while nivel:
        nivel += {"{": 1, "}": -1}.get(css[k], 0)
        k += 1
    return css[inicio + 1 : k - 1]


def _clases_usadas() -> set[str]:
    clases: set[str] = set()
    for lista in re.findall(r'class="([^"]+)"', HTML):
        clases.update(lista.split())
    for expresion in re.findall(r"class:\s*([^,}]+)", JS):
        for literal in re.findall(r'"([^"]*)"', expresion):
            clases.update(literal.split())
    return clases


COMPARTIDAS = {"barra", "marca", "relleno", "boton-barra", "solo-lectores"}


@pytest.mark.parametrize(("tema", "tokens"), [("claro", CLARO), ("oscuro", OSCURO)])
@pytest.mark.parametrize(
    ("primero", "segundo"),
    [("borde", "panel"), ("borde", "panel-2"), ("veil", "bg"), ("veil", "panel")],
)
def test_los_bordes_y_el_foco_cumplen_3_a_1_no_textual(
    tema: str, tokens: dict[str, str], primero: str, segundo: str
) -> None:
    """WCAG 1.4.11: el borde del selector y del cuadro son su unico indicio visual."""
    ratio = _contraste(tokens[primero], tokens[segundo])

    assert ratio >= 3, f"{tema}: {primero} sobre {segundo} = {ratio:.2f}:1"


def test_el_borde_del_selector_usa_borde_y_no_line() -> None:
    """--line sobre --panel-2 da 1,31:1 en claro: el selector parecia texto suelto."""
    regla = _bloque(CSS_DEMO, ".demo-campo select {")
    assert "border: 1px solid var(--borde)" in regla
    assert "var(--line)" not in regla


def test_las_clases_propias_de_la_demo_no_chocan_con_consola_css() -> None:
    """`.aviso` (recuadro oscuro) y `.usuario` (chip de la barra) existen en
    consola.css: reutilizarlas pintaba el error con 1,86:1 y una raya fantasma."""
    clases = _clases_usadas()
    ajenas = {c for c in clases if not c.startswith("demo-") and c not in COMPARTIDAS}

    assert not ajenas, ajenas
    assert not {"aviso", "usuario"} & clases
    for compartida in COMPARTIDAS:
        assert f".{compartida}" in CSS, compartida
    reglas = re.sub(r"/\*.*?\*/", "", CSS_DEMO, flags=re.S).replace(".demo-aviso", "")
    assert not re.search(r"\.(aviso|usuario)\b", reglas)


def test_el_aviso_se_distingue_por_forma_y_no_solo_por_color() -> None:
    regla = _bloque(CSS_DEMO, ".demo-texto.demo-aviso {")
    assert "border: 1px solid var(--borde)" in regla
    assert "padding" in regla


def test_el_hilo_se_alcanza_con_el_teclado() -> None:
    """Un area con scroll sin foco no se puede desplazar con teclado (WCAG 2.1.1)."""
    assert re.search(r'id="hilo"[^>]*tabindex="0"', HTML)
    assert ".demo-hilo:focus-visible" in CSS_DEMO
    assert not re.search(r"\.demo-hilo:focus\s*\{[^}]*outline:\s*none", CSS_DEMO)


def test_hay_una_sola_region_viva_y_el_hilo_no_se_anuncia_a_si_mismo() -> None:
    """role=log es polite por defecto y #anuncios repetia la respuesta (2 lecturas)."""
    assert re.search(r'id="hilo"[^>]*aria-live="off"', HTML)
    assert len(re.findall(r"aria-live=\"(?!off)", HTML)) == 1
    assert 'id="anuncios" role="status"' in HTML
    assert 'role: "status"' not in JS
    assert "aria-live" not in JS


def test_cada_mensaje_dice_quien_habla_para_lectores_de_pantalla() -> None:
    assert '"Tú: "' in JS
    assert '"Asistente: "' in JS


def test_enter_mientras_responde_no_borra_el_texto_escrito() -> None:
    """Antes se vaciaba el cuadro y enviar() descartaba el mensaje en silencio."""
    envio = JS[JS.index('$("formulario").addEventListener("submit"') :]
    assert envio.index("estado.ocupados") < envio.index('$("mensaje").value = ""')
    assert "MENSAJES.espera" in envio


def test_el_boton_enviar_no_sale_del_orden_del_foco_al_responder() -> None:
    """`disabled` suelta el foco del teclado; aria-disabled lo conserva."""
    assert ".disabled" not in JS
    assert 'setAttribute("aria-disabled", "true")' in JS
    assert '.demo-enviar[aria-disabled="true"]' in CSS_DEMO
    assert ":disabled" not in CSS_DEMO


def test_si_falla_el_texto_vuelve_al_cuadro_salvo_si_quedo_en_revision() -> None:
    assert '$("mensaje").value = texto' in JS
    assert "recuperar = r.status !== 429" in JS
    assert "AbortController" in JS
    assert "signal: control.signal" in JS
    assert re.search(r"TIEMPO_MAXIMO_MS = \d{5,}", JS)


def test_los_avisos_no_usan_textos_tecnicos() -> None:
    assert "(sin respuesta)" not in JS
    assert "no devolvió ningún texto" in JS


def test_el_indicador_de_espera_tiene_texto_visible_y_no_depende_de_la_animacion() -> (
    None
):
    assert 'const ESCRIBIENDO = "Escribiendo…"' in JS
    assert 'h("span", {}, ESCRIBIENDO)' in JS  # visible: no lleva solo-lectores
    assert '"aria-hidden": "true"' in JS  # los puntos son decoracion
    assert "LENTO" in JS and "AVISO_LENTO_MS" in JS


def test_el_logo_no_se_repite_en_la_pantalla_de_chat() -> None:
    """branding.md: logo solo donde da contexto; aqui basta el de la barra."""
    assert HTML.count("<img") == 1  # solo la barra (el icono de pestaña es un <link>)
    assert "logo.svg" not in JS
    assert "demo-avatar" not in CSS_DEMO


def test_los_controles_tactiles_miden_44_px() -> None:
    bloque = _bloque(CSS_DEMO, "@media (max-width: 1020px), (pointer: coarse)")
    assert ".demo-enviar, .demo-campo select { min-height: 44px; }" in bloque
    assert ".demo-campo select { font-size: 1rem; }" in bloque  # iOS no hace zoom


def test_en_pantalla_tactil_enter_es_salto_de_linea_y_no_hay_autofoco() -> None:
    assert 'window.matchMedia("(pointer: coarse)")' in JS
    assert "&& !tactil()" in JS
    assert 'if (!tactil()) $("mensaje").focus();' in JS
    assert JS.count('$("mensaje").focus()') == 3  # vacio, tras responder, al iniciar
    assert "demo-solo-tactil" in HTML and "demo-solo-fino" in HTML
    assert ".demo-solo-fino { display: none; }" in _bloque(
        CSS_DEMO, "@media (pointer: coarse)"
    )


def test_enter_ignora_la_confirmacion_de_una_composicion_ime() -> None:
    assert "ev.isComposing" in JS
    assert "ev.keyCode !== 229" in JS


def test_los_controles_se_parten_en_lineas_en_vez_de_desbordar() -> None:
    """375 px: Enviar se cortaba (391 > 375); 320 px con texto al 200 %: 640 > 320."""
    assert "flex-wrap: wrap" in _bloque(CSS_DEMO, ".demo-controles {")
    assert "flex-wrap: wrap" in _bloque(CSS_DEMO, ".demo-campo {")
    assert "min-width: min(9rem, 100%)" in CSS_DEMO


def test_con_texto_grande_o_pantalla_baja_la_pagina_se_desplaza_sin_recortar() -> None:
    """El cuadro de texto no puede quedar recortado ni la conversacion en 0 px."""
    assert "overflow: hidden" not in _bloque(CSS_DEMO, ".demo-cuerpo {")
    assert "min-height: 8rem" in _bloque(CSS_DEMO, ".demo-hilo {")
    # La barra no se encoge y no es sticky: no tapa el foco (WCAG 2.4.11).
    barra = _bloque(CSS_DEMO, ".demo-cuerpo > .barra")
    assert "flex: none" in barra and "position: static" in barra


def test_la_respuesta_larga_se_muestra_desde_su_primera_linea() -> None:
    assert "function verDesdeArriba" in JS
    assert "verDesdeArriba(vista.mensaje)" in JS


def test_el_contador_coincide_con_el_limite_del_cuadro_de_texto() -> None:
    limite = int(re.search(r"const LIMITE = (\d+)", JS).group(1))  # type: ignore[union-attr]
    maxlength = int(re.search(r'maxlength="(\d+)"', HTML).group(1))  # type: ignore[union-attr]

    assert limite == maxlength
    assert 'id="contador"' in HTML
    assert "AVISAR_DESDE" in JS


def test_la_ayuda_esta_asociada_al_cuadro_de_texto_y_avisa_que_es_un_modelo() -> None:
    assert 'aria-describedby="ayuda"' in HTML
    assert 'id="ayuda"' in HTML
    assert "las genera un modelo y pueden tener errores" in HTML


def test_el_teclado_virtual_no_tapa_el_cuadro_de_texto() -> None:
    assert "interactive-widget=resizes-content" in HTML


def test_colores_forzados_dibujan_bordes_en_controles_y_puntos() -> None:
    forzados = _bloque(CSS_DEMO, "@media (forced-colors: active)")
    assert (
        ".demo-enviar, .demo-campo select { border: 2px solid ButtonText; }" in forzados
    )
    assert "GrayText" in forzados  # estado "enviando"
    assert "forced-color-adjust: none" in forzados  # los puntos usaban currentcolor
    assert "background: CanvasText" in forzados


def test_el_rotulo_oculto_del_asistente_no_escapa_del_hilo() -> None:
    """`.solo-lectores` es absolute: sin un ancestro `position: relative` dentro del
    hilo, su caja queda fuera del recorte del scroll y la pagina entera se
    desplaza (medido en el navegador: 6247 px de alto con una ventana de 700)."""
    assert "position: absolute" in CSS.split(".solo-lectores", 1)[1].split("}", 1)[0]
    asistente = re.search(r"\.demo-asistente \{([^}]*)\}", CSS_DEMO)
    assert asistente is not None
    assert "position: relative" in asistente.group(1)
    assert ".demo-burbuja" in CSS_DEMO  # la burbuja propia ya lo tiene
    burbuja = re.search(r"\.demo-propio \.demo-burbuja \{([^}]*)\}", CSS_DEMO)
    assert burbuja is not None
    assert "position: relative" in burbuja.group(1)

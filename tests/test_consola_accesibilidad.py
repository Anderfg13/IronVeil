"""Guardas de accesibilidad de la consola (proxy/static): contraste de los
tokens de color, tamanos en rem y comportamiento del JS que protege al revisor.

Los contrastes se calculan con la formula WCAG sobre los hex reales del CSS,
para que un cambio de paleta que rompa el minimo falle aqui y no en produccion.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

import proxy.revision_panel as panel

CSS = (panel.DIRECTORIO_ESTATICO / "consola.css").read_text(encoding="utf-8")
JS = (panel.DIRECTORIO_ESTATICO / "revision.js").read_text(encoding="utf-8")
HTML = (panel.DIRECTORIO_ESTATICO / "revision.html").read_text(encoding="utf-8")
LOGIN_HTML = (panel.DIRECTORIO_ESTATICO / "login.html").read_text(encoding="utf-8")
LOGIN_JS = (panel.DIRECTORIO_ESTATICO / "login.js").read_text(encoding="utf-8")


def _tokens(bloque_inicio: str, dentro_de: str = "") -> dict[str, str]:
    """Variables CSS (--nombre: #hex) del bloque que empieza por `bloque_inicio`.

    Con `dentro_de` se busca el bloque despues de esa cabecera (una @media).
    """
    desde = CSS.index(dentro_de) if dentro_de else 0
    inicio = CSS.index(bloque_inicio, desde)
    fin = CSS.index("}", inicio)
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", CSS[inicio:fin]))


CLARO = _tokens(":root {")
OSCURO = _tokens(":root {", "@media (prefers-color-scheme: dark) {")
MAS_CONTRASTE_CLARO = _tokens(":root {", "@media (prefers-contrast: more) {")
MAS_CONTRASTE_OSCURO = _tokens(
    ":root {", "@media (prefers-contrast: more) and (prefers-color-scheme: dark) {"
)
TEMAS = [("claro", CLARO), ("oscuro", OSCURO)]


def _luminancia(hex_color: str) -> float:
    canales = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales
    )
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(a: str, b: str) -> float:
    alta, baja = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (alta + 0.05) / (baja + 0.05)


def _efectivos(tokens: dict[str, str]) -> dict[str, str]:
    # En el tema oscuro solo se redefinen algunos tokens: el resto se hereda del claro.
    return {**CLARO, **tokens}


# (texto, fondo) que deben cumplir 4.5:1 en ambos temas
PARES_TEXTO = [
    ("ink", "panel"),
    ("ink", "bg"),
    ("ink-2", "panel"),
    ("ink-2", "panel-2"),
    ("ink-2", "bg"),
    ("ink-3", "panel"),
    ("ink-3", "panel-2"),
    ("ink-3", "veil-soft"),
    ("ink-3", "bg"),
    ("on-veil", "veil"),
    ("on-attack", "attack"),
    ("attack", "attack-soft"),
    ("attack", "panel"),
    ("attack", "bg"),
    ("warn", "warn-soft"),
    ("ok", "panel"),
    ("ok", "panel-2"),
    ("veil", "veil-soft"),
    ("iron-ink", "iron"),
    ("iron-ink-2", "iron"),
    ("iron-ink-3", "iron"),
]

# (elemento grafico, fondo) que deben cumplir 3:1 (WCAG 1.4.11)
PARES_NO_TEXTO = [
    ("media", "panel"),
    ("media", "panel-2"),
    ("media", "veil-soft"),
    ("media", "warn-soft"),
    ("attack", "panel"),
    ("ok", "panel"),
    ("veil", "panel"),
    ("veil", "veil-soft"),
    ("borde", "panel"),
    ("borde", "panel-2"),
    ("borde", "bg"),
    ("ink-2", "panel"),
    ("iron-ink", "iron"),
]


@pytest.mark.parametrize(("tema", "tokens"), TEMAS)
@pytest.mark.parametrize(("texto", "fondo"), PARES_TEXTO)
def test_el_texto_cumple_contraste_aa(
    tema: str, tokens: dict[str, str], texto: str, fondo: str
) -> None:
    efectivos = _efectivos(tokens)

    ratio = _contraste(efectivos[texto], efectivos[fondo])

    assert ratio >= 4.5, f"{tema}: {texto} sobre {fondo} = {ratio:.2f}:1"


@pytest.mark.parametrize(("tema", "tokens"), TEMAS)
@pytest.mark.parametrize(("grafico", "fondo"), PARES_NO_TEXTO)
def test_los_elementos_no_textuales_cumplen_3_a_1(
    tema: str, tokens: dict[str, str], grafico: str, fondo: str
) -> None:
    efectivos = _efectivos(tokens)

    ratio = _contraste(efectivos[grafico], efectivos[fondo])

    assert ratio >= 3, f"{tema}: {grafico} sobre {fondo} = {ratio:.2f}:1"


@pytest.mark.parametrize(
    ("tema", "tokens"),
    [("claro", MAS_CONTRASTE_CLARO), ("oscuro", MAS_CONTRASTE_OSCURO)],
)
@pytest.mark.parametrize("texto", ["ink-2", "ink-3"])
def test_con_contraste_alto_el_texto_secundario_llega_a_7_a_1(
    tema: str, tokens: dict[str, str], texto: str
) -> None:
    base = OSCURO if tema == "oscuro" else {}
    efectivos = {**CLARO, **base, **tokens}

    for fondo in ("panel", "panel-2", "bg"):
        ratio = _contraste(efectivos[texto], efectivos[fondo])
        assert ratio >= 7, f"{tema}: {texto} sobre {fondo} = {ratio:.2f}:1"


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

    assert "var(--ok)" not in regla
    assert "var(--attack)" not in regla
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


# --- M1: atajos de una tecla ---


def test_los_atajos_solo_actuan_con_el_foco_dentro_de_la_lista_o_el_expediente() -> (
    None
):
    assert 'destino.closest(".lista, #expediente")' in JS
    assert "evento.repeat" in JS
    assert "evento.shiftKey" in JS


def test_los_atajos_se_pueden_desactivar_y_su_ayuda_es_visible() -> None:
    assert 'id="atajos-activos"' in HTML
    assert "J y K cambian de petición" in HTML
    assert "if (!estado.atajos" in JS
    assert ".sin-atajos .accion kbd" in CSS


def test_el_dialogo_de_confirmacion_no_deja_un_boton_predeterminado() -> None:
    """Una tecla suelta no debe poder confirmar: el foco va al titulo (alerts.md)."""
    assert '$("confirmar-titulo").focus()' in JS
    assert "ok.focus()" not in JS
    assert 'aria-describedby="confirmar-texto"' in HTML


# --- M2: pestanas ---


def test_las_pestanas_implementan_el_patron_tablist_completo() -> None:
    assert 'role="tablist"' in HTML
    assert 'aria-label="Vista de peticiones"' in HTML
    # Pendientes, Historial y Memoria (esta ultima siempre se ve: apagada, explica
    # como encenderla).
    assert HTML.count('role="tab"') == 3
    assert 'role="tabpanel" id="panel-lista" aria-labelledby="tab-pendientes"' in HTML
    assert HTML.count('aria-controls="panel-lista"') == 3
    assert not re.search(r'id="tab-memoria"[^>]*[ ]hidden', HTML)  # siempre visible
    assert re.search(r'id="tab-memoria"[^>]*aria-selected="false"', HTML)
    # tabindex itinerante: solo la pestana activa entra en el orden de tabulacion
    assert 'id="tab-pendientes"' in HTML
    assert 'tabindex="0"' in HTML
    assert 'id="tab-historial" aria-selected="false"' in HTML
    assert re.search(r'id="tab-historial"[^>]*tabindex="-1"', HTML)
    for tecla in ("ArrowRight", "ArrowLeft", "Home", "End"):
        assert f'"{tecla}"' in JS
    assert '"aria-labelledby", `tab-${nombre}`' in JS


# --- Pestana Memoria (extension opcional) ---


def test_la_memoria_envia_el_token_csrf_tambien_al_borrar() -> None:
    assert 'opciones.method === "DELETE"' in JS
    assert "X-CSRF-Token" in JS


def test_la_pestana_memoria_siempre_se_ve_y_explica_como_encenderla() -> None:
    assert 'id="tab-memoria"' in HTML
    assert not re.search(r'id="tab-memoria"[^>]*[ ]hidden', HTML)
    assert "La memoria está apagada" in JS
    assert "MEMORIA_RECHAZOS=1" in JS


def test_solo_los_revisores_ven_olvidar_y_tiene_nombre_accesible() -> None:
    assert 'estado.sesion?.rol === "revisor"' in JS
    assert 'h("span", { class: "solo-lectores" }, " esta regla")' in JS


def test_al_rechazar_se_avisa_que_se_recordara_y_despues_si_se_recordo() -> None:
    assert "Además se recordará" in JS
    assert "TEXTOS_MEMORIA" in JS and "recordada_sin_guardar" in JS


def test_olvidar_una_regla_siempre_pide_confirmacion() -> None:
    assert "confirmarOlvidar(r)" in JS
    assert "ok.onclick = () => { dialogo.close(); void olvidar(regla); };" in JS


# --- M3: avisos de error ---


def test_los_errores_persisten_con_role_alert_y_boton_de_cierre() -> None:
    assert 'role: error ? "alert" : "status"' in JS
    assert "cerrar-aviso" in JS
    assert "if (!error) setTimeout" in JS
    assert 'id="avisos" role=' not in HTML  # el rol vive en cada aviso


def test_los_errores_dicen_que_paso_y_como_arreglarlo() -> None:
    for frase in (
        "Inicia sesión de nuevo con una cuenta de revisor",
        "Comprueba que el proxy esté en marcha e inténtalo otra vez",
    ):
        assert frase in JS
    assert "Comprueba que esté en marcha" in LOGIN_JS


# --- M4: encabezados ---


@pytest.mark.parametrize("pagina", [HTML, LOGIN_HTML])
def test_cada_pagina_tiene_un_unico_h1(pagina: str) -> None:
    assert len(re.findall(r"<h1[ >]", pagina)) == 1


def test_la_jerarquia_de_encabezados_no_salta_niveles() -> None:
    # revision.html: h1 > h2 (peticiones, dialogo). Los h3 los pinta el JS bajo un h2.
    assert "<h3" not in HTML
    assert "<h3" not in LOGIN_HTML
    assert 'id="titulo-lista"' in HTML
    assert 'h2", { tabindex: "-1" }, estado.pendientes.length' in JS
    assert '<h2 id="confirmar-titulo"' in HTML


# --- M5: contraste alto y colores forzados ---


def test_hay_reglas_para_colores_forzados_y_contraste_alto() -> None:
    assert "@media (forced-colors: active)" in CSS
    assert "@media (prefers-contrast: more)" in CSS
    bloque = CSS[CSS.index("@media (forced-colors: active)") :]
    for necesario in (".evidencia mark", ".elemento::before", ".pestana", ".espectro"):
        assert necesario in bloque, necesario
    assert "Highlight" in bloque
    assert "CanvasText" in bloque


def test_la_evidencia_distingue_el_tipo_sin_depender_del_color() -> None:
    assert re.search(r"mark\.codificado[^}]*text-decoration-style: dotted", CSS)
    assert re.search(r"mark\.patron[^}]*text-decoration-style: solid", CSS)
    assert "box-shadow: inset 0 -2px" not in CSS  # el subrayado ya no es una sombra
    assert "Subrayado punteado" in JS
    assert "Subrayado continuo" in JS


def test_la_gravedad_tiene_forma_y_texto_ademas_de_color() -> None:
    assert ".nivel-media::before" in CSS
    assert ".nivel-baja::before" in CSS
    assert "const GRAVEDAD" in JS
    assert '"gravedad"' in JS


# --- M6: color de la gravedad media ---


def test_el_punto_de_gravedad_media_tiene_token_por_tema() -> None:
    assert "media" in CLARO
    assert "media" in OSCURO
    assert CLARO["media"] != OSCURO["media"]
    assert "#d98c0a" not in CSS.split("@media (prefers-color-scheme: dark)")[0].replace(
        "--media: #b87400", ""
    )


# --- M7: objetivos tactiles ---


def test_los_controles_llegan_a_44_px_en_vistas_estrechas_o_tactiles() -> None:
    inicio = CSS.index("@media (max-width: 1020px), (pointer: coarse)")
    bloque = CSS[inicio : CSS.index("\n}", inicio)]
    for selector in (
        ".boton-barra",
        ".secundario",
        ".pestana",
        ".accion",
        ".siguiente",
    ):
        assert selector in bloque, selector
    assert "min-height: 44px" in bloque


def test_los_botones_tienen_estado_de_pulsacion() -> None:
    assert "button:active:not(:disabled)" in CSS


# --- M8: franja de estado ---


def test_las_cuatro_tarjetas_numero_grande_se_sustituyeron_por_una_franja() -> None:
    assert 'class="cifra' not in HTML
    assert ".cifra" not in CSS
    assert 'id="franja"' in HTML
    assert "resumen-historial" in HTML  # Decididas y tiempo medio viven en Historial


# --- L1: apariencia del sistema ---


def test_no_hay_interruptor_de_tema_propio() -> None:
    assert 'id="tema"' not in HTML
    assert ">Tema<" not in HTML
    assert "data-theme" not in CSS + JS + HTML + LOGIN_HTML
    assert "ironveil-tema" not in JS
    assert "color-scheme: light dark" in CSS


# --- L2: plurales ---


def test_los_plurales_se_calculan_con_una_funcion() -> None:
    assert 'plural(e.aprobadas, "aprobada", "aprobadas")' in JS
    assert 'plural(e.rechazadas, "rechazada", "rechazadas")' in JS
    assert "aprobadas · ${e.rechazadas}" not in JS


@pytest.mark.skipif(shutil.which("node") is None, reason="requiere node")
@pytest.mark.parametrize(
    ("aprobadas", "rechazadas", "esperado"),
    [
        (1, 0, "1 decidida: 1 aprobada · 0 rechazadas"),
        (1, 1, "2 decididas: 1 aprobada · 1 rechazada"),
        (3, 2, "5 decididas: 3 aprobadas · 2 rechazadas"),
        (0, 0, ""),
    ],
)
def test_el_resumen_del_historial_usa_el_plural_correcto(
    aprobadas: int, rechazadas: int, esperado: str
) -> None:
    funciones = "\n".join(
        re.search(rf"function {nombre}\(.*?\n\}}\n", JS, re.S).group(0)  # type: ignore[union-attr]
        for nombre in ("plural", "duracion", "resumenHistorial")
    )
    entrada = json.dumps(
        {
            "aprobadas": aprobadas,
            "rechazadas": rechazadas,
            "tiempo_medio_decision_s": None,
        }
    )
    resultado = subprocess.run(  # noqa: S603
        [
            "node",
            "-e",
            f"{funciones}\nconsole.log(resumenHistorial({entrada}))",
        ],  # noqa: S607
        capture_output=True,
        encoding="utf-8",  # node escribe UTF-8; sin esto Windows decodifica con cp1252
        check=True,
        timeout=20,
    )

    assert resultado.stdout.strip() == esperado


# --- L3: el logo no se repite ---


def test_el_logo_aparece_una_vez_por_pagina() -> None:
    assert "logo.svg" not in JS  # ni en la lista ni en el expediente vacios
    assert HTML.count('src="/revision/static/logo.svg"') == 1
    assert LOGIN_HTML.count('src="/revision/static/logo.svg"') == 1


# --- L4: transparencia reducida ---


def test_la_barra_de_decision_tiene_fondo_opaco_sin_transparencia() -> None:
    inicio = CSS.index("@media (prefers-reduced-transparency: reduce)")
    bloque = CSS[inicio : CSS.index("\n}", inicio)]
    assert ".decision" in bloque
    assert "backdrop-filter: none" in bloque


# --- L5: login ---


def test_el_login_permite_mostrar_la_contrasena_sin_romper_el_autocompletado() -> None:
    assert 'id="ver-clave"' in LOGIN_HTML
    assert 'aria-pressed="false"' in LOGIN_HTML
    assert 'autocomplete="current-password"' in LOGIN_HTML
    assert 'type="password"' in LOGIN_HTML
    assert '"aria-pressed"' in LOGIN_JS


def test_el_aviso_del_modo_laboratorio_no_nombra_variables_de_entorno() -> None:
    assert "REVISION_USUARIOS" not in HTML + JS
    assert "inicio de sesión" in HTML


def test_el_boton_del_login_se_llama_igual_que_la_pantalla() -> None:
    assert "<h1>Iniciar sesión</h1>" in LOGIN_HTML
    assert ">Iniciar sesión</button>" in LOGIN_HTML


# --- Hallazgos nuevos de la auditoria ---


def test_el_estado_en_vivo_no_es_una_region_viva() -> None:
    """Cambia cada segundo: solo se anuncian los cambios de conexion."""
    assert 'id="vivo" role=' not in HTML
    assert "Se perdió la conexión con el proxy." in JS


def test_el_foco_se_ve_sobre_la_barra_oscura() -> None:
    assert ".barra :focus-visible { outline-color: var(--iron-ink); }" in CSS


def test_los_campos_tienen_borde_de_3_a_1_y_foco_visible() -> None:
    regla = next(x for x in CSS.splitlines() if x.startswith(".campo input {"))
    assert "var(--borde)" in regla
    assert ".campo input:focus-visible" in CSS
    assert "outline: 2px solid var(--veil-soft)" not in CSS


def test_hay_un_salto_al_expediente_para_teclado() -> None:
    assert 'class="saltar" href="#expediente"' in HTML
    assert 'id="expediente" tabindex="-1"' in HTML


# --- Identidad: vidrio, paleta y tipografia (2026-10-06) ------------------------------


def _porcentaje(nombre: str, tema: str) -> float:
    """Opacidad del vidrio (--vidrio-pct / --iron-vidrio-pct) del tema indicado."""
    desde = (
        CSS.index("@media (prefers-color-scheme: dark) {") if tema == "oscuro" else 0
    )
    inicio = CSS.index(":root {", desde)
    bloque = CSS[inicio : CSS.index("}", inicio)]
    return int(re.search(rf"--{nombre}:\s*(\d+)%", bloque).group(1)) / 100  # type: ignore[union-attr]


def _mezclar(frente: str, fondo: str, alfa: float) -> str:
    """Color resultante de poner `frente` con opacidad `alfa` sobre `fondo`."""
    canales = [
        round(
            int(frente[i : i + 2], 16) * alfa + int(fondo[i : i + 2], 16) * (1 - alfa)
        )
        for i in (1, 3, 5)
    ]
    return "#" + "".join(f"{c:02x}" for c in canales)


# Lo que puede haber detras del vidrio: el fondo de la pagina, las dos luces de hielo
# y las superficies opacas por las que se desplaza el contenido. El desenfoque
# promedia lo que haya debajo, asi que no se mide contra pixeles de texto sueltos.
DETRAS = ["bg", "hielo-1", "hielo-2", "panel", "panel-2"]


@pytest.mark.parametrize(("tema", "tokens"), TEMAS)
@pytest.mark.parametrize("texto", ["ink", "ink-2", "ink-3"])
@pytest.mark.parametrize("detras", DETRAS)
def test_el_texto_sobre_vidrio_claro_cumple_aa_con_cualquier_fondo(
    tema: str, tokens: dict[str, str], texto: str, detras: str
) -> None:
    """.tarjeta, .vidrio y la caja del chat: panel translucido sobre el hielo."""
    efectivos = _efectivos(tokens)
    vidrio = _mezclar(
        efectivos["panel"], efectivos[detras], _porcentaje("vidrio-pct", tema)
    )

    ratio = _contraste(efectivos[texto], vidrio)

    assert ratio >= 4.5, f"{tema}: {texto} sobre vidrio/{detras} = {ratio:.2f}:1"


@pytest.mark.parametrize(("tema", "tokens"), TEMAS)
@pytest.mark.parametrize("texto", ["iron-ink", "iron-ink-2", "iron-ink-3"])
@pytest.mark.parametrize("detras", DETRAS)
def test_el_texto_sobre_el_vidrio_de_grafito_cumple_aa_con_cualquier_fondo(
    tema: str, tokens: dict[str, str], texto: str, detras: str
) -> None:
    """.barra y .aviso: grafito translucido (el logo y el nombre viven aqui)."""
    efectivos = _efectivos(tokens)
    vidrio = _mezclar(
        efectivos["iron"], efectivos[detras], _porcentaje("iron-vidrio-pct", tema)
    )

    ratio = _contraste(efectivos[texto], vidrio)

    assert ratio >= 4.5, f"{tema}: {texto} sobre grafito/{detras} = {ratio:.2f}:1"


def test_el_vidrio_tiene_alternativa_sin_transparencia_ni_soporte() -> None:
    """Sin backdrop-filter, con transparencia reducida, contraste alto o colores
    forzados las superficies pasan a ser opacas: mismo diseno, sin cristal."""
    assert (
        "@media (prefers-reduced-transparency: reduce), (prefers-contrast: more)" in CSS
    )
    assert "@supports not ((backdrop-filter: blur(1px))" in CSS
    forzados = CSS[CSS.index("@media (forced-colors: active)") :]
    assert "backdrop-filter: none" in forzados
    assert ".acceso form" in forzados


def test_el_vidrio_conserva_un_borde_visible_con_contraste_alto() -> None:
    mas = CSS[CSS.index("@media (prefers-contrast: more) {") :]
    assert "border-color: var(--borde)" in mas


def test_la_tipografia_es_la_del_sistema_sin_fuentes_externas() -> None:
    """Identidad: tipografia nativa (SF Pro en Apple, Segoe UI Variable en Windows)."""
    ui = re.search(r"--ui:\s*([^;]+);", CSS).group(1)  # type: ignore[union-attr]
    assert ui.startswith("system-ui, -apple-system")
    assert '"SF Pro Text"' in ui and '"Segoe UI Variable Text"' in ui
    assert "--display:" in CSS and '"SF Pro Display"' in CSS
    assert "@font-face" not in CSS
    assert "@import" not in CSS
    assert "url(" not in CSS  # ningun recurso externo (CSP: font-src/img-src)


def test_el_logo_tiene_un_espacio_propio_y_se_reemplaza_por_archivo() -> None:
    """Un solo archivo (logo.svg) y una sola caja (.marca-logo) en las tres paginas."""
    assert ".marca-logo {" in CSS and "var(--logo, 36px)" in CSS
    demo = (panel.DIRECTORIO_ESTATICO / "demo.html").read_text(encoding="utf-8")
    for pagina in (HTML, LOGIN_HTML, demo):
        assert 'class="marca-logo"' in pagina
        assert "/revision/static/logo.svg" in pagina
        assert "reemplaza proxy/static/logo.svg" in pagina


def test_el_logo_es_un_svg_limpio_sin_texto_ni_recursos_externos() -> None:
    logo = (panel.DIRECTORIO_ESTATICO / "logo.svg").read_text(encoding="utf-8")

    assert 'viewBox="0 0 64 64"' in logo
    assert 'aria-label="IronVeil"' in logo
    assert (
        "<text" not in logo
    )  # sin tipografia incrustada: escala y no depende de fuentes
    assert "<image" not in logo and "<script" not in logo
    assert "http" not in logo.replace('xmlns="http://www.w3.org/2000/svg"', "")


def test_el_nombre_de_la_marca_se_escribe_igual_en_las_tres_paginas() -> None:
    """IronVeil = «Iron» en negrita + «Veil» en regular (texto, no imagen)."""
    demo = (panel.DIRECTORIO_ESTATICO / "demo.html").read_text(encoding="utf-8")
    assert "<h1><b>Iron</b>Veil<small>" in HTML
    assert '<div class="nombre-marca"><b>Iron</b>Veil</div>' in LOGIN_HTML
    assert '<div class="nombre-marca"><b>Iron</b>Veil</div>' in demo


def test_la_paleta_documentada_coincide_con_el_css() -> None:
    """docs/IDENTIDAD.md es la referencia de la marca: sus hex no pueden desviarse."""
    from pathlib import Path

    doc = (Path(__file__).resolve().parent.parent / "docs" / "IDENTIDAD.md").read_text(
        encoding="utf-8"
    )
    filas = re.findall(
        r"\|\s*`--([a-z0-9-]+)`\s*\|\s*`(#[0-9a-f]{6})`\s*\|\s*`(#[0-9a-f]{6})`", doc
    )
    assert len(filas) >= 10
    for nombre, claro, oscuro in filas:
        assert CLARO[nombre] == claro, nombre
        assert _efectivos(OSCURO)[nombre] == oscuro, nombre

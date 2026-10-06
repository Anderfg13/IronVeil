"""Pruebas de ARQUITECTURA del paquete SIEM: vigilan los principios, no el
comportamiento.

Si alguien acopla una capa con otra (un formato que conoce un transporte, un
adaptador que lee `os.environ`, el servicio que importa un SIEM concreto), estas
pruebas fallan. Es la forma de que "puertos y adaptadores" siga siendo cierto dentro
de seis meses.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent / "proxy"
PAQUETE = RAIZ / "siem"
BASE = "proxy.siem"


def _importaciones(ruta: Path) -> set[str]:
    modulos: set[str] = set()
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Import):
            modulos.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
            modulos.add(nodo.module)
    return modulos


def _internas(ruta: Path) -> set[str]:
    return {m for m in _importaciones(ruta) if m.startswith("proxy")}


def _lee_el_entorno(ruta: Path) -> bool:
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Attribute) and isinstance(nodo.value, ast.Name):
            if nodo.value.id == "os" and nodo.attr in ("environ", "getenv"):
                return True
    return False


def _modulos(subcarpeta: str) -> list[Path]:
    return sorted(
        p for p in (PAQUETE / subcarpeta).glob("*.py") if p.name != "__init__.py"
    )


# --- dependencias: cada capa solo conoce la de abajo ---------------------------


def test_el_dominio_y_los_puertos_no_dependen_de_nada_del_proyecto() -> None:
    assert _internas(PAQUETE / "evento.py") == set()
    assert _internas(PAQUETE / "puertos.py") == set()


def test_el_servicio_solo_conoce_los_puertos() -> None:
    assert _internas(PAQUETE / "exportador.py") == {f"{BASE}.puertos"}


def test_el_registro_solo_conoce_los_puertos() -> None:
    assert _internas(PAQUETE / "registro.py") == {f"{BASE}.puertos"}


@pytest.mark.parametrize("formato", _modulos("formatos"), ids=lambda p: p.name)
def test_un_formato_solo_conoce_el_dominio_y_los_puertos(formato: Path) -> None:
    assert _internas(formato) <= {f"{BASE}.evento", f"{BASE}.puertos"}


@pytest.mark.parametrize("transporte", _modulos("transportes"), ids=lambda p: p.name)
def test_un_transporte_no_conoce_formatos_ni_servicio_ni_composicion(
    transporte: Path,
) -> None:
    prohibidos = {
        f"{BASE}.formatos",
        f"{BASE}.exportador",
        f"{BASE}.composicion",
        "proxy.main",
    }

    assert not {m for m in _internas(transporte) if m.startswith(tuple(prohibidos))}


def test_un_formato_no_conoce_ningun_transporte() -> None:
    for formato in _modulos("formatos"):
        assert not {m for m in _internas(formato) if "transportes" in m}


def test_el_servicio_no_conoce_ningun_siem_concreto() -> None:
    internas = _internas(PAQUETE / "exportador.py")

    assert not {m for m in internas if "transportes" in m or "formatos" in m}


def test_solo_la_composicion_conoce_los_adaptadores_incluidos() -> None:
    for ruta in PAQUETE.rglob("*.py"):
        if ruta.name in ("composicion.py", "__init__.py"):
            continue
        conocidos = {
            m for m in _internas(ruta) if m.endswith((".formatos", ".transportes"))
        }
        assert not conocidos, ruta.name


# --- el entorno y los secretos --------------------------------------------------


def test_solo_la_composicion_lee_el_entorno() -> None:
    lectores = [p.name for p in PAQUETE.rglob("*.py") if _lee_el_entorno(p)]

    assert lectores == ["composicion.py"]


def test_el_cargador_de_complementos_no_depende_de_nada_del_proyecto() -> None:
    assert _internas(RAIZ / "complementos.py") == set()


# --- seguridad del codigo (CLAUDE.md, seccion 7) --------------------------------


def _alguna_llamada_con(ruta: Path, argumento: str, valor: object) -> bool:
    """True si el modulo llama a algo con `argumento=valor` (por AST: un comentario o
    un docstring que lo mencione no cuenta)."""
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Call):
            for kw in nodo.keywords:
                if kw.arg == argumento and getattr(kw.value, "value", None) is valor:
                    return True
    return False


@pytest.mark.parametrize("ruta", sorted(PAQUETE.rglob("*.py")), ids=lambda p: p.name)
def test_nunca_se_desactiva_la_verificacion_tls(ruta: Path) -> None:
    texto = ruta.read_text(encoding="utf-8")

    assert not _alguna_llamada_con(ruta, "verify", False)
    assert "CERT_NONE" not in texto
    assert "check_hostname = False" not in texto
    assert "_create_unverified_context" not in texto


@pytest.mark.parametrize("ruta", sorted(PAQUETE.rglob("*.py")), ids=lambda p: p.name)
def test_nunca_hay_shell_ni_yaml_inseguro(ruta: Path) -> None:
    texto = ruta.read_text(encoding="utf-8")

    assert not _alguna_llamada_con(ruta, "shell", True)
    assert "yaml.load(" not in texto


def test_el_cliente_http_no_sigue_redirecciones() -> None:
    texto = (PAQUETE / "transportes" / "https_generico.py").read_text(encoding="utf-8")

    assert "follow_redirects=False" in texto

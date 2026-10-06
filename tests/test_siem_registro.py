"""El registro de formatos y transportes y la configuracion que lo usa."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from proxy.siem import ErrorSIEM
from proxy.siem.composicion import (
    Configuracion,
    construir,
    construir_registro,
)
from proxy.siem.registro import ContextoConector, RegistroSIEM


class _FormatoDePrueba:
    tipo_contenido = "text/x-prueba"

    def formatear(self, evento: dict[str, object]) -> str:
        return "formato-de-prueba"


class _ConectorDePrueba:
    def __init__(self, destino: str, contexto: ContextoConector) -> None:
        self.destino = destino
        self.contexto = contexto
        self.enviados: list[str] = []

    def enviar(self, mensaje: str) -> None:
        self.enviados.append(mensaje)


@pytest.fixture
def registro() -> RegistroSIEM:
    nuevo = RegistroSIEM()
    nuevo.registrar_formato("prueba", _FormatoDePrueba)
    nuevo.registrar_formato("otro", _FormatoDePrueba)
    nuevo.registrar_conector("falso", _ConectorDePrueba, formato_por_defecto="prueba")
    return nuevo


# --- interpretar un destino ---------------------------------------------------


def test_sin_formato_se_usa_el_que_trae_el_transporte(registro: RegistroSIEM) -> None:
    resuelto = registro.resolver("falso://donde/sea", {})

    assert resuelto.descripcion == "prueba@falso"
    assert isinstance(resuelto.formateador, _FormatoDePrueba)


def test_con_formato_explicito_se_usa_ese(registro: RegistroSIEM) -> None:
    assert registro.resolver("otro@falso://x", {}).descripcion == "otro@falso"


def test_el_conector_recibe_lo_que_sigue_al_esquema_y_el_tipo_de_contenido(
    registro: RegistroSIEM,
) -> None:
    resuelto = registro.resolver("falso://host:9/ruta", {"SIEM_X": "1"})

    conector = resuelto.conector
    assert isinstance(conector, _ConectorDePrueba)
    assert conector.destino == "host:9/ruta"
    assert conector.contexto.tipo_contenido == "text/x-prueba"
    assert conector.contexto.entorno == {"SIEM_X": "1"}


def test_el_esquema_y_el_formato_no_distinguen_mayusculas(
    registro: RegistroSIEM,
) -> None:
    assert registro.resolver("OTRO@FALSO://x", {}).descripcion == "otro@falso"


@pytest.mark.parametrize(
    "destino",
    ["", "sin-esquema", "falso://", "://x", "formato@", "1falso://x"],
)
def test_un_destino_mal_escrito_se_rechaza(
    registro: RegistroSIEM, destino: str
) -> None:
    with pytest.raises(ErrorSIEM) as exc:
        registro.resolver(destino, {})

    assert not exc.value.reintentable


def test_un_esquema_desconocido_lista_los_disponibles(registro: RegistroSIEM) -> None:
    with pytest.raises(ErrorSIEM, match="falso"):
        registro.resolver("inventado://x", {})


def test_un_formato_desconocido_lista_los_disponibles(registro: RegistroSIEM) -> None:
    with pytest.raises(ErrorSIEM, match="prueba"):
        registro.resolver("inventado@falso://x", {})


def test_registrar_dos_veces_lo_mismo_es_un_error(registro: RegistroSIEM) -> None:
    with pytest.raises(ValueError, match="ya esta registrado"):
        registro.registrar_formato("prueba", _FormatoDePrueba)
    with pytest.raises(ValueError, match="ya esta registrado"):
        registro.registrar_conector("falso", _ConectorDePrueba, formato_por_defecto="x")


def test_un_nombre_vacio_no_se_registra() -> None:
    with pytest.raises(ValueError, match="vacio"):
        RegistroSIEM().registrar_formato("  ", _FormatoDePrueba)


def test_el_contexto_no_muestra_el_entorno_en_el_repr() -> None:
    contexto = ContextoConector(entorno={"SIEM_SPLUNK_TOKEN": "no-debe-verse"})

    assert "no-debe-verse" not in repr(contexto)


# --- lo que trae IronVeil -----------------------------------------------------


def test_el_registro_incluido_conoce_todos_los_siem_anunciados() -> None:
    registro = construir_registro()

    assert set(registro.esquemas()) == {
        "archivo",
        "syslog+udp",
        "syslog+tcp",
        "syslog+tls",
        "https",
        "splunk",
        "elastic",
        "azure-logs",
        "aws-cloudwatch",
    }
    assert set(registro.formatos()) == {"json", "cef", "leef", "ecs"}


def test_el_archivo_usa_json_y_syslog_usa_cef_por_defecto(tmp_path: Path) -> None:
    registro = construir_registro()

    assert registro.resolver(f"archivo://{tmp_path / 'a.jsonl'}", {}).descripcion == (
        "json@archivo"
    )
    assert registro.resolver("syslog+udp://127.0.0.1:514", {}).descripcion == (
        "cef@syslog+udp"
    )


def test_solo_los_transportes_de_red_se_marcan_como_de_red(tmp_path: Path) -> None:
    registro = construir_registro()

    assert not registro.resolver(f"archivo://{tmp_path / 'a'}", {}).de_red
    assert registro.resolver("syslog+tcp://127.0.0.1:514", {}).de_red


# --- complementos de terceros -------------------------------------------------


def test_un_modulo_de_terceros_agrega_su_siem_sin_tocar_ironveil(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modulo = types.ModuleType("siem_de_prueba_mi_empresa")

    def registrar(registro: RegistroSIEM) -> None:
        registro.registrar_formato("mio", _FormatoDePrueba)
        registro.registrar_conector(
            "datadog", _ConectorDePrueba, formato_por_defecto="mio"
        )

    modulo.registrar = registrar  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "siem_de_prueba_mi_empresa", modulo)

    resuelto = construir_registro(("siem_de_prueba_mi_empresa",)).resolver(
        "datadog://api", {}
    )

    assert resuelto.descripcion == "mio@datadog"


@pytest.mark.parametrize("nombre", ["../x", "os; import sys", "a b", "1modulo"])
def test_solo_se_aceptan_nombres_de_modulo(nombre: str) -> None:
    with pytest.raises(ErrorSIEM, match="nombre de modulo"):
        construir_registro((nombre,))


def test_un_modulo_inexistente_dice_cual_es() -> None:
    with pytest.raises(ErrorSIEM, match="modulo_que_no_existe_siem"):
        construir_registro(("modulo_que_no_existe_siem",))


def test_un_modulo_sin_registrar_se_rechaza(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "siem_sin_enganche", types.ModuleType("x"))

    with pytest.raises(ErrorSIEM, match="registrar"):
        construir_registro(("siem_sin_enganche",))


# --- configuracion ------------------------------------------------------------


def test_sin_variables_no_hay_destinos() -> None:
    assert Configuracion.desde_entorno({}).destinos == ()


def test_siem_destinos_se_separa_por_comas_e_ignora_vacios() -> None:
    config = Configuracion.desde_entorno(
        {"SIEM_DESTINOS": " cef@syslog+tcp://a:1 , ,json@archivo:///x "}
    )

    assert config.destinos == ("cef@syslog+tcp://a:1", "json@archivo:///x")


def test_la_variable_historica_equivale_a_un_destino_de_archivo() -> None:
    config = Configuracion.desde_entorno({"SIEM_ARCHIVO_WAZUH": "/app/siem/w.json"})

    assert config.destinos == ("json@archivo:///app/siem/w.json",)


def test_la_variable_historica_se_suma_a_los_destinos_nuevos() -> None:
    config = Configuracion.desde_entorno(
        {"SIEM_ARCHIVO_WAZUH": "/w.json", "SIEM_DESTINOS": "cef@syslog+udp://a"}
    )

    assert config.destinos == ("json@archivo:///w.json", "cef@syslog+udp://a")


def test_el_entorno_solo_lleva_variables_del_siem_y_de_aws() -> None:
    config = Configuracion.desde_entorno(
        {
            "SIEM_SPLUNK_TOKEN": "t",
            "AWS_ACCESS_KEY_ID": "k",
            "PATH": "/bin",
            "OLLAMA_URL": "http://ollama",
        }
    )

    assert dict(config.entorno) == {"SIEM_SPLUNK_TOKEN": "t", "AWS_ACCESS_KEY_ID": "k"}


def test_la_configuracion_nunca_muestra_las_claves_en_el_repr() -> None:
    config = Configuracion.desde_entorno({"SIEM_SPLUNK_TOKEN": "no-debe-verse"})

    assert "no-debe-verse" not in repr(config)


def test_cambiar_una_clave_cuenta_como_otra_configuracion() -> None:
    una = Configuracion.desde_entorno({"SIEM_SPLUNK_TOKEN": "a"})
    otra = Configuracion.desde_entorno({"SIEM_SPLUNK_TOKEN": "b"})

    assert una != otra


# --- construir: un destino malo no tumba a los demas ---------------------------


def test_un_destino_mal_configurado_se_omite_y_los_demas_siguen(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = Configuracion(
        destinos=("splunk://host:8088", f"json@archivo://{tmp_path / 'ok.jsonl'}")
    )

    with caplog.at_level("ERROR"):
        exportador = construir(config)

    assert exportador.descripcion == "json@archivo"
    assert "SIEM_SPLUNK_TOKEN" in caplog.text  # dice QUE falta, nunca su valor


def test_un_complemento_roto_deja_los_adaptadores_incluidos(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = Configuracion(
        destinos=(f"json@archivo://{tmp_path / 'ok.jsonl'}",),
        adaptadores=("modulo_que_no_existe_siem",),
    )

    with caplog.at_level("ERROR"):
        exportador = construir(config)

    assert exportador.descripcion == "json@archivo"
    assert "modulo_que_no_existe_siem" in caplog.text

"""El ciclo de vida de la exportacion: de las variables de entorno a los destinos."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from proxy.siem import composicion
from proxy.siem.exportador import Destino, ExportadorSIEM
from proxy.siem.puertos import ErrorSIEM

EVENTO: dict[str, Any] = {
    "timestamp": "2026-10-06T14:32:11-05:00",
    "configuracion": "C1",
    "mecanismos_activos": ["filtrado"],
    "vector_probado": "V3-A",
    "modelo_destino": "soporte",
    "resultado": "bloqueado",
    "mecanismo_que_bloqueo": "filtrado",
    "latencia_ms": 12,
}


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for variable in ("SIEM_DESTINOS", "SIEM_ARCHIVO_WAZUH", "SIEM_ADAPTADORES"):
        monkeypatch.delenv(variable, raising=False)
    composicion.cerrar()
    yield
    composicion.cerrar()


def _lineas(ruta: Path) -> list[str]:
    return ruta.read_text(encoding="utf-8").splitlines()


def test_sin_destinos_la_exportacion_esta_apagada() -> None:
    assert composicion.obtener() is None
    composicion.exportar_evento(EVENTO)  # no hace nada y no falla


def test_cada_destino_recibe_el_evento_en_su_propio_formato(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    en_json, en_cef = tmp_path / "a.jsonl", tmp_path / "b.log"
    monkeypatch.setenv(
        "SIEM_DESTINOS", f"json@archivo://{en_json},cef@archivo://{en_cef}"
    )

    composicion.exportar_evento(EVENTO)

    assert json.loads(_lineas(en_json)[0])["vector_probado"] == "V3-A"
    assert _lineas(en_cef)[0].startswith("CEF:0|IronVeil|")


def test_un_destino_caido_no_impide_que_los_demas_reciban(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bloqueo = tmp_path / "es_un_archivo"
    bloqueo.write_text("x", encoding="utf-8")
    sano = tmp_path / "sano.jsonl"
    monkeypatch.setenv(
        "SIEM_DESTINOS", f"json@archivo://{bloqueo / 'x.json'},json@archivo://{sano}"
    )

    with caplog.at_level("ERROR"):
        composicion.exportar_evento(EVENTO)

    assert len(_lineas(sano)) == 1
    assert "exportacion a SIEM fallida" in caplog.text
    assert "bloqueado" not in caplog.text  # el contenido del evento no se vuelca


def test_la_variable_historica_sigue_funcionando(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archivo = tmp_path / "wazuh.json"
    monkeypatch.setenv("SIEM_ARCHIVO_WAZUH", str(archivo))

    composicion.exportar_evento(EVENTO)

    assert json.loads(_lineas(archivo)[0])["integration"] == "ironveil"


def test_con_la_misma_configuracion_se_reutiliza_el_exportador(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SIEM_ARCHIVO_WAZUH", str(tmp_path / "w.json"))

    assert composicion.obtener() is composicion.obtener()


def test_cambiar_el_entorno_reconstruye_los_destinos_y_cierra_los_viejos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SIEM_ARCHIVO_WAZUH", str(tmp_path / "uno.json"))
    primero = composicion.obtener()

    monkeypatch.setenv("SIEM_ARCHIVO_WAZUH", str(tmp_path / "dos.json"))
    segundo = composicion.obtener()

    assert segundo is not primero
    composicion.exportar_evento(EVENTO)
    assert not (tmp_path / "uno.json").exists()
    assert (tmp_path / "dos.json").exists()


def test_quitar_las_variables_apaga_la_exportacion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SIEM_ARCHIVO_WAZUH", str(tmp_path / "w.json"))
    assert composicion.obtener() is not None

    monkeypatch.delenv("SIEM_ARCHIVO_WAZUH")

    assert composicion.obtener() is None


def test_un_destino_de_red_se_entrega_en_un_hilo_aparte_y_cerrar_lo_vacia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Colector:
        recibidos: list[str] = []

        def __init__(self, destino: str, contexto: object) -> None:
            pass

        def enviar(self, mensaje: str) -> None:
            Colector.recibidos.append(mensaje)

    registro = composicion.construir_registro()
    registro.registrar_conector(
        "colector", Colector, formato_por_defecto="json", de_red=True
    )
    monkeypatch.setattr(composicion, "construir_registro", lambda *a, **k: registro)
    monkeypatch.setenv("SIEM_DESTINOS", "colector://donde-sea")

    composicion.exportar_evento(EVENTO)
    composicion.cerrar()  # entrega lo pendiente antes de volver

    assert len(Colector.recibidos) == 1
    assert json.loads(Colector.recibidos[0])["resultado"] == "bloqueado"


# --- el servicio, aislado ------------------------------------------------------


class _Conector:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.enviados: list[str] = []
        self.cerrado = False

    def enviar(self, mensaje: str) -> None:
        if self.error:
            raise self.error
        self.enviados.append(mensaje)

    def cerrar(self) -> None:
        self.cerrado = True


class _Formato:
    def formatear(self, evento: dict[str, Any]) -> str:
        return "m"


def test_el_exportador_nunca_lanza_aunque_un_conector_ajeno_falle(
    caplog: pytest.LogCaptureFixture,
) -> None:
    roto = _Conector(RuntimeError("explota"))
    sano = _Conector()
    exportador = ExportadorSIEM(
        [Destino("a@x", _Formato(), roto), Destino("b@y", _Formato(), sano)]
    )

    with caplog.at_level("ERROR"):
        exportador.exportar(EVENTO)

    assert sano.enviados == ["m"]
    assert "a@x" in caplog.text


def test_el_exportador_cierra_todos_aunque_uno_falle_al_cerrar() -> None:
    class CierraMal(_Conector):
        def cerrar(self) -> None:
            raise ErrorSIEM("no cierra")

    primero, ultimo = CierraMal(), _Conector()
    exportador = ExportadorSIEM(
        [Destino("a@x", _Formato(), primero), Destino("b@y", _Formato(), ultimo)]
    )

    exportador.cerrar()

    assert ultimo.cerrado


def test_la_descripcion_no_lleva_hosts_ni_claves() -> None:
    exportador = ExportadorSIEM([Destino("cef@syslog+tls", _Formato(), _Conector())])

    assert exportador.descripcion == "cef@syslog+tls"
    assert ExportadorSIEM([]).descripcion == "ninguno"

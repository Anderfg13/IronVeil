"""Medicion del costo propio por mecanismo: carga de medicion y resumen.

`ataques/medir_costo_mecanismos.py` genera trafico legitimo; el proxy registra el
tiempo de cada pieza; `analisis/costo_por_mecanismo.py` lo resume. Nada de esto
necesita el stack: el proxy y Ollama se reemplazan por dobles.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pytest

import analisis.costo_por_mecanismo as costo
import ataques.medir_costo_mecanismos as carga
import ataques.vectores_1_2_3 as vectores
import proxy.mecanismos as mecanismos

# --- La carga de medicion ------------------------------------------------------


def test_el_plan_pone_calentamiento_luego_legitimas_y_al_final_bloqueos() -> None:
    plan = carga.construir_plan(n_legitimas=5, n_bloqueos=2, n_calentamiento=3)

    assert [i.tipo for i in plan] == ["calentamiento"] * 3 + ["legitima"] * 5 + [
        "bloqueo"
    ] * 2
    assert all(i.vector == carga.VECTOR_CALENTAMIENTO for i in plan[:3])
    assert all(i.vector is None for i in plan[3:])  # trafico normal: sin vector


def test_el_plan_recorre_los_mensajes_en_ciclo_y_es_determinista() -> None:
    n = len(carga.PROMPTS_LEGITIMOS)

    plan = carga.construir_plan(n_legitimas=n + 2, n_calentamiento=0)

    assert plan == carga.construir_plan(n_legitimas=n + 2, n_calentamiento=0)
    assert plan[n].mensaje == plan[0].mensaje  # vuelve a empezar


def test_no_se_aceptan_cantidades_negativas() -> None:
    with pytest.raises(ValueError):
        carga.construir_plan(n_legitimas=-1)


def test_hay_mensajes_cortos_medianos_y_largos() -> None:
    largos = sorted(len(p) for p in carga.PROMPTS_LEGITIMOS)

    assert len(carga.PROMPTS_LEGITIMOS) == 12
    assert largos[0] < 120  # cortos
    assert largos[-1] > 2000  # largos
    assert any(300 <= x <= 1000 for x in largos)  # medianos


def test_los_mensajes_legitimos_no_los_retiene_ningun_mecanismo_por_patron() -> None:
    """Si uno 'legitimo' se retuviera, no mediria el costo de toda la cadena."""
    for texto in carga.PROMPTS_LEGITIMOS:
        assert mecanismos.filtrar(texto, "entrada")[1] is False
        assert mecanismos.validar_privilegio("soporte", texto) is False


def test_los_casos_de_bloqueo_hacen_lo_que_dicen() -> None:
    es, en, credencial, otro_idioma = carga.CASOS_DE_BLOQUEO

    assert mecanismos.filtrar(es, "entrada")[1] is True
    assert mecanismos.filtrar(en, "entrada")[1] is True
    assert mecanismos.validar_privilegio("soporte", credencial) is True
    # el de otro idioma pasa el filtro: queda para la clasificacion
    assert mecanismos.filtrar(otro_idioma, "entrada")[1] is False


def test_los_mensajes_no_llevan_las_credenciales_reales_del_proyecto() -> None:
    """CLAUDE.md, regla 2: los canarios viven en .env/Modelfiles, no en el codigo."""
    todo = " ".join((*carga.PROMPTS_LEGITIMOS, *carga.CASOS_DE_BLOQUEO))

    assert "SPT-DEMO-8841" not in todo
    assert "RRHH-DEMO-2291" not in todo


class _Resp:
    def __init__(self, estado: int) -> None:
        self.status_code = estado


def test_ejecutar_envia_cada_intento_y_guarda_un_resumen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    enviados: list[dict[str, Any]] = []

    def post(url: str, **kwargs: Any) -> _Resp:
        enviados.append({"url": url, **kwargs["json"]})
        return _Resp(429 if "RRHH-DEMO" in kwargs["json"]["mensaje"] else 200)

    monkeypatch.setattr(carga.httpx, "post", post)
    plan = carga.construir_plan(2, 3, 1)
    salida = tmp_path / "s.jsonl"

    conteo = carga.ejecutar(plan, "http://localhost:8000/", "soporte", "C1", salida)

    assert len(enviados) == 6
    assert enviados[0]["url"] == "http://localhost:8000/chat"
    assert enviados[0]["vector_probado"] == "CALENTAMIENTO"
    assert enviados[1]["vector_probado"] is None
    assert conteo == {"200": 5, "429": 1}
    lineas = [json.loads(x) for x in salida.read_text(encoding="utf-8").splitlines()]
    assert [x["tipo"] for x in lineas][:2] == ["calentamiento", "legitima"]
    assert all(x["configuracion"] == "C1" for x in lineas)


def test_un_error_de_red_se_registra_y_no_detiene_la_carga(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def post(url: str, **kwargs: Any) -> _Resp:
        raise httpx.ConnectError("sin red (de prueba)")

    monkeypatch.setattr(carga.httpx, "post", post)

    conteo = carga.ejecutar(
        carga.construir_plan(2, 0, 0),
        "http://localhost:8000",
        "soporte",
        "C0",
        tmp_path / "s.jsonl",
    )

    assert conteo == {"sin_respuesta": 2}


def test_la_pausa_entre_envios_se_aplica(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pausas: list[float] = []
    monkeypatch.setattr(carga.time, "sleep", pausas.append)
    monkeypatch.setattr(carga, "enviar", lambda *a, **k: (200, 5, None))

    carga.ejecutar(
        carga.construir_plan(3, 0, 0),
        "http://localhost:8000",
        "soporte",
        "C5",
        tmp_path / "s.jsonl",
        pausa_s=7.0,
    )

    assert pausas == [7.0, 7.0, 7.0]


def test_solo_acepta_el_laboratorio_propio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regla 1 de CLAUDE.md: nunca contra un host que no sea del equipo."""
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(f"{k}: false" for k in mecanismos.FLAGS_REQUERIDAS), encoding="utf-8"
    )
    monkeypatch.setattr(vectores, "validar_ruta_salida_segura", lambda r, **k: r)

    with pytest.raises(ValueError, match="laboratorio"):
        carga.main(
            [
                "--configuracion",
                "C0",
                "--url-proxy",
                "http://un-servidor-ajeno.example.com:8000",
                "--config-path",
                str(config),
                "--salida",
                str(tmp_path / "s.jsonl"),
            ]
        )


def test_main_rechaza_una_configuracion_que_no_coincide_con_config_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(f"{k}: false" for k in mecanismos.FLAGS_REQUERIDAS), encoding="utf-8"
    )
    monkeypatch.setattr(vectores, "validar_ruta_salida_segura", lambda r, **k: r)

    with pytest.raises(ValueError):
        carga.main(
            [
                "--configuracion",
                "C6",  # config.yaml dice C0
                "--config-path",
                str(config),
                "--salida",
                str(tmp_path / "s.jsonl"),
            ]
        )


# --- El resumen ----------------------------------------------------------------


def _evento(
    configuracion: str,
    total_ms: int,
    modelo_us: int | None,
    *,
    resultado: str = "permitido_normal",
    bloqueo: str | None = None,
    vector: str | None = None,
    segundos: int = 0,
    **piezas_us: int,
) -> dict[str, Any]:
    evento: dict[str, Any] = {
        "timestamp": f"2026-10-05T12:00:{segundos:02d}-05:00",
        "configuracion": configuracion,
        "mecanismos_activos": [],
        "vector_probado": vector,
        "modelo_destino": "soporte",
        "resultado": resultado,
        "mecanismo_que_bloqueo": bloqueo,
        "latencia_ms": total_ms,
    }
    if modelo_us is not None:
        evento["latencia_modelo_us"] = modelo_us
    evento.update({f"latencia_{k}_us": v for k, v in piezas_us.items()})
    return evento


def _escribir_jsonl(ruta: Path, eventos: list[dict[str, Any]]) -> Path:
    ruta.write_text("\n".join(json.dumps(e) for e in eventos) + "\n", encoding="utf-8")
    return ruta


def test_el_sobrecosto_propio_es_el_total_menos_el_modelo(tmp_path: Path) -> None:
    eventos = [
        _evento("C1", 100, 90_000, segundos=1, filtrado=10),
        _evento("C1", 110, 90_000, segundos=2, filtrado=20),
        _evento("C1", 120, 90_000, segundos=3, filtrado=30),
    ]
    df = costo.leer_eventos([_escribir_jsonl(tmp_path / "e.jsonl", eventos)])

    resumen = costo.resumen_legitimas(df)

    fila = resumen.iloc[0]
    assert fila["Configuración"] == "C1"
    assert fila["n"] == 3
    assert fila["Total, mediana (ms)"] == 110
    assert fila["Modelo, mediana (ms)"] == 90
    assert fila["Sobrecosto propio, mediana (ms)"] == 20  # 110 - 90
    assert fila["Filtrado (ms)"] == pytest.approx(0.020)
    assert fila["Suma de mecanismos, mediana (ms)"] == pytest.approx(0.020)


def test_un_mecanismo_que_no_corrio_queda_vacio_y_no_en_cero(tmp_path: Path) -> None:
    df = costo.leer_eventos(
        [
            _escribir_jsonl(
                tmp_path / "e.jsonl", [_evento("C1", 100, 90_000, filtrado=5)]
            )
        ]
    )

    fila = costo.resumen_legitimas(df).iloc[0]

    assert fila["Filtrado (ms)"] == pytest.approx(0.005)
    assert pd.isna(fila["Clasificación (ms)"])
    assert pd.isna(fila["Delimitación (ms)"])


def test_las_configuraciones_salen_en_orden(tmp_path: Path) -> None:
    eventos = [
        _evento("C6", 100, 50_000, segundos=1),
        _evento("C0", 100, 50_000, segundos=2),
        _evento("C3", 100, 50_000, segundos=3),
    ]
    df = costo.leer_eventos([_escribir_jsonl(tmp_path / "e.jsonl", eventos)])

    assert list(costo.resumen_legitimas(df)["Configuración"]) == ["C0", "C3", "C6"]


def test_solo_se_miden_peticiones_que_llegaron_al_modelo_sin_retener(
    tmp_path: Path,
) -> None:
    eventos = [
        _evento("C1", 100, 90_000, segundos=1),
        _evento("C1", 5, None, resultado="bloqueado", bloqueo="filtrado", segundos=2),
        _evento(
            "C1",
            300,
            250_000,
            resultado="bloqueado",
            bloqueo="clasificacion",
            segundos=3,
        ),
    ]
    df = costo.leer_eventos([_escribir_jsonl(tmp_path / "e.jsonl", eventos)])

    assert (
        costo.resumen_legitimas(df).iloc[0]["n"] == 1
    )  # la retenida a la salida no cuenta


def test_las_retenidas_se_resumen_aparte_porque_su_total_es_todo_costo_propio(
    tmp_path: Path,
) -> None:
    eventos = [
        _evento("C1", 4, None, resultado="bloqueado", bloqueo="filtrado", segundos=1),
        _evento("C1", 6, None, resultado="bloqueado", bloqueo="filtrado", segundos=2),
        _evento(
            "C3", 70, None, resultado="bloqueado", bloqueo="clasificacion", segundos=3
        ),
    ]
    df = costo.leer_eventos([_escribir_jsonl(tmp_path / "e.jsonl", eventos)])

    resumen = costo.resumen_retenidas(df)

    assert list(resumen["Retuvo"]) == ["filtrado", "clasificacion"]
    assert resumen.iloc[0]["n"] == 2
    assert resumen.iloc[0]["Total, mediana (ms)"] == 5


def test_se_ignoran_calentamiento_ataques_revision_humana_y_extension(
    tmp_path: Path,
) -> None:
    base = _evento("C1", 100, 90_000, segundos=1)
    eventos = [
        base,
        _evento("C1", 100, 90_000, vector="CALENTAMIENTO", segundos=2),
        _evento("C1", 100, 90_000, vector="V3-A", segundos=3),
        {**_evento("C1", 100, 90_000, segundos=4), "tiempo_revision_humana_ms": 1500},
        {**_evento("C1", 100, 90_000, segundos=5), "es_extension": True},
    ]

    df = costo.leer_eventos([_escribir_jsonl(tmp_path / "e.jsonl", eventos)])

    assert len(df) == 1


def test_desde_descarta_lo_anterior_a_la_marca(tmp_path: Path) -> None:
    eventos = [_evento("C1", 100, 90_000, segundos=s) for s in (10, 20, 30)]
    ruta = _escribir_jsonl(tmp_path / "e.jsonl", eventos)
    marca = datetime.fromisoformat("2026-10-05T12:00:15-05:00")

    assert len(costo.leer_eventos([ruta], desde=marca)) == 2


def test_lineas_ajenas_y_duplicados_no_rompen_ni_cuentan_doble(tmp_path: Path) -> None:
    evento = _evento("C1", 100, 90_000)
    ruta = tmp_path / "e.jsonl"
    ruta.write_text(
        "esto no es json con latencia_ms\n"
        + json.dumps(evento)
        + "\n"
        + json.dumps(evento)
        + "\n",
        encoding="utf-8",
    )

    assert len(costo.leer_eventos([ruta])) == 1


def test_sin_datos_no_se_inventa_nada(tmp_path: Path) -> None:
    vacio = costo.leer_eventos([_escribir_jsonl(tmp_path / "e.jsonl", [])])

    assert vacio.empty
    assert costo.resumen_legitimas(vacio).empty
    assert costo.resumen_retenidas(vacio).empty


def test_eventos_anteriores_a_la_instrumentacion_no_producen_tabla(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    viejo = _evento("C1", 100, None)  # sin latencia_*_us
    ruta = _escribir_jsonl(tmp_path / "e.jsonl", [viejo])

    costo.main(["--eventos", str(ruta), "--output-dir", str(tmp_path)])

    assert not (tmp_path / "costo_por_mecanismo.md").exists()
    assert "No se estima nada" in caplog.text


def test_main_escribe_csv_y_markdown_con_tres_decimales(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(costo, "validar_ruta_salida_segura", lambda r, **k: r)
    ruta = _escribir_jsonl(
        tmp_path / "e.jsonl",
        [_evento("C1", 100, 90_000, filtrado=8, segundos=1)],
    )

    costo.main(["--eventos", str(ruta), "--output-dir", str(tmp_path / "salida")])

    md = (tmp_path / "salida" / "costo_por_mecanismo.md").read_text(encoding="utf-8")
    assert "0.008" in md  # 8 microsegundos = 0.008 ms
    assert (tmp_path / "salida" / "costo_por_mecanismo.csv").exists()
    assert (tmp_path / "salida" / "costo_por_mecanismo_retenidas.md").exists()
    assert "costo_por_mecanismo" in capsys.readouterr().out


def test_la_ruta_de_salida_no_puede_salir_del_repositorio(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        costo._escribir(pd.DataFrame({"a": [1]}), tmp_path / "fuera", "x")

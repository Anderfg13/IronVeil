"""El resumen de las corridas de Garak (sin Docker ni Garak: informes sinteticos)."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "analisis"))

import resumen_garak as rg  # noqa: E402


def _informe(
    carpeta: Path, evals: list[tuple[str, int, int, int]], estados: list[str]
) -> None:
    """Una carpeta de configuracion: (probe, fails, evaluados, nones) y los estados."""
    carpeta.mkdir(parents=True)
    lineas = [json.dumps({"entry_type": "attempt", "uuid": "x"})]
    for probe, fallos, evaluados, nones in evals:
        lineas.append(
            json.dumps(
                {
                    "entry_type": "eval",
                    "probe": probe,
                    "detector": "d",
                    "passed": evaluados - fallos,
                    "fails": fallos,
                    "nones": nones,
                    "total_evaluated": evaluados,
                }
            )
        )
    (carpeta / "garak.report.jsonl").write_text(
        "\n".join(lineas) + "\n", encoding="utf-8"
    )
    (carpeta / "estados.jsonl").write_text(
        "".join(json.dumps({"estado": e}) + "\n" for e in estados), encoding="utf-8"
    )


@pytest.fixture
def corrida(tmp_path: Path) -> Path:
    _informe(
        tmp_path / "C0", [("a.uno", 6, 30, 0), ("a.dos", 3, 30, 0)], ["respondido"] * 60
    )
    _informe(
        tmp_path / "C1",
        [("a.uno", 0, 30, 0), ("a.dos", 3, 30, 2)],
        ["bloqueado"] * 40 + ["respondido"] * 18 + ["http_502"] * 2,
    )
    return tmp_path


def test_el_intervalo_de_wilson_contiene_a_la_proporcion_y_se_estrecha() -> None:
    bajo, alto = rg.intervalo_wilson(6, 30)
    estrecho_bajo, estrecho_alto = rg.intervalo_wilson(60, 300)

    assert bajo < 6 / 30 < alto
    assert (estrecho_alto - estrecho_bajo) < (alto - bajo)


def test_con_cero_exitos_el_limite_inferior_es_cero_y_el_superior_no() -> None:
    bajo, alto = rg.intervalo_wilson(0, 30)

    assert bajo == 0.0
    assert 0 < alto < 0.2  # "0 de 30" no demuestra que el riesgo sea 0


def test_sin_datos_el_intervalo_no_inventa_nada() -> None:
    assert all(math.isnan(x) for x in rg.intervalo_wilson(0, 0))


def test_se_leen_las_configuraciones_en_orden_canonico(corrida: Path) -> None:
    filas, estados = rg.cargar(corrida)

    assert [f.configuracion for f in filas] == ["C0", "C0", "C1", "C1"]
    assert estados["C1"] == {"bloqueado": 40, "respondido": 18, "http_502": 2}


def test_los_totales_suman_los_probes_de_cada_configuracion(corrida: Path) -> None:
    filas, _ = rg.cargar(corrida)

    assert rg.totales(filas) == {"C0": (9, 60, 0), "C1": (3, 60, 2)}


def test_el_markdown_dice_los_limites_y_marca_lo_que_no_es_oficial(
    corrida: Path,
) -> None:
    filas, estados = rg.cargar(corrida)

    texto = rg.construir_markdown(filas, estados, corrida)

    assert "| C0 | 60 | 9 | 15.0 %" in texto
    assert "| C1 | 60 | 3 | 5.0 %" in texto
    assert "no entra en las tablas del núcleo" in texto.lower()
    assert "no es la C6 oficial" in texto
    assert "se solapan" in texto


def test_sin_informes_el_script_avisa_y_falla(tmp_path: Path) -> None:
    assert rg.main(["--entrada", str(tmp_path), "--salida", str(tmp_path / "s")]) == 1


def test_el_csv_lleva_una_fila_por_probe_y_configuracion(
    corrida: Path, tmp_path: Path
) -> None:
    filas, _ = rg.cargar(corrida)
    destino = tmp_path / "salida.csv"

    rg.escribir_csv(filas, destino)

    assert len(destino.read_text(encoding="utf-8").splitlines()) == 1 + 4


# --- bloqueos reales vs fallo cerrado, y credenciales ---------------------------------


def _evento(
    activos: list[str],
    resultado: str,
    entrada: str | None = None,
    salida: str | None = None,
    vector: str = "GARAK",
) -> dict[str, object]:
    evento: dict[str, object] = {
        "vector_probado": vector,
        "mecanismos_activos": activos,
        "resultado": resultado,
    }
    if entrada:
        evento["clasificador_entrada"] = {"estado": entrada}
    if salida:
        evento["clasificador_salida"] = {"estado": salida}
    return evento


def test_cada_configuracion_se_reconoce_por_sus_mecanismos_activos() -> None:
    cuatro = ["filtrado", "delimitacion", "clasificacion", "minimo_privilegio"]

    assert rg.CONFIGURACION_POR_MECANISMOS[frozenset()] == "C0"
    assert rg.CONFIGURACION_POR_MECANISMOS[frozenset(cuatro)] == "C6sinH"


def test_un_timeout_del_clasificador_es_fallo_cerrado_y_no_deteccion() -> None:
    eventos = [
        _evento(["clasificacion"], "bloqueado", entrada="ok"),  # deteccion real
        _evento(["clasificacion"], "bloqueado", entrada="ok", salida="timeout"),
        _evento(["clasificacion"], "bloqueado", entrada="error_red"),
        _evento(["clasificacion"], "permitido_normal", entrada="ok"),  # no bloquea
    ]

    bloqueos = rg.clasificar_bloqueos(eventos)

    assert bloqueos["C3"] == rg.Bloqueos(detecciones=1, fallo_cerrado=2)
    assert bloqueos["C3"].total == 3


def test_un_bloqueo_del_filtro_es_deteccion_porque_no_usa_clasificador() -> None:
    bloqueos = rg.clasificar_bloqueos([_evento(["filtrado"], "bloqueado")])

    assert bloqueos["C1"] == rg.Bloqueos(detecciones=1, fallo_cerrado=0)


def test_se_ignoran_los_eventos_que_no_son_de_garak(tmp_path: Path) -> None:
    carpeta = tmp_path / "eventos_proxy" / "2026-10-07"
    carpeta.mkdir(parents=True)
    (carpeta / "eventos.jsonl").write_text(
        json.dumps(_evento([], "permitido_normal", vector="V3-A"))
        + "\n"
        + json.dumps(_evento([], "permitido_normal"))
        + "\n",
        encoding="utf-8",
    )

    assert len(rg.leer_eventos(tmp_path)) == 1


def test_el_markdown_advierte_que_el_asr_esta_inflado_si_hubo_fallo_cerrado(
    corrida: Path,
) -> None:
    filas, estados = rg.cargar(corrida)
    bloqueos = {"C1": rg.Bloqueos(detecciones=10, fallo_cerrado=5)}

    texto = rg.construir_markdown(filas, estados, corrida, bloqueos)

    assert "inflado a la baja" in texto
    assert "| C1 | 15 | 10 | 5 |" in texto
    assert rg.configuraciones_infladas(bloqueos) == ["C1"]


def test_sin_fallo_cerrado_no_hay_advertencia(corrida: Path) -> None:
    filas, estados = rg.cargar(corrida)
    bloqueos = {"C1": rg.Bloqueos(detecciones=15)}

    texto = rg.construir_markdown(filas, estados, corrida, bloqueos)

    assert "inflado" not in texto
    assert rg.configuraciones_infladas(bloqueos) == []


def test_sin_eventos_el_informe_sigue_funcionando_y_omite_esas_secciones(
    corrida: Path,
) -> None:
    filas, estados = rg.cargar(corrida)

    texto = rg.construir_markdown(filas, estados, corrida)

    assert "Bloqueos del proxy" not in texto
    assert "Credenciales en las respuestas" not in texto


def _intento(textos: list[str | None], estado: int = 2) -> str:
    return json.dumps(
        {
            "entry_type": "attempt",
            "status": estado,
            "outputs": [None if x is None else {"text": x} for x in textos],
        }
    )


def test_se_cuentan_las_credenciales_sin_redactar_y_las_redactadas(
    tmp_path: Path,
) -> None:
    # Credenciales de prueba con el formato del filtro (no son los canarios reales).
    fuga = "la clave es PRUEBA-DEMO-0001"
    carpeta = tmp_path / "C0"
    carpeta.mkdir()
    (carpeta / "garak.report.jsonl").write_text(
        "\n".join(
            [
                _intento(["hola", fuga]),
                _intento(["[REDACTADO] es la clave"]),
                _intento([None, ""]),  # sin salida: no es una respuesta
                _intento(["incompleto " + fuga], estado=1),  # intento sin evaluar
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cuenta = rg.contar_credenciales(tmp_path)

    assert cuenta["C0"] == rg.Credenciales(respuestas=3, sin_redactar=1, redactadas=1)


def test_el_markdown_incluye_la_tabla_de_credenciales(corrida: Path) -> None:
    filas, estados = rg.cargar(corrida)
    credenciales = {
        "C0": rg.Credenciales(338, 13, 0),
        "C1": rg.Credenciales(339, 0, 15),
    }

    texto = rg.construir_markdown(filas, estados, corrida, None, credenciales)

    assert "| C0 | 338 | 13 | 0 |" in texto
    assert "| C1 | 339 | 0 | 15 |" in texto


# --- Fisher exacto y comparacion contra C0 ------------------------------------------


def test_fisher_coincide_con_el_valor_exacto_conocido() -> None:
    # 3/3 contra 0/3: unica tabla igual de extrema por cada lado = 2 / C(6,3) = 0.1
    assert rg.fisher_exacto(3, 3, 0, 3) == pytest.approx(0.1)


def test_fisher_de_dos_proporciones_iguales_es_uno() -> None:
    assert rg.fisher_exacto(6, 30, 6, 30) == pytest.approx(1.0)


def test_fisher_es_simetrico() -> None:
    assert rg.fisher_exacto(16, 30, 7, 30) == pytest.approx(
        rg.fisher_exacto(7, 30, 16, 30)
    )


def test_fisher_reproduce_el_valor_de_la_corrida_real_de_latentinjection() -> None:
    # C0 16/30 contra C2 7/30 (el valor que se uso para opinar sobre la delimitacion)
    assert rg.fisher_exacto(16, 30, 7, 30) == pytest.approx(0.033, abs=0.001)


def test_la_comparacion_solo_usa_los_probes_donde_c0_cae(corrida: Path) -> None:
    filas, estados = rg.cargar(corrida)

    texto = rg.construir_markdown(filas, estados, corrida)

    assert "Cada defensa contra C0" in texto
    assert "`a.uno`" in texto.split("Cada defensa contra C0")[1]
    assert "comparaciones" in texto
    assert "Bonferroni" in texto


def test_no_se_compara_una_configuracion_inflada_por_fallo_de_servicio(
    corrida: Path,
) -> None:
    filas, estados = rg.cargar(corrida)
    bloqueos = {"C1": rg.Bloqueos(detecciones=1, fallo_cerrado=1)}

    texto = rg.construir_markdown(filas, estados, corrida, bloqueos)

    assert "Cada defensa contra C0" not in texto  # C1 era la unica otra configuracion

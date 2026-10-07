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

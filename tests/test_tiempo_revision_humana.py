"""Pruebas de analisis/tiempo_revision_humana.py (lectura de decisiones del log)."""

from __future__ import annotations

import json
from pathlib import Path

from analisis.tiempo_revision_humana import cargar_decisiones_humanas


def _evento(timestamp: str, mecanismo: str | None, tiempo: int | None) -> str:
    evento: dict[str, object] = {
        "timestamp": timestamp,
        "configuracion": "C5",
        "modelo_destino": "soporte",
        "mecanismo_que_bloqueo": mecanismo,
    }
    if tiempo is not None:
        evento["tiempo_revision_humana_ms"] = tiempo
    return json.dumps(evento)


def test_lee_decisiones_de_todas_las_fechas_y_deduplica(tmp_path: Path) -> None:
    dia1, dia2 = tmp_path / "2026-09-20", tmp_path / "2026-09-25"
    dia1.mkdir()
    dia2.mkdir()
    rechazo = _evento("2026-09-20T10:00:00", "aprobacion_humana", 4000)
    encolado = _evento("2026-09-20T09:59:00", "aprobacion_humana", None)
    aprobacion = _evento("2026-09-25T11:00:00", None, 9000)
    (dia1 / "eventos.jsonl").write_text(f"{encolado}\n{rechazo}\n", encoding="utf-8")
    (dia2 / "eventos.jsonl").write_text(f"{aprobacion}\n{rechazo}\n", encoding="utf-8")

    decisiones, archivos = cargar_decisiones_humanas(tmp_path)

    assert archivos == 2
    assert len(decisiones) == 2  # el rechazo copiado en dos archivos cuenta una vez
    assert sorted(decisiones["decision"]) == ["aprobada", "rechazada"]


def test_sin_decisiones_devuelve_tabla_vacia(tmp_path: Path) -> None:
    encolado = _evento("2026-09-22T00:00:00", "aprobacion_humana", None)
    (tmp_path / "eventos.jsonl").write_text(encolado, encoding="utf-8")

    decisiones, archivos = cargar_decisiones_humanas(tmp_path)

    assert archivos == 1
    assert decisiones.empty

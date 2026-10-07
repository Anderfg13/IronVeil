"""Medicion del clasificador de entrada: resumen, fallos aparte y preparacion."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ataques import medir_clasificador_entrada as m
from ataques.corpus_multilingue import IDIOMAS as IDIOMAS_ESPERADOS


@dataclass
class _Detalle:
    estado: str = "ok"
    puntaje: float | None = None


def _muestra(id_, clase, ms, malicioso, puntaje=None, estado="ok"):
    return m.Muestra(id_, clase, ms, estado, malicioso, puntaje)


def test_los_casos_cubren_ataques_y_legitimas() -> None:
    clases = [caso.clase for caso in m.casos()]
    assert clases.count(m.CLASE_ATAQUE) == len(m.ATAQUES)
    assert clases.count(m.CLASE_LEGITIMA) > len(m.ATAQUES)
    ids = [caso.id for caso in m.casos()]
    assert len(ids) == len(set(ids))
    assert {caso.idioma for caso in m.casos()} == {m.IDIOMA_BASE}


def test_percentil_por_rango_mas_cercano() -> None:
    assert m.percentil([], 0.5) == 0.0
    assert m.percentil([10, 20, 30, 40], 0.5) == 20
    assert m.percentil([10, 20, 30, 40], 0.95) == 40


def test_medir_registra_estado_puntaje_y_latencia() -> None:
    respuestas = {
        "a": (True, _Detalle("ok", 0.9)),
        "b": (True, _Detalle("timeout")),
    }
    relojes = iter([0.0, 0.25, 1.0, 1.5])
    muestras = m.medir(
        lambda texto: respuestas[texto],
        [("A", m.CLASE_ATAQUE, "a"), ("B", m.CLASE_LEGITIMA, "b")],
        reloj=lambda: next(relojes),
    )
    assert [x.id for x in muestras] == ["A", "B"]
    assert muestras[0].latencia_ms == pytest.approx(250)
    assert muestras[0].valida and muestras[0].puntaje == 0.9
    assert not muestras[1].valida and muestras[1].estado == "timeout"


def test_medir_repite_y_hace_pausa_entre_envios() -> None:
    pausas: list[float] = []
    muestras = m.medir(
        lambda _: (False, _Detalle()),
        [("A", m.CLASE_ATAQUE, "x")],
        repeticiones=3,
        pausa_s=0.5,
        dormir=pausas.append,
    )
    assert len(muestras) == 3 and pausas == [0.5, 0.5, 0.5]


def test_los_fallos_no_cuentan_como_deteccion() -> None:
    """Un timeout es 'malicioso' (fail closed) pero no debe inflar la deteccion."""
    informe = m.resumir(
        [
            _muestra("V3-A", m.CLASE_ATAQUE, 100, True, 0.95),
            _muestra("V3-B", m.CLASE_ATAQUE, 100, False, 0.10),
            _muestra("V3-C", m.CLASE_ATAQUE, 9000, True, None, "timeout"),
            _muestra("L-01", m.CLASE_LEGITIMA, 80, False, 0.02),
        ]
    )
    assert "1/2 = 50%" in informe  # solo los 2 ataques que contestaron
    assert "`timeout`: 1" in informe
    assert "3 contestaron** y **1 fallaron" in informe


def test_resumen_cuenta_falsos_positivos_y_latencia() -> None:
    informe = m.resumir(
        [
            _muestra("V3-A", m.CLASE_ATAQUE, 100, True, 0.95),
            _muestra("L-01", m.CLASE_LEGITIMA, 300, True, 0.70),
            _muestra("L-02", m.CLASE_LEGITIMA, 200, False, 0.05),
        ]
    )
    assert "Legitimas bloqueadas por error:** 1/2 = 50%" in informe
    assert "p50: 200" in informe and "maximo: 300" in informe


def test_barrido_de_umbral_marca_el_actual() -> None:
    informe = m.resumir(
        [
            _muestra("V3-A", m.CLASE_ATAQUE, 1, True, 0.55),
            _muestra("L-01", m.CLASE_LEGITIMA, 1, False, 0.35),
        ],
        umbral_actual=0.5,
    )
    assert "| 0.5 (actual) | 1/1 | 0/1 |" in informe
    assert "| 0.3 | 1/1 | 1/1 |" in informe
    assert "| 0.6 | 0/1 | 0/1 |" in informe


def test_sin_envios_validos_no_divide_por_cero() -> None:
    informe = m.resumir([_muestra("V3-A", m.CLASE_ATAQUE, 5, True, None, "timeout")])
    assert "n/a" in informe and "`timeout`: 1" in informe


def test_cargar_env_no_pisa_ni_imprime(tmp_path, monkeypatch, capsys) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# comentario\n\nFALSA_UNO=uno\nFALSA_DOS='dos'\nFALSA_VACIA=\n"
        "FALSA_TRES=tres\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("FALSA_UNO", raising=False)
    monkeypatch.delenv("FALSA_DOS", raising=False)
    monkeypatch.delenv("FALSA_VACIA", raising=False)
    monkeypatch.setenv("FALSA_TRES", "ya_definida")
    m.cargar_env(env)
    assert m.os.environ["FALSA_UNO"] == "uno"
    assert m.os.environ["FALSA_DOS"] == "dos"
    assert "FALSA_VACIA" not in m.os.environ
    assert m.os.environ["FALSA_TRES"] == "ya_definida"
    assert capsys.readouterr().out == ""
    for nombre in ("FALSA_UNO", "FALSA_DOS"):
        monkeypatch.delenv(nombre, raising=False)


def test_jev_sin_clave_o_sin_permiso_no_se_mide(monkeypatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("CLASIFICADOR_PERMITIR_REMOTO", raising=False)
    assert "TYPESAFE_API_KEY" in (m.problema_de_configuracion("jev") or "")
    monkeypatch.setenv("TYPESAFE_API_KEY", "clave-ficticia-de-prueba")
    assert "CLASIFICADOR_PERMITIR_REMOTO" in (m.problema_de_configuracion("jev") or "")
    monkeypatch.setenv("CLASIFICADOR_PERMITIR_REMOTO", "1")
    assert m.problema_de_configuracion("jev") is None


def test_otros_backends_no_exigen_la_clave_de_jev(monkeypatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert m.problema_de_configuracion("ollama") is None


def test_main_sin_configuracion_sale_con_2_y_no_llama_a_nadie(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setattr(m, "cargar_env", lambda _: None)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    salida = tmp_path / "informe.md"
    assert m.main(["--salida", str(salida)]) == 2
    assert not salida.exists()
    assert "TYPESAFE_API_KEY" in capsys.readouterr().err


def test_aborta_tras_fallos_seguidos_y_no_sigue_gastando() -> None:
    llamadas: list[str] = []

    def evaluar(texto: str):
        llamadas.append(texto)
        return True, _Detalle("error_http_401")

    entradas = [(f"A{i}", m.CLASE_ATAQUE, f"t{i}") for i in range(10)]
    muestras = m.medir(evaluar, entradas, abortar_tras_fallos=3)
    assert len(muestras) == len(llamadas) == 3


def test_un_exito_reinicia_la_cuenta_de_fallos() -> None:
    estados = iter(["timeout", "timeout", "ok", "timeout", "timeout", "ok"])
    muestras = m.medir(
        lambda _: (True, _Detalle(next(estados), 0.5)),
        [(f"A{i}", m.CLASE_ATAQUE, "x") for i in range(6)],
        abortar_tras_fallos=3,
    )
    assert len(muestras) == 6


def test_cada_envio_se_guarda_al_instante_sin_texto_ni_clave(tmp_path) -> None:
    crudo = tmp_path / "carpeta" / "crudo.jsonl"
    texto_secreto = "TEXTO-QUE-NO-DEBE-QUEDAR-EN-EL-ARCHIVO"
    detalle = _Detalle("ok", 0.8)
    detalle.backend, detalle.modelo, detalle.umbral = "jev", "jev-latest", 0.5
    m.medir(
        lambda _: (True, detalle),
        [("V3-A", m.CLASE_ATAQUE, texto_secreto)],
        repeticiones=2,
        al_medir=m.guardar_crudo(crudo),
    )
    contenido = crudo.read_text(encoding="utf-8")
    assert texto_secreto not in contenido
    registros = m.leer_lineas(crudo)
    assert len(registros) == 2
    assert registros[0]["modelo"] == "jev-latest" and registros[0]["umbral"] == 0.5
    assert registros[0]["caracteres"] == len(texto_secreto)
    assert registros[1]["repeticion"] == 2


def test_resumir_desde_el_crudo_no_llama_a_nadie(tmp_path, capsys) -> None:
    crudo = tmp_path / "crudo.jsonl"
    detalle = _Detalle("ok", 0.9)
    detalle.backend, detalle.modelo, detalle.umbral = "jev", "jev-latest", 0.5
    m.medir(
        lambda _: (True, detalle),
        [("V3-A", m.CLASE_ATAQUE, "x")],
        al_medir=m.guardar_crudo(crudo),
    )
    salida = tmp_path / "informe.md"
    assert m.main(["--resumir-desde", str(crudo), "--salida", str(salida)]) == 0
    informe = salida.read_text(encoding="utf-8")
    assert "1/1 = 100%" in informe and "| 0.5 (actual) |" in informe


def test_simular_cuenta_los_envios_sin_llamar(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(m, "cargar_env", lambda _: None)
    monkeypatch.setenv("TYPESAFE_API_KEY", "clave-ficticia-de-prueba")
    monkeypatch.setenv("CLASIFICADOR_PERMITIR_REMOTO", "1")
    llamado = []
    monkeypatch.setattr(m, "medir", lambda *a, **k: llamado.append(1))
    crudo = tmp_path / "no_debe_existir.jsonl"
    assert m.main(["--simular", "--repeticiones", "2", "--crudo", str(crudo)]) == 0
    esperado = len(m.casos()) * 2
    assert f"Se haran {esperado} envios" in capsys.readouterr().err
    assert not llamado and not crudo.exists()


def test_estabilidad_senala_textos_que_cambian_entre_repeticiones() -> None:
    informe = m.resumir(
        [
            _muestra("V3-A", m.CLASE_ATAQUE, 1, True, 0.90),
            _muestra("V3-A", m.CLASE_ATAQUE, 1, True, 0.60),
            _muestra("V3-B", m.CLASE_ATAQUE, 1, True, 0.80),
            _muestra("V3-B", m.CLASE_ATAQUE, 1, True, 0.80),
        ]
    )
    assert "1 de 2 textos repetidos cambiaron" in informe
    assert "V3-A: de 0.60 a 0.90 (2 envios)" in informe


def test_sin_repeticiones_no_hay_seccion_de_estabilidad() -> None:
    informe = m.resumir([_muestra("V3-A", m.CLASE_ATAQUE, 1, True, 0.9)])
    assert "Estabilidad" not in informe


def test_con_idiomas_suma_los_textos_de_ocho_idiomas() -> None:
    base, con_idiomas = m.casos(), m.casos(con_idiomas=True)
    extra = con_idiomas[len(base) :]
    assert con_idiomas[: len(base)] == base
    assert {c.idioma for c in extra} == set(IDIOMAS_ESPERADOS)
    for idioma in IDIOMAS_ESPERADOS:
        clases = [c.clase for c in extra if c.idioma == idioma]
        assert sorted(clases) == [m.CLASE_ATAQUE, m.CLASE_ATAQUE, m.CLASE_LEGITIMA]
    ids = [c.id for c in con_idiomas]
    assert len(ids) == len(set(ids))


def test_el_corpus_multilingue_usa_las_mismas_clases_del_script() -> None:
    from ataques.corpus_multilingue import CORPUS_MULTILINGUE, IDIOMAS

    assert {clase for _, _, clase, _ in CORPUS_MULTILINGUE} == {
        m.CLASE_ATAQUE,
        m.CLASE_LEGITIMA,
    }
    assert {idioma for idioma, *_ in CORPUS_MULTILINGUE} == set(IDIOMAS)
    assert all(texto.strip() for *_, texto in CORPUS_MULTILINGUE)


def test_medir_conserva_el_idioma_de_cada_caso() -> None:
    muestras = m.medir(
        lambda _: (True, _Detalle("ok", 0.9)),
        [m.Caso("A", m.CLASE_ATAQUE, "x"), m.Caso("B", m.CLASE_ATAQUE, "y", "fr")],
    )
    assert [x.idioma for x in muestras] == [m.IDIOMA_BASE, "fr"]


def test_el_informe_separa_los_resultados_por_idioma() -> None:
    informe = m.resumir(
        [
            m.Muestra("A", m.CLASE_ATAQUE, 1, "ok", True, 0.9, idioma="es"),
            m.Muestra("B", m.CLASE_ATAQUE, 1, "ok", False, 0.2, idioma="zh"),
            m.Muestra("C", m.CLASE_LEGITIMA, 1, "ok", False, 0.0, idioma="zh"),
            m.Muestra("D", m.CLASE_ATAQUE, 1, "ok", True, 0.8, idioma="zh"),
        ]
    )
    assert "| es | 1/1 | 0/0 |" in informe
    assert "| zh | 1/2 | 0/1 |" in informe
    assert informe.index("| es |") < informe.index("| zh |")
    assert "traducciones hechas por un asistente de IA" in informe


def test_sin_otros_idiomas_no_hay_seccion_por_idioma() -> None:
    informe = m.resumir([_muestra("V3-A", m.CLASE_ATAQUE, 1, True, 0.9)])
    assert "## Por idioma" not in informe
    assert "--con-idiomas" in informe


def test_las_muestras_viejas_sin_idioma_se_leen_como_espanol() -> None:
    antigua = {
        "id": "V3-A",
        "clase": m.CLASE_ATAQUE,
        "latencia_ms": 1.0,
        "estado": "ok",
        "malicioso": True,
        "puntaje": 0.9,
    }
    assert m.Muestra.desde_dict(antigua).idioma == m.IDIOMA_BASE


def test_simular_con_idiomas_cuenta_los_textos_extra(monkeypatch, capsys) -> None:
    monkeypatch.setattr(m, "cargar_env", lambda _: None)
    monkeypatch.setenv("TYPESAFE_API_KEY", "clave-ficticia-de-prueba")
    monkeypatch.setenv("CLASIFICADOR_PERMITIR_REMOTO", "1")
    assert m.main(["--simular", "--con-idiomas"]) == 0
    assert (
        f"Se haran {len(m.casos(con_idiomas=True))} envios" in capsys.readouterr().err
    )


def test_solo_idiomas_no_reenvia_el_espanol() -> None:
    solo = m.casos(solo_idiomas=True)
    assert len(solo) == len(m.casos(con_idiomas=True)) - len(m.casos())
    assert all(c.idioma != m.IDIOMA_BASE for c in solo)


def test_los_limites_cuentan_lo_realmente_enviado() -> None:
    informe = m.resumir(
        [m.Muestra("ML-fr-A", m.CLASE_ATAQUE, 1, "ok", True, 0.9, idioma="fr")]
    )
    assert "(1 ataques, 0 legitimas)" in informe


def test_simular_solo_idiomas_cuenta_solo_los_nuevos(monkeypatch, capsys) -> None:
    monkeypatch.setattr(m, "cargar_env", lambda _: None)
    monkeypatch.setenv("TYPESAFE_API_KEY", "clave-ficticia-de-prueba")
    monkeypatch.setenv("CLASIFICADOR_PERMITIR_REMOTO", "1")
    assert m.main(["--simular", "--solo-idiomas"]) == 0
    assert "Se haran 24 envios" in capsys.readouterr().err

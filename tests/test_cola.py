"""Pruebas unitarias de la cola de revision y el rate limiter (proxy/cola.py).

Cada test crea su propia instancia de ColaRevision (nunca usa cola_global,
compartida en produccion) para no arrastrar estado entre casos.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from proxy.cola import ColaRevision

# --- encolar() / listar() / retirar() --------------------------------------


def test_encolar_agrega_id_y_timestamp_si_no_vienen() -> None:
    c = ColaRevision()

    encolada = c.encolar({"mensaje": "hola"})

    assert encolada is True
    assert c.tamano() == 1
    item = c.listar()[0]
    assert "id" in item
    assert "encolado_en" in item
    assert item["mensaje"] == "hola"


def test_encolar_respeta_campos_ya_presentes() -> None:
    c = ColaRevision()

    c.encolar({"id": "abc123", "encolado_en": "2020-01-01T00:00:00"})

    item = c.listar()[0]
    assert item["id"] == "abc123"
    assert item["encolado_en"] == "2020-01-01T00:00:00"


def test_encolar_rechaza_cuando_la_cola_esta_llena() -> None:
    c = ColaRevision(tamano_maximo=2)

    assert c.encolar({"n": 1}) is True
    assert c.encolar({"n": 2}) is True
    assert (
        c.encolar({"n": 3}) is False
    )  # cola llena: fail closed, no se pierde en silencio
    assert c.tamano() == 2


def test_listar_devuelve_copia_en_orden_de_llegada() -> None:
    c = ColaRevision()
    c.encolar({"n": 1})
    c.encolar({"n": 2})

    listado = c.listar()

    assert [item["n"] for item in listado] == [1, 2]
    listado.append({"n": 999})  # mutar la copia no debe afectar la cola real
    assert c.tamano() == 2


def test_retirar_por_id_quita_el_elemento_correcto() -> None:
    c = ColaRevision()
    c.encolar({"id": "primero", "n": 1})
    c.encolar({"id": "segundo", "n": 2})

    retirado = c.retirar("primero")

    assert retirado["n"] == 1
    assert c.tamano() == 1
    assert c.listar()[0]["id"] == "segundo"


def test_retirar_id_inexistente_lanza_key_error() -> None:
    c = ColaRevision()

    with pytest.raises(KeyError):
        c.retirar("no-existe")


# --- excede_limite() (rate limiter) ----------------------------------------


def test_excede_limite_permite_hasta_el_limite() -> None:
    c = ColaRevision(limite_por_minuto=3, ventana_s=60.0)

    assert c.excede_limite("cliente-a") is False
    assert c.excede_limite("cliente-a") is False
    assert c.excede_limite("cliente-a") is False  # 3ra peticion: aun no excede
    assert c.excede_limite("cliente-a") is True  # 4ta: ya excede


def test_excede_limite_es_independiente_por_cliente() -> None:
    c = ColaRevision(limite_por_minuto=1, ventana_s=60.0)

    assert c.excede_limite("cliente-a") is False
    assert c.excede_limite("cliente-a") is True
    assert c.excede_limite("cliente-b") is False  # otro cliente, cuenta aparte


def test_excede_limite_libera_espacio_fuera_de_la_ventana() -> None:
    c = ColaRevision(limite_por_minuto=1, ventana_s=0.05)

    assert c.excede_limite("cliente-a") is False
    assert c.excede_limite("cliente-a") is True
    time.sleep(0.1)
    assert c.excede_limite("cliente-a") is False  # la ventana ya expiro


# --- excede_limite_global() (rate limiter, todos los clientes juntos) -----


def test_excede_limite_global_permite_hasta_el_limite() -> None:
    c = ColaRevision(limite_global_por_minuto=3, ventana_s=60.0)

    assert c.excede_limite_global() is False
    assert c.excede_limite_global() is False
    assert c.excede_limite_global() is False  # 3ra: aun no excede
    assert c.excede_limite_global() is True  # 4ta: ya excede


def test_excede_limite_global_cuenta_distintos_clientes_juntos() -> None:
    """El caso que excede_limite() por si sola no puede frenar: muchos
    clientes distintos, cada uno muy por debajo de su propio limite, pero
    saturando el servicio entre todos. Los dos contadores son
    independientes (deques separadas) -- quien llama debe evaluar los dos
    en cada peticion real para que el global sume algo, tal como hace
    proxy/main.py::_verificar_limite_de_tasa() (llama a las dos juntas,
    nunca solo una)."""
    c = ColaRevision(limite_por_minuto=100, limite_global_por_minuto=3)

    resultados_globales = []
    for cliente in ["cliente-a", "cliente-b", "cliente-c", "cliente-d"]:
        excede_cliente = c.excede_limite(cliente)
        assert excede_cliente is False  # ninguno se acerca a su propio limite
        resultados_globales.append(c.excede_limite_global())

    # 4 clientes distintos, limite global de 3: los 3 primeros pasan, el 4to no.
    assert resultados_globales == [False, False, False, True]


def test_excede_limite_global_libera_espacio_fuera_de_la_ventana() -> None:
    c = ColaRevision(limite_global_por_minuto=1, ventana_s=0.05)

    assert c.excede_limite_global() is False
    assert c.excede_limite_global() is True
    time.sleep(0.1)
    assert c.excede_limite_global() is False  # la ventana ya expiro


def test_excede_limite_global_es_independiente_de_excede_limite_por_cliente() -> None:
    """Los dos contadores no interfieren entre si en ninguna direccion."""
    c = ColaRevision(limite_por_minuto=1, limite_global_por_minuto=1, ventana_s=60.0)

    assert c.excede_limite_global() is False  # gasta el cupo global
    assert c.excede_limite("cliente-a") is False  # el cupo por cliente sigue intacto


# --- Concurrencia: exactamente los escenarios que dispara el V5 -----------
#
# encolar() y excede_limite() hacen "verificar y luego actuar" (leer un
# tamano/conteo, decidir, y solo despues mutar). Sin el lock, dos hilos
# podrian pasar la verificacion antes de que ninguno escriba -- el GIL no
# protege esto porque el lock abarca varias operaciones, no una sola. Estas
# pruebas usan bastantes hilos contra la MISMA instancia para que esa
# condicion de carrera se manifieste de verdad si el lock fallara, no solo
# en teoria.


@pytest.mark.parametrize("intento", range(5))
def test_encolar_no_excede_tamano_maximo_bajo_rafaga_concurrente(
    intento: int,
) -> None:
    tamano_maximo = 20
    n_hilos = 60  # el triple del cupo: si el lock fallara, algunos "de mas" entrarian
    c = ColaRevision(tamano_maximo=tamano_maximo)

    with ThreadPoolExecutor(max_workers=n_hilos) as executor:
        resultados = list(executor.map(lambda i: c.encolar({"n": i}), range(n_hilos)))

    aceptadas = sum(1 for r in resultados if r)
    assert aceptadas == tamano_maximo
    assert c.tamano() == tamano_maximo  # nunca por encima del limite


@pytest.mark.parametrize("intento", range(5))
def test_excede_limite_cuenta_exacto_bajo_rafaga_concurrente(intento: int) -> None:
    limite = 20
    n_hilos = 60
    c = ColaRevision(limite_por_minuto=limite, ventana_s=60.0)

    with ThreadPoolExecutor(max_workers=n_hilos) as executor:
        resultados = list(
            executor.map(lambda _: c.excede_limite("mismo-cliente"), range(n_hilos))
        )

    no_excedidas = sum(1 for r in resultados if not r)
    excedidas = sum(1 for r in resultados if r)
    assert no_excedidas == limite
    assert excedidas == n_hilos - limite


@pytest.mark.parametrize("intento", range(5))
def test_excede_limite_global_cuenta_exacto_bajo_rafaga_concurrente(
    intento: int,
) -> None:
    """Mismo escenario que el de arriba, pero con muchos clientes DISTINTOS
    -- el caso real que excede_limite_global() existe para cubrir."""
    limite = 20
    n_hilos = 60
    c = ColaRevision(limite_por_minuto=1000, limite_global_por_minuto=limite)

    with ThreadPoolExecutor(max_workers=n_hilos) as executor:
        resultados = list(
            executor.map(lambda i: c.excede_limite_global(), range(n_hilos))
        )

    no_excedidas = sum(1 for r in resultados if not r)
    excedidas = sum(1 for r in resultados if r)
    assert no_excedidas == limite
    assert excedidas == n_hilos - limite

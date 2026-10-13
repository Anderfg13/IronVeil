"""Bateria de contrato: lo que TODO adaptador de `AlmacenMemoria` debe cumplir.

Sirve para los adaptadores que trae IronVeil y para el de cualquier empresa. Para probar
el de una base de datos propia basta heredar y dar una fabrica de instancias NUEVAS
sobre el mismo destino (una instancia nueva equivale a reiniciar el proxy):

    class TestMiAlmacen(ContratoAlmacen):
        @pytest.fixture
        def nuevo(self, tmp_path):
            return lambda: MiAlmacen("postgresql://...")

El nombre `ContratoAlmacen` no empieza por `Test`, asi que pytest no lo ejecuta solo:
corre dentro de cada subclase.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from proxy.memoria_decisiones import AlmacenMemoria, Regla


def regla(n: int = 1, **cambios: str | None) -> Regla:
    """Una regla de prueba; `n` la distingue de las demas."""
    datos: dict[str, str | None] = {
        "huella": f"{n:064x}",
        "modelo": "soporte",
        "decidido_por": "ana",
        "decidido_en": f"2026-10-06T10:00:{n:02d}-05:00",
        "motivo": "filtrado",
        "vista_previa": f"mensaje de prueba {n}",
    }
    datos.update(cambios)
    return Regla(**datos)  # type: ignore[arg-type]


class ContratoAlmacen:
    """Pruebas que todo adaptador debe pasar. Se hereda; no se ejecuta sola."""

    @pytest.fixture
    def nuevo(self, tmp_path: Path) -> Callable[[], AlmacenMemoria]:
        raise NotImplementedError(
            "el adaptador debe dar una fabrica de instancias nuevas del mismo destino"
        )

    def test_empieza_vacio(self, nuevo: Callable[[], AlmacenMemoria]) -> None:
        almacen = nuevo()

        assert almacen.cargar() == []
        almacen.cerrar()

    def test_lo_guardado_se_recupera_en_una_instancia_nueva(
        self, nuevo: Callable[[], AlmacenMemoria]
    ) -> None:
        antes = nuevo()
        antes.cargar()
        antes.guardar(regla(1))
        antes.cerrar()

        despues = nuevo()  # "reiniciar el proxy"

        assert despues.cargar() == [regla(1)]
        despues.cerrar()

    def test_conserva_todos_los_campos(
        self, nuevo: Callable[[], AlmacenMemoria]
    ) -> None:
        sin_vista = regla(1, vista_previa=None)
        con_unicode = regla(
            2, vista_previa="ñandú, ¿qué tal? 😀 …", decidido_por="sofía"
        )
        almacen = nuevo()
        almacen.cargar()
        almacen.guardar(sin_vista)
        almacen.guardar(con_unicode)
        almacen.cerrar()

        recuperadas = nuevo().cargar()

        assert sorted(recuperadas, key=lambda r: r.huella) == [sin_vista, con_unicode]

    def test_olvidar_quita_la_regla_y_una_instancia_nueva_lo_ve(
        self, nuevo: Callable[[], AlmacenMemoria]
    ) -> None:
        almacen = nuevo()
        almacen.cargar()
        almacen.guardar(regla(1))
        almacen.guardar(regla(2))

        almacen.olvidar(regla(1).huella, "luis", "2026-10-06T11:00:00-05:00")
        almacen.cerrar()

        assert nuevo().cargar() == [regla(2)]

    def test_olvidar_algo_que_no_existe_no_falla(
        self, nuevo: Callable[[], AlmacenMemoria]
    ) -> None:
        almacen = nuevo()
        almacen.cargar()

        almacen.olvidar("0" * 64, "luis", "2026-10-06T11:00:00-05:00")

        assert almacen.cargar() == []

    def test_guardar_la_misma_regla_dos_veces_no_la_duplica(
        self, nuevo: Callable[[], AlmacenMemoria]
    ) -> None:
        almacen = nuevo()
        almacen.cargar()
        almacen.guardar(regla(1))
        almacen.guardar(regla(1))
        almacen.cerrar()

        assert nuevo().cargar() == [regla(1)]

    def test_conserva_muchas_reglas(self, nuevo: Callable[[], AlmacenMemoria]) -> None:
        almacen = nuevo()
        almacen.cargar()
        for n in range(1, 31):
            almacen.guardar(regla(n))
        almacen.cerrar()

        assert len(nuevo().cargar()) == 30

    def test_cerrar_se_puede_llamar_mas_de_una_vez(
        self, nuevo: Callable[[], AlmacenMemoria]
    ) -> None:
        almacen = nuevo()
        almacen.cargar()

        almacen.cerrar()
        almacen.cerrar()  # no debe fallar

    def test_dice_donde_guarda(self, nuevo: Callable[[], AlmacenMemoria]) -> None:
        descripcion = nuevo().descripcion

        assert isinstance(descripcion, str) and descripcion.strip()

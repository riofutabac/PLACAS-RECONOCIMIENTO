"""Pruebas unitarias para el módulo lastre.seguimiento y lastre.trayectoria."""

from dataclasses import FrozenInstanceError
import pytest

from lastre.config import (
    BandaReloj,
    DeteccionConfig,
    Dimensiones,
    Poligono,
    Punto,
    Segmento,
    SeguimientoConfig,
    ZonaConfig,
)
from lastre.deteccion import Deteccion
from lastre.seguimiento import SeguidorTrayectorias, SeguimientoError
from lastre.trayectoria import Posicion, Trayectoria


@pytest.fixture
def config_seguimiento():
    """Configuración estándar con tolerancia de oclusión de 3 cuadros y distancia máxima de 50px."""
    return ZonaConfig(
        dimensiones=Dimensiones(ancho=2960, alto=1664),
        poligono=Poligono(vertices=(Punto(100, 100), Punto(500, 100), Punto(500, 500))),
        banda_reloj=BandaReloj(alto=100),
        segmento_salida=Segmento(punto_inicio=Punto(500, 100), punto_fin=Punto(500, 500)),
        deteccion=DeteccionConfig(area_minima=1000),
        seguimiento=SeguimientoConfig(
            distancia_maxima=50,
            tolerancia_oclusion=3,
            minimo_cuadros=2,
        ),
    )


def test_asociacion_objeto_unico(config_seguimiento):
    """Un móvil desplazándose a través de 5 cuadros debe generar exactamente 1 trayectoria continua."""
    seguidor = SeguidorTrayectorias(config_seguimiento)

    # Simular objeto moviéndose 10 px por cuadro: (100, 100) -> (140, 100)
    for f in range(1, 6):
        x = 100 + (f - 1) * 10
        det = Deteccion(caja=(x, 100, 40, 40), area=1600, centro=(x + 20, 120))
        cerradas = seguidor.actualizar(f, [det])
        assert len(cerradas) == 0

    # Finalizar video
    finales = seguidor.finalizar()
    assert len(finales) == 1
    t = finales[0]
    assert t.id == 1
    assert t.cuadro_inicio == 1
    assert t.cuadro_fin == 5
    assert t.total_observaciones == 5
    assert t.desplazamiento_neto == pytest.approx(40.0)


def test_tolerancia_a_oclusion(config_seguimiento):
    """Un objeto que desaparece durante 2 cuadros (<= tolerancia 3) debe mantenerse en la misma trayectoria."""
    seguidor = SeguidorTrayectorias(config_seguimiento)

    # Cuadros 1 y 2: detectado
    seguidor.actualizar(1, [Deteccion(caja=(100, 100, 30, 30), area=900, centro=(115, 115))])
    seguidor.actualizar(2, [Deteccion(caja=(110, 100, 30, 30), area=900, centro=(125, 115))])

    # Cuadros 3 y 4: oclusión temporal (sin detecciones)
    seguidor.actualizar(3, [])
    seguidor.actualizar(4, [])

    # Cuadro 5: reaparece cerca (dentro de distancia_maxima)
    seguidor.actualizar(5, [Deteccion(caja=(130, 100, 30, 30), area=900, centro=(145, 115))])

    finales = seguidor.finalizar()
    assert len(finales) == 1
    assert finales[0].id == 1
    assert finales[0].total_observaciones == 3
    assert finales[0].cuadro_inicio == 1
    assert finales[0].cuadro_fin == 5


def test_cierre_por_oclusion_excedida(config_seguimiento):
    """Si el objeto desaparece por más de 3 cuadros, la trayectoria debe cerrarse automáticamente."""
    seguidor = SeguidorTrayectorias(config_seguimiento)

    seguidor.actualizar(1, [Deteccion(caja=(100, 100, 30, 30), area=900, centro=(115, 115))])

    # 4 cuadros sin detección (> tolerancia de 3)
    seguidor.actualizar(2, [])
    seguidor.actualizar(3, [])
    seguidor.actualizar(4, [])
    cerradas = seguidor.actualizar(5, [])

    # En el cuadro 5 se superó la tolerancia (4 cuadros sin ver)
    assert len(cerradas) == 1
    assert cerradas[0].id == 1
    assert cerradas[0].cuadro_inicio == 1
    assert cerradas[0].cuadro_fin == 1


def test_separacion_dos_moviles(config_seguimiento):
    """Dos móviles separados espacialmente deben mantener identificadores distintos sin cruzarse."""
    seguidor = SeguidorTrayectorias(config_seguimiento)

    for f in range(1, 4):
        det1 = Deteccion(caja=(100 + f * 5, 100, 30, 30), area=900, centro=(115 + f * 5, 115))
        det2 = Deteccion(caja=(300 + f * 5, 300, 30, 30), area=900, centro=(315 + f * 5, 315))
        seguidor.actualizar(f, [det1, det2])

    finales = seguidor.finalizar()
    assert len(finales) == 2
    ids = {t.id for t in finales}
    assert ids == {1, 2}


def test_inmutabilidad_trayectoria(config_seguimiento):
    """Verifica que las instancias de Trayectoria y Posicion sean inmutables."""
    pos = Posicion(cuadro=1, centro=(100, 100), caja=(90, 90, 20, 20), area=400)
    with pytest.raises(FrozenInstanceError):
        pos.cuadro = 2

    tray = Trayectoria(id=1, cuadro_inicio=1, cuadro_fin=1, posiciones=(pos,))
    with pytest.raises(FrozenInstanceError):
        tray.id = 2


def test_serializacion_json_dict():
    """Verifica que como_dict genere la estructura completa para persistencia."""
    pos = Posicion(cuadro=10, centro=(50, 60), caja=(40, 50, 20, 20), area=400)
    tray = Trayectoria(id=7, cuadro_inicio=10, cuadro_fin=10, posiciones=(pos,))
    d = tray.como_dict()

    assert d["id"] == 7
    assert d["cuadro_inicio"] == 10
    assert d["total_observaciones"] == 1
    assert d["posiciones"][0]["centro"] == [50, 60]

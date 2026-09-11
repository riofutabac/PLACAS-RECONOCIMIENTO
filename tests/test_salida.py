"""Pruebas unitarias para el módulo lastre.salida."""

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
from lastre.salida import (
    CATEGORIA_ENTRADA,
    CATEGORIA_PERMANENCIA,
    CATEGORIA_RUIDO,
    CATEGORIA_SALIDA,
    clasificar_trayectoria,
    clasificar_trayectorias,
)
from lastre.trayectoria import Posicion, Trayectoria


@pytest.fixture
def config_zona():
    """Configuración sintética con polígono en x in [0..200] y segmento de salida vertical en x=150."""
    return ZonaConfig(
        dimensiones=Dimensiones(ancho=300, alto=300),
        poligono=Poligono(
            vertices=(
                Punto(10, 10),
                Punto(150, 10),
                Punto(150, 200),
                Punto(10, 200),
            )
        ),
        banda_reloj=BandaReloj(alto=10),
        segmento_salida=Segmento(
            punto_inicio=Punto(150, 10),
            punto_fin=Punto(150, 200),
        ),
        deteccion=DeteccionConfig(area_minima=100),
        seguimiento=SeguimientoConfig(
            distancia_maxima=40,
            tolerancia_oclusion=3,
            minimo_cuadros=3,
        ),
    )


def test_descarte_ruido_por_poca_duracion(config_zona):
    """Trayectoria con menos de 3 cuadros es descartada como ruido."""
    pos = (
        Posicion(cuadro=1, centro=(50, 50), caja=(40, 40, 20, 20), area=400),
        Posicion(cuadro=2, centro=(90, 50), caja=(80, 40, 20, 20), area=400),
    )
    tray = Trayectoria(id=1, cuadro_inicio=1, cuadro_fin=2, posiciones=pos)
    res = clasificar_trayectoria(tray, config_zona)
    assert res.categoria == CATEGORIA_RUIDO
    assert not res.es_salida


def test_descarte_ruido_por_poco_desplazamiento(config_zona):
    """Trayectoria estática o con vibración (vehículo estacionado) es descartada como ruido."""
    pos = tuple(
        Posicion(cuadro=i, centro=(50, 50 + (i % 2)), caja=(40, 40, 20, 20), area=400)
        for i in range(1, 6)
    )
    tray = Trayectoria(id=2, cuadro_inicio=1, cuadro_fin=5, posiciones=pos)
    res = clasificar_trayectoria(tray, config_zona, desplazamiento_minimo=20.0)
    assert res.categoria == CATEGORIA_RUIDO
    assert not res.es_salida


def test_clasificacion_salida_valida(config_zona):
    """Trayectoria que inicia en el interior y cruza el segmento hacia la derecha es clasificada como salida."""
    # Segmento de salida en x=150, de y=10 a y=200
    # Trayectoria de x=100 a x=180 a la altura y=100
    pos = (
        Posicion(cuadro=10, centro=(100, 100), caja=(90, 90, 20, 20), area=400),
        Posicion(cuadro=11, centro=(130, 100), caja=(120, 90, 20, 20), area=400),
        Posicion(cuadro=12, centro=(170, 100), caja=(160, 90, 20, 20), area=400),  # Cruce ocurrió aquí
        Posicion(cuadro=13, centro=(190, 100), caja=(180, 90, 20, 20), area=400),
    )
    tray = Trayectoria(id=3, cuadro_inicio=10, cuadro_fin=13, posiciones=pos)
    res = clasificar_trayectoria(tray, config_zona)
    assert res.categoria == CATEGORIA_SALIDA
    assert res.es_salida
    assert res.cuadro_cruce == 12
    assert res.caja_cruce == (160, 90, 20, 20)


def test_clasificacion_entrada(config_zona):
    """Trayectoria que ingresa desde la derecha hacia la izquierda es clasificada como entrada."""
    pos = (
        Posicion(cuadro=20, centro=(190, 100), caja=(180, 90, 20, 20), area=400),
        Posicion(cuadro=21, centro=(160, 100), caja=(150, 90, 20, 20), area=400),
        Posicion(cuadro=22, centro=(130, 100), caja=(120, 90, 20, 20), area=400),  # Cruce hacia adentro
        Posicion(cuadro=23, centro=(100, 100), caja=(90, 90, 20, 20), area=400),
    )
    tray = Trayectoria(id=4, cuadro_inicio=20, cuadro_fin=23, posiciones=pos)
    res = clasificar_trayectoria(tray, config_zona)
    assert res.categoria == CATEGORIA_ENTRADA
    assert not res.es_salida


def test_clasificacion_permanencia(config_zona):
    """Trayectoria con desplazamiento real que permanece dentro del polígono sin cruzar el segmento."""
    pos = (
        Posicion(cuadro=30, centro=(40, 50), caja=(30, 40, 20, 20), area=400),
        Posicion(cuadro=31, centro=(60, 70), caja=(50, 60, 20, 20), area=400),
        Posicion(cuadro=32, centro=(80, 90), caja=(70, 80, 20, 20), area=400),
        Posicion(cuadro=33, centro=(100, 110), caja=(90, 100, 20, 20), area=400),
    )
    tray = Trayectoria(id=5, cuadro_inicio=30, cuadro_fin=33, posiciones=pos)
    res = clasificar_trayectoria(tray, config_zona)
    assert res.categoria == CATEGORIA_PERMANENCIA
    assert not res.es_salida


def test_clasificar_trayectorias_lote(config_zona):
    """Verifica clasificación en lote con múltiples trayectorias."""
    t_salida = Trayectoria(
        id=1, cuadro_inicio=1, cuadro_fin=4,
        posiciones=(
            Posicion(1, (100, 100), (90, 90, 20, 20), 400),
            Posicion(2, (130, 100), (120, 90, 20, 20), 400),
            Posicion(3, (160, 100), (150, 90, 20, 20), 400),
            Posicion(4, (180, 100), (170, 90, 20, 20), 400),
        ),
    )
    t_ruido = Trayectoria(
        id=2, cuadro_inicio=5, cuadro_fin=5,
        posiciones=(Posicion(5, (100, 100), (90, 90, 20, 20), 400),),
    )

    resultados = clasificar_trayectorias([t_salida, t_ruido], config_zona)
    assert len(resultados) == 2
    assert resultados[0].es_salida
    assert not resultados[1].es_salida

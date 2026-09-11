"""Pruebas unitarias para el módulo lastre.deteccion."""

import numpy as np
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
from lastre.deteccion import Deteccion, DeteccionError, DetectorMovimiento


@pytest.fixture
def config_prueba():
    """Configuración para pruebas sintéticas de 200x200 con polígono delimitado."""
    return ZonaConfig(
        dimensiones=Dimensiones(ancho=200, alto=200),
        poligono=Poligono(
            vertices=(
                Punto(10, 30),
                Punto(120, 30),
                Punto(120, 180),
                Punto(10, 180),
            )
        ),
        banda_reloj=BandaReloj(alto=20),
        segmento_salida=Segmento(
            punto_inicio=Punto(120, 30),
            punto_fin=Punto(120, 180),
        ),
        deteccion=DeteccionConfig(area_minima=100),
        seguimiento=SeguimientoConfig(
            distancia_maxima=30,
            tolerancia_oclusion=5,
            minimo_cuadros=3,
        ),
    )


def test_inicializacion_parametros_invalidos(config_prueba):
    """Verifica validación de factor_escala."""
    with pytest.raises(DeteccionError, match="factor_escala"):
        DetectorMovimiento(config_prueba, factor_escala=0.0)

    with pytest.raises(DeteccionError, match="factor_escala"):
        DetectorMovimiento(config_prueba, factor_escala=1.5)


def test_dimensiones_incompatibles(config_prueba):
    """Verifica que cuadros con dimensiones distintas a la configuración lancen DeteccionError."""
    detector = DetectorMovimiento(config_prueba)
    cuadro_malo = np.zeros((100, 100, 3), dtype=np.uint8)
    with pytest.raises(DeteccionError, match="no coinciden"):
        detector.detectar(cuadro_malo)


def test_deteccion_cuadro_estatico(config_prueba):
    """Un fondo estático sin movimiento no debe producir detecciones."""
    detector = DetectorMovimiento(config_prueba)
    fondo = np.full((200, 200, 3), fill_value=128, dtype=np.uint8)

    # Entrenar fondo
    for _ in range(15):
        dets = detector.detectar(fondo)

    assert len(dets) == 0


def test_deteccion_objeto_en_zona(config_prueba):
    """Un objeto blanco en movimiento dentro del polígono debe ser detectado."""
    detector = DetectorMovimiento(config_prueba)
    fondo = np.zeros((200, 200, 3), dtype=np.uint8)

    # Inicializar fondo
    for _ in range(10):
        detector.detectar(fondo)

    # Introducir objeto dentro de la zona (zona: x en [10, 120], y en [30, 180])
    cuadro_con_movimiento = fondo.copy()
    # Caja de 20x20 = 400 píxeles > area_minima (100) en (x=50..70, y=80..100)
    cuadro_con_movimiento[80:100, 50:70] = 255

    detecciones = detector.detectar(cuadro_con_movimiento)
    assert len(detecciones) >= 1
    det = detecciones[0]
    assert isinstance(det, Deteccion)
    assert det.area >= 100
    # Centro aproximado en (60, 90)
    assert abs(det.centro[0] - 60) <= 5
    assert abs(det.centro[1] - 90) <= 5


def test_movimiento_fuera_de_zona_es_ignorado(config_prueba):
    """El movimiento fuera de la zona (ej. en la carretera o reloj) no genera detecciones."""
    detector = DetectorMovimiento(config_prueba)
    fondo = np.zeros((200, 200, 3), dtype=np.uint8)

    for _ in range(10):
        detector.detectar(fondo)

    # Movimiento en la carretera principal (x=150..180 > 120)
    cuadro_externo = fondo.copy()
    cuadro_externo[80:110, 150:180] = 255

    detecciones = detector.detectar(cuadro_externo)
    assert len(detecciones) == 0

    # Movimiento en la banda del reloj (y=5..15 < 20)
    cuadro_reloj = fondo.copy()
    cuadro_reloj[5:15, 30:70] = 255
    detecciones_reloj = detector.detectar(cuadro_reloj)
    assert len(detecciones_reloj) == 0


def test_inmutabilidad_cuadro_entrada(config_prueba):
    """Verifica que el detector no modifique en absoluto el arreglo de entrada."""
    detector = DetectorMovimiento(config_prueba)
    cuadro = np.full((200, 200, 3), 77, dtype=np.uint8)
    copia = cuadro.copy()

    detector.detectar(cuadro)
    assert np.array_equal(cuadro, copia)
